"""Probe Groq STT from the gateway host. Never prints the API key."""
import json
import struct
import urllib.error
import urllib.request
from pathlib import Path

import yaml

cfg = yaml.safe_load(Path("/opt/s3-kolonka-gw/config.yaml").read_text(encoding="utf-8")) or {}
groq = cfg.get("groq") or {}
key = (groq.get("api_key") or "").strip()
model = groq.get("stt_model") or "whisper-large-v3-turbo"
print("has_key", bool(key), "model", model)

pcm = b"\x00\x00" * 16000
wav = struct.pack(
    "<4sI4s4sIHHIIHH4sI",
    b"RIFF",
    36 + len(pcm),
    b"WAVE",
    b"fmt ",
    16,
    1,
    1,
    16000,
    32000,
    2,
    16,
    b"data",
    len(pcm),
) + pcm
boundary = "----KolonkaBoundary"
body = (
    (
        "--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n%s\r\n"
        "--%s\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nru\r\n"
        "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"speech.wav\"\r\n"
        "Content-Type: audio/wav\r\n\r\n"
        % (boundary, model, boundary, boundary)
    ).encode("utf-8")
    + wav
    + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
)

for label, headers in (
    ("no-ua", {"Authorization": "Bearer " + key, "Content-Type": "multipart/form-data; boundary=%s" % boundary}),
    (
        "with-ua",
        {
            "Authorization": "Bearer " + key,
            "User-Agent": "s3-kolonka-gw/1.0",
            "Accept": "application/json",
            "Content-Type": "multipart/form-data; boundary=%s" % boundary,
        },
    ),
):
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            print(label, "OK", resp.status, "text_len", len((payload.get("text") or "")))
    except urllib.error.HTTPError as exc:
        print(label, "HTTP", exc.code, exc.read().decode("utf-8", "replace")[:180])
    except Exception as exc:
        print(label, type(exc).__name__, str(exc)[:180])
