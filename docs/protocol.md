# Voice protocol

The speaker is a WebSocket client. The gateway is the server.

- URL: `ws://<host>:<port>/` (default port **8765**)
- Text frames: JSON
- Binary frames: PCM16 little-endian, mono, 16 kHz

Do not bind **8123**, **1900**, or **5353** (Home Assistant / discovery).

## Messages (speaker → gateway)

| `type` | Meaning |
| --- | --- |
| `hello` | Optional greet. Body may include `device`. |
| `listen` | Start capturing a turn. |
| `stop` | End the turn and run STT → LLM → TTS. |

After `listen`, the speaker streams binary PCM until `stop` or the gateway
ends the turn (silence / max length).

## Messages (gateway → speaker)

| `type` | Fields | Meaning |
| --- | --- | --- |
| `hello` | `backend`, `sample_rate` | Connection accepted. |
| `status` | `state`, `detail` | UI state. |
| binary | PCM16 | TTS playback. |

### `status.state`

| State | Speaker UI |
| --- | --- |
| `idle` | `Brain: <backend>` (for Groq: `Brain: groq`) |
| `live` | Listening |
| `thinking` | STT / LLM in progress |
| `speaking` | Playing TTS |
| `error` | Failed turn |

`thinking`, `speaking`, `idle`, and `error` end the listen UI on the device.

## Timing (Groq adapter)

- Ignore the first ~800 ms (button beep)
- After speech, ~1.2 s of silence ends the turn
- Hard cap ~12 s
