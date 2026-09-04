import array
import struct
import subprocess
import tempfile
from pathlib import Path


def pcm16_rms(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    acc = 0
    for sample in samples:
        acc += sample * sample
    return (acc / len(samples)) ** 0.5


def pcm16_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm


def _which(names):
    import sys
    from shutil import which

    for name in names:
        path = which(name)
        if path:
            return path
        for base in (Path(sys.executable).parent, Path(sys.prefix) / "bin"):
            sibling = base / name
            if sibling.is_file():
                return str(sibling)
    return None


def ffmpeg_radio_cmd(url, sample_rate=16000):
    raw = (url or "").strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raise ValueError("bad radio url")
    ffmpeg = _which(["ffmpeg"])
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "2",
        "-i",
        raw,
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]


def audio_to_pcm16(data: bytes, sample_rate: int = 16000, suffix: str = ".bin") -> bytes:
    ffmpeg = _which(["ffmpeg"])
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / ("in" + suffix)
        dst = Path(tmp) / "out.raw"
        src.write_bytes(data)
        subprocess.check_call(
            [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-f",
                "s16le",
                str(dst),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return dst.read_bytes()


def mp3_to_pcm16(mp3: bytes, sample_rate: int = 16000) -> bytes:
    return audio_to_pcm16(mp3, sample_rate=sample_rate, suffix=".mp3")


def piper_to_pcm16(text: str, model: str, sample_rate: int = 16000) -> bytes:
    if not model or not Path(model).is_file():
        raise RuntimeError("piper model not found: %s" % model)
    piper = _which(["piper"])
    if not piper:
        raise RuntimeError("piper not found")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "out.wav"
        proc = subprocess.run(
            [piper, "--model", model, "--output_file", str(wav)],
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0 or not wav.is_file():
            err = (proc.stderr or b"").decode("utf-8", "replace")[:200]
            raise RuntimeError("piper failed: %s" % err)
        return audio_to_pcm16(wav.read_bytes(), sample_rate=sample_rate, suffix=".wav")


def espeak_to_pcm16(text: str, voice: str = "ru", sample_rate: int = 16000) -> bytes:
    espeak = _which(["espeak-ng", "espeak"])
    if not espeak:
        raise RuntimeError("espeak-ng not found")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "out.wav"
        subprocess.check_call(
            [espeak, "-v", voice, "-s", "145", "-w", str(wav), text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return audio_to_pcm16(wav.read_bytes(), sample_rate=sample_rate, suffix=".wav")
