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
| binary | PCM16 | TTS playback. Valid only after `status.state=speaking`. A new `listen` or `live`/`thinking`/`error`/`radio` aborts leftover audio. |

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

`radio_play` must be HTTP(S) MP3 Icecast. HLS / m3u8 is rejected. Radio and TTS never share the DAC. The gateway probes each candidate before sending `radio_play`; a dead or non-MP3 URL is skipped and the next station is used. HTTP redirects are followed and the final URL is sent, because a 301 with an empty body stops the on-device player. If none work, the device is not started and the user hears that no station was found.

Wake words (when `mode=wake`): «колонка», «слушай», «kolonka», «проснись».
A tap Listen still processes speech without a wake word.

## Timing (Groq adapter)

- Ignore the first ~800 ms (button beep)
- After speech, ~1.2 s of silence ends the turn
- Hard cap ~12 s
