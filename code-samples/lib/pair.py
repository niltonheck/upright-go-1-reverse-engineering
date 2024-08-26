from bleak import BleakScanner


async def scan():
    devices = await BleakScanner.discover()

    for device in devices:
        if device.name == "UprightGO":
            return device.address

    return None
