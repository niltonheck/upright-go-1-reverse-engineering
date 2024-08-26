import asyncio
import argparse
from lib.pair import scan
from lib.subscriber import listen_for_notifications

"""This is a simple example of how to pair to a device and listen for notifications.
Please ignore the non-used variables, iI meant to evolve it (and will do later).
"""


async def main():
    parser = argparse.ArgumentParser(description='BLE Scanner')
    parser.add_argument('--pair', action='store_true', help='Pair to device')

    # Search for a Upright GO V1 device
    # If found, pair to device
    device_uuid = None

    args = parser.parse_args()
    if args.pair or device_uuid is None:
        print("Preparing to pair to device")
        print("Make sure the device is in pairing mode (blue blinking light)")

        devide_addr = await scan()
        print(f"Device address: {devide_addr}")

        if devide_addr is None:
            print("Device not found")
            return

        device_uuid = devide_addr

    characteristic_uuid = "0000aac6-0000-1000-8000-00805f9b34fb"

    # Listen for notifications from the device
    await listen_for_notifications(device_uuid, characteristic_uuid)


if __name__ == "__main__":
    asyncio.run(main())
