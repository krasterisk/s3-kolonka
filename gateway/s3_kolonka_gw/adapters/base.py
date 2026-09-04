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

    async def close(self) -> None:
        pass

    async def status(self, state: str, detail: str = "", heard: str = "", reply: str = "") -> None:
        cb: Optional[StatusFn] = getattr(self, "_on_status", None)
        if cb:
            await cb(state, detail, heard, reply)
