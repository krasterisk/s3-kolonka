import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from s3_kolonka_gw.adapters.base import VoiceBackend
from s3_kolonka_gw.device_ctrl import (
    TOOLS,
    apply_tool,
    attach_music_play,
    attach_radio_play,
    heuristic_commands,
    music_play_query,
    radio_play_query,
    spoken_ack,
)
from s3_kolonka_gw import radio
from s3_kolonka_gw import youtube
from s3_kolonka_gw.pcmutil import (
    RADIO_FRAME_BYTES,
    audio_to_pcm16,
    espeak_to_pcm16,
    ffmpeg_radio_cmd,
    mp3_to_pcm16,
    pcm16_rms,
    pcm16_to_wav,
    piper_to_pcm16,
    radio_drop_for_live,
)
from s3_kolonka_gw.wake import match_wake

log = logging.getLogger("gw.groq")

GROQ_BASE = "https://api.groq.com/openai/v1"
_MAX_BYTES = 16000 * 2 * 12
_CHUNK = 3200
_SPEECH_RMS = 400.0
_GRACE_MS = 800
_SILENCE_MS = 1200
_MAX_LISTEN_MS = 12000
_SYSTEM = (
    "Ты голосовой ассистент умной колонки. Отвечай кратко, по-русски, "
    "без списков и разметки. Одно-три предложения. "
    "Если просят громкость, яркость, выключить или включить колонку — "
    "вызови соответствующую функцию. "
    "play_radio вызывай только если в фразе есть слово «радио». "
    "Иначе включить что-то (песню, мультфильм, «хрум», «сказочный детектив», "
    "название через «или», «с youtube») — play_music, источник YouTube. "
    "Выключить радио или музыку — stop_radio. "
    "Не выдумывай названия станций, треков и URL. "
    "Если инструмент вернул ask — озвучь этот вопрос. "
    "Если станции или трека нет — попроси уточнить."
)


class GroqBackend(VoiceBackend):
    name = "groq"

    def __init__(self, cfg=None, radio_cfg=None, youtube_cfg=None):
        cfg = cfg or {}
        self.api_key = (cfg.get("api_key") or os.environ.get("GROQ_API_KEY") or "").strip()
        self.radio_cfg = radio.normalize_config(radio_cfg)
        self.youtube_cfg = youtube.normalize_config(youtube_cfg)
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
        self._turn_task = None
        self._radio_proc = None
        self._ytdlp_proc = None
        self._gen = 0
        self._pcm_epoch = -1
        self._mode = "tap"
        self._vol = 50
        self._bl = 70
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

    async def start(self, on_pcm, on_status):
        async def gated(data):
            if self._pcm_epoch != self._gen:
                return
            await on_pcm(data)

        await super().start(gated, on_status)

    def _arm_tts(self):
        self._pcm_epoch = self._gen

    async def listen(self, mode="tap"):
        if not self.api_key:
            await self.status("error", "groq: no api_key")
            return
        self._gen += 1
        self._pcm_epoch = -1
        await self.close()
        self._mode = mode if mode in ("wake", "tap") else "tap"
        self._listening = True
        self._busy = False
        self._buf.clear()
        self._reset_vad()
        log.info("listen mode=%s gen=%s", self._mode, self._gen)
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
            log.info(
                "auto-stop silence %sms after %sms rms=%.0f bytes=%d",
                self._silence_ms,
                self._listen_ms,
                pcm16_rms(bytes(self._buf)),
                len(self._buf),
            )
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
        self._turn_task = asyncio.create_task(self._run_turn(pcm), name="gw-turn")

    async def _run_turn(self, pcm: bytes):
        try:
            await self._finish_turn(pcm)
        finally:
            self._busy = False

    async def close(self):
        self._pcm_epoch = -1
        await self._kill_radio()
        task = self._turn_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def stop_radio(self):
        log.info("radio stop")
        self._pcm_epoch = -1
        await self._kill_radio()
        await self.status("idle", "groq", reply="Радио выключено.")

    async def _kill_radio(self):
        procs = [self._radio_proc, self._ytdlp_proc]
        self._radio_proc = None
        self._ytdlp_proc = None
        for proc in procs:
            if not proc:
                continue
            if proc.returncode is None:
                proc.kill()
                try:
                    await proc.wait()
                except Exception:
                    pass

    async def _pump_pcm(self, proc):
        on_pcm = getattr(self, "_on_pcm", None)
        started = None
        sent = 0
        dropped = 0
        try:
            while True:
                data = await proc.stdout.read(RADIO_FRAME_BYTES)
                if not data:
                    break
                if self._pcm_epoch != self._gen:
                    break
                now = asyncio.get_event_loop().time()
                if started is None:
                    started = now
                if radio_drop_for_live(sent, now - started):
                    dropped += 1
                    continue
                if on_pcm:
                    await on_pcm(data)
                sent += len(data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("radio stream failed: %s", exc)
        finally:
            if dropped:
                log.info("radio drop %s frames to stay live", dropped)
            await self._kill_radio()

    async def _stream_radio(self, url: str):
        if youtube.is_youtube_source(url):
            await self._stream_youtube(url)
            return
        try:
            cmd = ffmpeg_radio_cmd(url)
        except Exception as exc:
            log.warning("radio ffmpeg cmd: %s", exc)
            await self.status("error", "radio decode: %s" % exc)
            return
        log.info("radio ffmpeg %s", url)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._radio_proc = proc
        await self._pump_pcm(proc)

    async def _stream_youtube(self, source: str):
        cached = youtube.cached_file(source, self.youtube_cfg)
        try:
            if cached:
                log.info("youtube cache %s", cached)
                cmd = youtube.ffmpeg_file_cmd(str(cached))
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                self._radio_proc = proc
                await self._pump_pcm(proc)
                return
            ytdlp_cmd, ff_cmd = youtube.youtube_pcm_cmds(source)
        except Exception as exc:
            log.warning("youtube cmd: %s", exc)
            await self.status("error", "youtube: %s" % exc)
            return
        log.info("youtube yt-dlp %s", source)
        ytdlp = await asyncio.create_subprocess_exec(
            *ytdlp_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._ytdlp_proc = ytdlp
        proc = await asyncio.create_subprocess_exec(
            *ff_cmd,
            stdin=ytdlp.stdout,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        if ytdlp.stdout:
            ytdlp.stdout.close()
        self._radio_proc = proc
        await self._pump_pcm(proc)

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

        woke, rest = match_wake(text)
        if self._mode == "wake" and not woke:
            log.info("ignore no wake: %s", text[:80])
            await self.status("idle", "no wake")
            return
        user_text = rest if woke else text
        if woke and not user_text:
            await self._speak("Слушаю.", heard=text)
            return

        await self.status("thinking", "groq llm", heard=user_text)
        try:
            reply, cmds, radio_err = await loop.run_in_executor(
                None, self._reply_and_radio, user_text
            )
        except Exception as exc:
            log.exception("llm")
            await self.status("error", "groq llm: %s" % exc)
            return
        if radio_err:
            reply = radio_err
        if cmds:
            await self._emit_cmds(cmds)
            if not reply:
                reply = spoken_ack(cmds)
        radio_cmd = next((c for c in cmds if c.get("name") == "radio_play"), None)
        if radio_cmd:
            title = radio_cmd.get("title") or "радио"
            source = radio_cmd.get("source") or ""
            self._arm_tts()
            await self.status("radio", title, heard=user_text, reply=title)
            stream_gen = self._gen
            await self._stream_radio(source)
            if self._gen == stream_gen:
                await self.status("idle", "groq")
            return
        if any(c.get("name") == "radio_stop" for c in cmds):
            await self.status("idle", "groq", heard=user_text, reply=reply or "Радио выключено.")
            return
        if not reply:
            await self.status("idle", "groq: empty llm")
            return
        log.info("llm: %s", reply[:120])

        await self._speak(reply, heard=user_text)

    async def _speak(self, reply: str, heard: str = ""):
        self._arm_tts()
        await self.status("speaking", "groq tts", heard=heard, reply=reply)
        try:
            audio = await self._tts(reply)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("tts")
            await self.status("error", "groq tts: %s" % exc)
            return
        if self._pcm_epoch != self._gen:
            return

        on_pcm = getattr(self, "_on_pcm", None)
        if on_pcm and audio:
            try:
                for i in range(0, len(audio), _CHUNK):
                    if self._pcm_epoch != self._gen:
                        return
                    await on_pcm(audio[i : i + _CHUNK])
                    await asyncio.sleep(0.07)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("tts send failed: %s", exc)
                await self.status("error", "tts send failed")
                return
        if self._pcm_epoch != self._gen:
            return
        await self.status("idle", "groq")

    async def _emit_cmds(self, cmds):
        cb = getattr(self, "_on_cmd", None)
        for cmd in cmds:
            name = cmd.get("name")
            if name == "volume":
                self._vol = int(cmd.get("value") or self._vol)
            elif name == "brightness":
                self._bl = int(cmd.get("value") or self._bl)
            if cb:
                await cb(name, cmd.get("value"), url=cmd.get("url"), title=cmd.get("title"))
            log.info("cmd %s %s", name, cmd.get("value") or cmd.get("title") or "")

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

    def _complete(self, messages, use_tools=True):
        payload = {
            "model": self.llm_model,
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": 400,
        }
        if use_tools:
            payload["tools"] = TOOLS
            payload["tool_choice"] = "auto"
        req = urllib.request.Request(
            GROQ_BASE + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers({"Content-Type": "application/json"}),
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            if use_tools and exc.code in (400, 404, 422):
                log.warning("llm tools unsupported: %s %s", exc.code, body)
                return self._complete(messages, use_tools=False)
            raise RuntimeError("llm HTTP %s %s" % (exc.code, body)) from exc

    def _reply_and_radio(self, user_text: str):
        reply, cmds = self._chat(user_text)
        if not cmds:
            cmds = heuristic_commands(user_text, self._vol, self._bl)
        cmds, music_err = attach_music_play(cmds, user_text, self._pick_music)
        if music_err:
            return reply, cmds, music_err
        cmds, radio_err = attach_radio_play(cmds, user_text, self._pick_radio)
        return reply, cmds, radio_err

    def _chat(self, user_text: str):
        messages = [{"role": "system", "content": _SYSTEM}]
        messages.extend(self._history[-8:])
        messages.append({"role": "user", "content": user_text})
        payload = self._complete(messages, use_tools=True)
        message = payload["choices"][0]["message"]
        cmds = []
        vol, bl = self._vol, self._bl
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            messages.append(message)
            for call in tool_calls:
                fn = (call.get("function") or {})
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                extra, vol, bl = apply_tool(name, args, vol, bl)
                cmds.extend(extra)
                tool_body = extra or {"ok": True}
                if name == "play_radio" and radio_play_query(user_text) is None:
                    name = "play_music"
                    if not (args.get("query") or "").strip():
                        args["query"] = music_play_query(user_text) or user_text
                if name == "play_radio":
                    picked = self._pick_radio((args.get("query") or user_text or "").strip())
                    if picked and picked.get("url"):
                        extra = [radio.device_play_cmd(picked)]
                        cmds.extend(extra)
                        tool_body = {"ok": True, "title": extra[0]["title"], "uuid": picked.get("uuid")}
                    elif picked and picked.get("clarify"):
                        tool_body = {"ok": False, "ask": picked["clarify"]}
                    else:
                        tool_body = {"ok": False, "error": "no station"}
                if name == "play_music":
                    picked = self._pick_music((args.get("query") or user_text or "").strip())
                    if picked and (picked.get("url") or picked.get("video_id")):
                        extra = [youtube.device_music_cmd(picked)]
                        cmds.extend(extra)
                        tool_body = {
                            "ok": True,
                            "title": extra[0]["title"],
                            "id": picked.get("video_id"),
                        }
                    else:
                        tool_body = {"ok": False, "error": "no track"}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "content": json.dumps(tool_body),
                    }
                )
            try:
                follow = self._complete(messages, use_tools=False)
                message = follow["choices"][0]["message"]
            except RuntimeError as exc:
                log.warning("llm follow failed: %s", exc)
                return spoken_ack(cmds), cmds
        reply = (message.get("content") or "").strip()
        if not reply:
            reply = (message.get("reasoning") or "").strip()
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": reply or spoken_ack(cmds)})
        return reply, cmds

    def _pick_music(self, query: str):
        try:
            picked = youtube.resolve_track(query, self.youtube_cfg)
            if picked:
                log.info("youtube pick %s %s", picked.get("video_id"), picked.get("title"))
            return picked
        except Exception as exc:
            log.warning("youtube resolve failed: %s", exc)
            return None

    def _pick_radio(self, query: str):
        def picker(q, cands):
            slim = [
                {
                    "uuid": c["uuid"],
                    "name": c["name"],
                    "bitrate": c["bitrate"],
                    "countrycode": c.get("countrycode") or "",
                    "tags": c.get("tags") or "",
                }
                for c in cands
            ]
            prompt = radio.PICKER_PROMPT % (q, json.dumps(slim, ensure_ascii=False))
            payload = self._complete(
                [
                    {"role": "system", "content": "Pick one station. JSON only."},
                    {"role": "user", "content": prompt},
                ],
                use_tools=False,
            )
            return (payload["choices"][0]["message"].get("content") or "")

        try:
            return radio.resolve_station(query, self.radio_cfg, picker_fn=picker, opener=self._opener)
        except Exception as exc:
            log.warning("radio resolve failed: %s", exc)
            return None

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
