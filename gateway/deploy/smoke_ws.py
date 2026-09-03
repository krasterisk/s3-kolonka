import asyncio
import json

import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        print(await ws.recv())
        await ws.send(json.dumps({"type": "listen"}))
        print(await ws.recv())
        await ws.send(json.dumps({"type": "stop"}))
        print(await ws.recv())


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
