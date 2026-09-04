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
| `listen` | Start a turn. Optional `mode`: `tap` (process any speech) or `wake` (require wake word). |
| `stop` | End the turn and run STT → LLM → TTS. |

After `listen`, the speaker streams binary PCM until `stop` or the gateway
ends the turn (silence / max length).

## Messages (gateway → speaker)

| `type` | Fields | Meaning |
| --- | --- | --- |
| `hello` | `backend`, `sample_rate` | Connection accepted. |
| `status` | `state`, `detail`, optional `heard`, `reply` | UI state. `heard` is the recognized phrase, `reply` is the spoken answer. |
| `cmd` | `name`, `value`, optional `url`, `title` | Device control: `volume`, `brightness`, `power_off`, `power_on`, `radio_play`, `radio_stop`. |
| binary | PCM16 | TTS or radio PCM. Valid after `status.state=speaking` or `radio`. A new `listen` or `live`/`thinking`/`error` aborts leftover audio. |

### `status.state`

| State | Speaker UI |
| --- | --- |
| `idle` | `Brain: <backend>` (for Groq: `Brain: groq`) |
| `live` | Listening |
| `thinking` | STT / LLM in progress |
| `speaking` | Playing TTS |
| `error` | Failed turn |
| `radio` | Playing Icecast MP3; `reply` is the station title |

`thinking`, `speaking`, `idle`, `radio`, and `error` end the listen UI on the device.

`radio_play` must be HTTP(S) MP3 Icecast. HLS / m3u8 is rejected. Radio and TTS never share the DAC. The gateway probes each candidate, follows HTTP redirects, then decodes the Icecast stream to PCM16 mono 16 kHz and sends it as binary frames. `radio_play` uses `url=pcm://` so the speaker does not open Icecast itself. A device `radio_stop` text frame stops the relay. If no station works, the device is not started and the user hears that no station was found.

Wake words (when `mode=wake`): «колонка», «слушай», «kolonka», «проснись».
A tap Listen still processes speech without a wake word.

## Timing (Groq adapter)

- Ignore the first ~800 ms (button beep)
- After speech, ~1.2 s of silence ends the turn
- Hard cap ~12 s
