from typing import Awaitable, Callable, Optional

PcmFn = Callable[[bytes], Awaitable[None]]
StatusFn = Callable[..., Awaitable[None]]


class VoiceBackend:
    name = "base"

    async def start(self, on_pcm: PcmFn, on_status: StatusFn) -> None:
        self._on_pcm = on_pcm
        self._on_status = on_status

    async def send_pcm(self, data: bytes) -> None:
        raise NotImplementedError

    async def listen(self, mode: str = "tap") -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def listen_pcm_snapshot(self) -> bytes:
        return b""

    async def close(self) -> None:
        pass

    async def stop_radio(self) -> None:
        pass

    async def status(
        self,
        state: str,
        detail: str = "",
        heard: str = "",
        reply: str = "",
        gen: int | None = None,
    ) -> None:
        cb: Optional[StatusFn] = getattr(self, "_on_status", None)
        if not cb:
            return
        # Pass gen explicitly so a superseded turn cannot tag idle/thinking
        # with the newer listen generation (TOCTOU on backend._gen).
        try:
            await cb(state, detail, heard=heard, reply=reply, gen=gen)
        except TypeError:
            await cb(state, detail, heard, reply)
