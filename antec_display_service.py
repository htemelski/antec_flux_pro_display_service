#!/usr/bin/env python3

import subprocess
import time
import re
import usb.core
import usb.util
import pynvml

def generate_payload(cpu_temp, gpu_temp):
    """
    Generate the HID payload for the digital display.
    :param cpu_temp: CPU temperature in °C (string).
    :param gpu_temp: GPU temperature in °C (string).
    :return: Payload as a bytes object.
    """
    def encode_temperature(temp):
        float_temp = float(temp)
        integer_part = int(float_temp // 10)
        tenths_part = int(float_temp % 10)
        hundredths_part = int((float_temp * 10) % 10)
        return f"{integer_part:02x}{tenths_part:02x}{hundredths_part:02x}"

    cpu_encoded = encode_temperature(cpu_temp)
    gpu_encoded = encode_temperature(gpu_temp)
    combined_encoded = bytes.fromhex(cpu_encoded + gpu_encoded)
    checksum = (sum(combined_encoded) + 7) % 256
    payload_hex = f"55aa010106{cpu_encoded}{gpu_encoded}{checksum:02x}"
    return bytes.fromhex(payload_hex)

def send_to_device(payload):
    """
    Send the generated payload to the USB device.
    :param payload: Payload as a bytes object.
    """
    VENDOR_ID = 0x2022
    PRODUCT_ID = 0x0522

    device = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if device is None:
        print("Device not found")
        return

    if device.is_kernel_driver_active(0):
        device.detach_kernel_driver(0)
    device.set_configuration()

    cfg = device.get_active_configuration()
    intf = cfg[(0, 0)]

    endpoint = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT,
    )

    if endpoint is None:
        print("Could not find OUT endpoint")
        return

    try:
        endpoint.write(payload)
    except usb.core.USBError as e:
        print(f"Failed to send payload: {e}")

    usb.util.dispose_resources(device)

def read_gpu_temp():
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        return str(temp)
    except (ImportError, pynvml.NVMLError):
        return "0.0"

def read_cpu_temp():
    def extract_temp(temp_str):
        match = re.search(r'Tctl:\s*\+([0-9]+\.[0-9]+)', temp_str)
        if match:
            return match.group(1)
        return None

    try:
        cpu_temp_line = subprocess.check_output('sensors k10temp-pci-00c3', shell=True, text=True)
        return extract_temp(cpu_temp_line)
    except subprocess.CalledProcessError:
        return "0.0"

def main():
    pynvml.nvmlInit()
    while True:
        cpu_temp = read_cpu_temp()
        gpu_temp = read_gpu_temp()
        payload = generate_payload(cpu_temp, gpu_temp)
        send_to_device(payload)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
