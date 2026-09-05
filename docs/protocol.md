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
`live`, `idle`, and `radio` clear leftover Home `heard` / `reply` text. The station title is shown on Media only.

`radio_play` uses `url=pcm://` so the speaker never opens Icecast or YouTube itself. For radio the gateway probes MP3 Icecast, follows redirects, and decodes to PCM16 mono 16 kHz. For a song the gateway searches YouTube Music on the server, extracts audio with yt-dlp, and decodes the same PCM path. HLS / m3u8 Icecast is rejected. Radio, YouTube audio, and TTS never share the DAC. A device `radio_stop` text frame stops the relay. Radio search is by name, aliases, and genre tags. If nothing close is found, the device is not started and the user is asked to clarify.

Wake words (when `mode=wake`): «колонка», «слушай», «kolonka», «проснись».
A tap Listen still processes speech without a wake word.

## Timing (Groq adapter)

- Ignore the first ~800 ms (button beep)
- After speech, ~2.5 s of silence ends the turn
- Hard cap ~12 s
