import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import websockets
import websockets.exceptions
import yaml

from s3_kolonka_gw.adapters import create_backend

log = logging.getLogger("gw")

_ORPHAN_SEC = 15
_ORPHAN_MIN = 16000
_orphans = {}


def peer_host(ws):
    addr = getattr(ws, "remote_address", None)
    if not addr:
        return ""
    return addr[0]


def stash_listen_orphan(store, host, pcm, mode, now=None):
    now = time.time() if now is None else now
    if not host or len(pcm or b"") < _ORPHAN_MIN:
        return False
    store[host] = {"pcm": bytes(pcm), "mode": mode or "tap", "ts": now}
    return True


def pop_listen_orphan(store, host, now=None):
    now = time.time() if now is None else now
    row = store.pop(host, None) if host else None
    if not row:
        return None
    if now - float(row.get("ts") or 0) > _ORPHAN_SEC:
        return None
    return row


def status_payload(state: str, detail: str = "", heard: str = "", reply: str = "", gen: int | None = None) -> dict:
    msg = {"type": "status", "state": state, "detail": detail}
    if heard:
        msg["heard"] = heard
    if reply:
        msg["reply"] = reply
    if gen is not None:
        msg["gen"] = int(gen)
    return msg


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def _resume_orphan(backend, row):
    """Re-arm listen from stashed uplink and start the turn.

    Must NOT await the turn task: doing so blocked the WebSocket recv loop for
    the whole YouTube/radio stream, so radio_stop/listen never ran until the
    track ended (and keepalive pings failed → reconnect storms).
    """
    pcm = row.get("pcm") or b""
    mode = row.get("mode") or "tap"
    log.info("resume orphan bytes=%s mode=%s", len(pcm), mode)
    await backend.listen(mode)
    backend._buf.clear()
    backend._buf.extend(pcm)
    backend._heard = True
    await backend.stop()


async def session(ws, path, cfg):
    peer = ws.remote_address
    host = peer_host(ws)
    backend = create_backend(cfg)
    log.info("client %s backend=%s", peer, backend.name)

    async def on_pcm(data: bytes):
        await ws.send(data)

    async def on_status(
        state: str,
        detail: str = "",
        heard: str = "",
        reply: str = "",
        gen: int | None = None,
    ):
        # Prefer the caller's pinned gen (turn_gen). Falling back to live
        # backend._gen re-introduces the race where a late idle is labeled
        # with the new listen gen and the speaker ends «Слушаю» immediately.
        if gen is None:
            gen = getattr(backend, "_gen", None)
        try:
            await ws.send(
                json.dumps(
                    status_payload(
                        state,
                        detail,
                        heard,
                        reply,
                        gen=gen,
                    )
                )
            )
        except Exception as exc:
            log.warning("status send failed: %s", exc)

    async def on_cmd(name, value=None, url=None, title=None):
        payload = {"type": "cmd", "name": name}
        if value is not None:
            payload["value"] = value
        if url:
            payload["url"] = url
        if title:
            payload["title"] = title
        try:
            await ws.send(json.dumps(payload))
        except Exception as exc:
            log.warning("cmd send failed: %s", exc)

    await backend.start(on_pcm, on_status)
    backend._on_cmd = on_cmd
    await ws.send(json.dumps({"type": "hello", "backend": backend.name, "sample_rate": 16000}))
    await on_status("idle", backend.name)
    orphan = pop_listen_orphan(_orphans, host)
    if orphan:
        await _resume_orphan(backend, orphan)

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
                await backend.listen(mode=cmd.get("mode") or "tap")
            elif kind == "stop":
                await backend.stop()
            elif kind == "radio_stop":
                await backend.stop_radio()
            else:
                await on_status("error", "unknown type")
    except websockets.exceptions.ConnectionClosed as exc:
        snap = backend.listen_pcm_snapshot()
        log.info(
            "client %s disconnected: %s listen_bytes=%s",
            peer,
            exc,
            len(snap),
        )
        if stash_listen_orphan(_orphans, host, snap, getattr(backend, "_mode", "tap")):
            log.info("orphan listen bytes=%s host=%s", len(snap), host)
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
