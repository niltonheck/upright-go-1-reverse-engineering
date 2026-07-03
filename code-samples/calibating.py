import asyncio
from bleak import BleakClient


async def send_signals(device_address: str, characteristic_uuid: str):
    async with BleakClient(device_address) as client:
        await client.write_gatt_char(characteristic_uuid, bytearray(b'\x01'))
        print("Calibrate signal sent.")

if __name__ == "__main__":
    # Replace with your device's address
    device_address = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

    # Calibration characteristic (aab1). NOTE: an earlier version of this
    # sample used aaa6, which does not exist in the device's GATT tree —
    # hardware-confirmed 2026-07-03 (see PROTOCOL.md). The device acks a
    # successful calibration with a double vibration.
    characteristic_uuid = "0000aab1-0000-1000-8000-00805f9b34fb"

    # Run the asyncio event loop
    asyncio.run(send_signals(device_address, characteristic_uuid))
