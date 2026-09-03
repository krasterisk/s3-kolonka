import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

import websockets
import websockets.exceptions
import yaml

from s3_kolonka_gw.adapters import create_backend

log = logging.getLogger("gw")


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def session(ws, path, cfg):
    peer = ws.remote_address
    backend = create_backend(cfg)
    log.info("client %s backend=%s", peer, backend.name)

    async def on_pcm(data: bytes):
        await ws.send(data)

    async def on_status(state: str, detail: str = ""):
        try:
            await ws.send(json.dumps({"type": "status", "state": state, "detail": detail}))
        except Exception as exc:
            log.warning("status send failed: %s", exc)

    await backend.start(on_pcm, on_status)
    await ws.send(json.dumps({"type": "hello", "backend": backend.name, "sample_rate": 16000}))
    await on_status("idle", backend.name)

    try:
        async for msg in ws:
            if isinstance(msg, bytes):
                await backend.send_pcm(msg)
                continue
            try:
                cmd = json.loads(msg)
            except json.JSONDecodeError:
                await on_status("error", "bad json")
                continue
            kind = cmd.get("type")
            if kind == "hello":
                await ws.send(json.dumps({"type": "hello", "backend": backend.name, "sample_rate": 16000}))
            elif kind == "listen":
                await backend.listen()
            elif kind == "stop":
                await backend.stop()
            else:
                await on_status("error", "unknown type")
    except websockets.exceptions.ConnectionClosed as exc:
        log.info("client %s disconnected: %s", peer, exc)
    finally:
        await backend.close()
        log.info("client %s closed", peer)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="s3-kolonka voice gateway")
    parser.add_argument(
        "--config",
        default=os.environ.get("KOLONKA_GW_CONFIG", ""),
        help="path to config.yaml",
    )
    args = parser.parse_args()
    here = Path(__file__).resolve().parent.parent
    cfg_path = Path(args.config) if args.config else here / "config.yaml"
    if not cfg_path.is_file():
        raise SystemExit("config not found: %s" % cfg_path)

    cfg = load_config(cfg_path)
    host = cfg.get("listen") or "0.0.0.0"
    port = int(cfg.get("port") or 8765)
    if port in (8123, 1900, 5353):
        raise SystemExit("port %s is reserved for Home Assistant" % port)

    log.info("listen %s:%s backend=%s config=%s", host, port, cfg.get("backend"), cfg_path)

    async def run():
        async def handler(ws, path):
            await session(ws, path, cfg)

        async with websockets.serve(
            handler,
            host,
            port,
            max_size=2 ** 20,
            max_queue=256,
            ping_interval=20,
            ping_timeout=60,
        ):
            await asyncio.Future()

    asyncio.run(run())


if __name__ == "__main__":
    main()
