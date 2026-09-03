#!/bin/bash
set -e
GW=/opt/s3-kolonka-gw
VOICE_DIR="$GW/voices"
mkdir -p "$VOICE_DIR"
"$GW/.venv/bin/pip" install -q piper-tts
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium"
if [ ! -s "$VOICE_DIR/ru_RU-irina-medium.onnx" ]; then
  curl -fsSL "$BASE/ru_RU-irina-medium.onnx?download=true" -o "$VOICE_DIR/ru_RU-irina-medium.onnx"
fi
if [ ! -s "$VOICE_DIR/ru_RU-irina-medium.onnx.json" ]; then
  curl -fsSL "$BASE/ru_RU-irina-medium.onnx.json?download=true" -o "$VOICE_DIR/ru_RU-irina-medium.onnx.json"
fi
ls -lh "$VOICE_DIR"
"$GW/.venv/bin/piper" --help | head -n 3
echo "Привет, я Ирина" | "$GW/.venv/bin/piper" --model "$VOICE_DIR/ru_RU-irina-medium.onnx" --output_file /tmp/piper-test.wav
stat -c "wav=%s" /tmp/piper-test.wav
