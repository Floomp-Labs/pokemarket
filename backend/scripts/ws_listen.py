"""Dev check: connect to the live WebSocket and print the first event."""

import asyncio

import websockets


async def main():
    for _ in range(30):
        try:
            async with websockets.connect("ws://localhost:8000/ws") as ws:
                print("connected", flush=True)
                msg = await asyncio.wait_for(ws.recv(), timeout=60)
                print(f"RECEIVED: {msg}", flush=True)
                return
        except Exception:
            await asyncio.sleep(1)
    print("FAILED: no message received", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
