import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from s3_kolonka_gw.adapters.base import VoiceBackend
from s3_kolonka_gw.pcmutil import (
    audio_to_pcm16,
    espeak_to_pcm16,
    mp3_to_pcm16,
    pcm16_rms,
    pcm16_to_wav,
    piper_to_pcm16,
)

log = logging.getLogger("gw.groq")

GROQ_BASE = "https://api.groq.com/openai/v1"
_MAX_BYTES = 16000 * 2 * 12
_CHUNK = 640
_SPEECH_RMS = 400.0
_GRACE_MS = 800
_SILENCE_MS = 1200
_MAX_LISTEN_MS = 12000
_SYSTEM = (
    "Ты голосовой ассистент умной колонки. Отвечай кратко, по-русски, "
    "без списков и разметки. Одно-три предложения."
)


class GroqBackend(VoiceBackend):
    name = "groq"

    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.api_key = (cfg.get("api_key") or os.environ.get("GROQ_API_KEY") or "").strip()
        self.stt_model = cfg.get("stt_model") or "whisper-large-v3-turbo"
        self.llm_model = cfg.get("llm_model") or "openai/gpt-oss-20b"
        self.voice = cfg.get("voice") or "ru-RU-SvetlanaNeural"
        self.tts_model = cfg.get("tts_model") or "canopylabs/orpheus-v1-english"
        self.tts_voice = cfg.get("tts_voice") or "tara"
        self.espeak_voice = cfg.get("espeak_voice") or "ru"
        self.piper_model = (cfg.get("piper_model") or "/opt/s3-kolonka-gw/voices/ru_RU-irina-medium.onnx").strip()
        self.proxy = (cfg.get("proxy") or os.environ.get("KOLONKA_GROQ_PROXY") or "").strip()
        self._listening = False
        self._busy = False
        self._buf = bytearray()
        self._history = []
        self._reset_vad()

    def _reset_vad(self):
        self._heard = False
        self._silence_ms = 0
        self._listen_ms = 0
        if self.proxy:
            handler = urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
            self._opener = urllib.request.build_opener(handler)
            log.info("groq proxy=%s", self.proxy)
        else:
            self._opener = urllib.request.build_opener()

    async def listen(self):
        if not self.api_key:
            await self.status("error", "groq: no api_key")
            return
        self._listening = True
        self._busy = False
        self._buf.clear()
        self._reset_vad()
        log.info("listen")
        await self.status("live", "groq")

    async def send_pcm(self, data: bytes):
        if not self._listening or self._busy or not data:
            return
        self._buf.extend(data)
        if len(self._buf) > _MAX_BYTES:
            del self._buf[: len(self._buf) - _MAX_BYTES]
        ms = (len(data) // 2) * 1000 // 16000
        if ms <= 0:
            return
        self._listen_ms += ms
        rms = pcm16_rms(data)
        if self._listen_ms >= _GRACE_MS:
            if rms >= _SPEECH_RMS:
                self._heard = True
                self._silence_ms = 0
            elif self._heard:
                self._silence_ms += ms
        if self._heard and self._silence_ms >= _SILENCE_MS:
            log.info("auto-stop silence %sms after %sms", self._silence_ms, self._listen_ms)
            await self.stop()
            return
        if self._listen_ms >= _MAX_LISTEN_MS:
            log.info("auto-stop max listen %sms heard=%s", self._listen_ms, self._heard)
            await self.stop()

    async def stop(self):
        if self._busy:
            return
        self._listening = False
        self._busy = True
        pcm = bytes(self._buf)
        self._buf.clear()
        self._reset_vad()
        try:
            await self._finish_turn(pcm)
        finally:
            self._busy = False

    async def _finish_turn(self, pcm: bytes):
        if not self.api_key:
            await self.status("idle", "groq")
            return
        if len(pcm) < 3200:
            await self.status("idle", "groq: too short")
            return

        await self.status("thinking", "groq stt")
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(None, self._transcribe, pcm)
        except Exception as exc:
            log.exception("stt")
            await self.status("error", "groq stt: %s" % exc)
            return
        if not text:
            await self.status("idle", "groq: empty stt")
            return
        log.info("stt: %s", text[:120])

        await self.status("thinking", "groq llm")
        try:
            reply = await loop.run_in_executor(None, self._chat, text)
        except Exception as exc:
            log.exception("llm")
            await self.status("error", "groq llm: %s" % exc)
            return
        if not reply:
            await self.status("idle", "groq: empty llm")
            return
        log.info("llm: %s", reply[:120])

        await self.status("speaking", "groq tts")
        try:
            audio = await self._tts(reply)
        except Exception as exc:
            log.exception("tts")
            await self.status("error", "groq tts: %s" % exc)
            return

        on_pcm = getattr(self, "_on_pcm", None)
        if on_pcm and audio:
            for i in range(0, len(audio), _CHUNK):
                await on_pcm(audio[i : i + _CHUNK])
                await asyncio.sleep(0.018)
        await self.status("idle", "groq")

    def _headers(self, extra=None):
        headers = {
            "Authorization": "Bearer %s" % self.api_key,
            "User-Agent": "s3-kolonka-gw/1.0",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _transcribe(self, pcm: bytes) -> str:
        wav = pcm16_to_wav(pcm)
        boundary = "----KolonkaBoundary"
        body = (
            (
                "--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n%s\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nru\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"speech.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n"
                % (boundary, self.stt_model, boundary, boundary)
            ).encode("utf-8")
            + wav
            + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
        )
        req = urllib.request.Request(
            GROQ_BASE + "/audio/transcriptions",
            data=body,
            headers=self._headers({"Content-Type": "multipart/form-data; boundary=%s" % boundary}),
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError("stt HTTP %s %s" % (exc.code, exc.read().decode("utf-8", "replace")[:160])) from exc
        return (payload.get("text") or "").strip()

    def _chat(self, user_text: str) -> str:
        messages = [{"role": "system", "content": _SYSTEM}]
        messages.extend(self._history[-8:])
        messages.append({"role": "user", "content": user_text})
        body = json.dumps(
            {
                "model": self.llm_model,
                "messages": messages,
                "temperature": 0.6,
                "max_tokens": 400,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            GROQ_BASE + "/chat/completions",
            data=body,
            headers=self._headers({"Content-Type": "application/json"}),
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError("llm HTTP %s %s" % (exc.code, exc.read().decode("utf-8", "replace")[:160])) from exc
        message = payload["choices"][0]["message"]
        reply = (message.get("content") or "").strip()
        if not reply:
            reply = (message.get("reasoning") or "").strip()
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def _tts_groq(self, text: str) -> bytes:
        body = json.dumps(
            {
                "model": self.tts_model,
                "input": text,
                "voice": self.tts_voice,
                "response_format": "wav",
                "sample_rate": 16000,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            GROQ_BASE + "/audio/speech",
            data=body,
            headers=self._headers({"Content-Type": "application/json", "Accept": "audio/wav"}),
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=60) as resp:
                audio = resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError("tts HTTP %s %s" % (exc.code, exc.read().decode("utf-8", "replace")[:160])) from exc
        if not audio:
            raise RuntimeError("empty groq tts")
        return audio_to_pcm16(audio, suffix=".wav")

    async def _tts_edge(self, text: str) -> bytes:
        import edge_tts

        comm = edge_tts.Communicate(text, self.voice)
        mp3 = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                mp3.extend(chunk["data"])
        if not mp3:
            raise RuntimeError("empty edge tts")
        return mp3_to_pcm16(bytes(mp3))

    async def _tts(self, text: str) -> bytes:
        errors = []
        loop = asyncio.get_event_loop()
        try:
            pcm = await loop.run_in_executor(
                None, lambda: piper_to_pcm16(text, self.piper_model)
            )
            log.info("tts piper %s bytes=%s", Path(self.piper_model).name, len(pcm))
            return pcm
        except Exception as exc:
            errors.append("piper:%s" % exc)
            log.warning("tts piper failed: %s", exc)
        try:
            pcm = await loop.run_in_executor(
                None, lambda: espeak_to_pcm16(text, voice=self.espeak_voice)
            )
            log.info("tts espeak %s bytes=%s", self.espeak_voice, len(pcm))
            return pcm
        except Exception as exc:
            errors.append("espeak:%s" % exc)
            log.warning("tts espeak failed: %s", exc)
        try:
            pcm = await loop.run_in_executor(None, self._tts_groq, text)
            log.info("tts groq %s", self.tts_voice)
            return pcm
        except Exception as exc:
            errors.append("groq:%s" % exc)
            log.warning("tts groq failed: %s", exc)
        try:
            pcm = await self._tts_edge(text)
            log.info("tts edge %s", self.voice)
            return pcm
        except Exception as exc:
            errors.append("edge:%s" % exc)
            raise RuntimeError("tts failed %s" % " | ".join(errors)) from exc
