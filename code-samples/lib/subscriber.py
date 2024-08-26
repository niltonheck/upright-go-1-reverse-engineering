import asyncio
from bleak import BleakClient


def notification_handler(sender, data):
    print(f"Notification from {sender}: {data}")


async def listen_for_notifications(address, characteristic_uuid):
    async with BleakClient(address) as client:
        await client.start_notify(characteristic_uuid, notification_handler)

        print(f"Subscribed to notifications from {characteristic_uuid}")

        await asyncio.sleep(3000)

        await client.stop_notify(characteristic_uuid)
