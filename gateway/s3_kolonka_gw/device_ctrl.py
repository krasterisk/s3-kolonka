import re

from s3_kolonka_gw import radio
from s3_kolonka_gw import youtube

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set speaker volume from 0 to 100.",
            "parameters": {
                "type": "object",
                "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
                "required": ["percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_volume",
            "description": "Change volume by a delta, for example -20 or 15.",
            "parameters": {
                "type": "object",
                "properties": {"delta": {"type": "integer", "minimum": -100, "maximum": 100}},
                "required": ["delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_brightness",
            "description": "Set screen backlight from 5 to 100.",
            "parameters": {
                "type": "object",
                "properties": {"percent": {"type": "integer", "minimum": 5, "maximum": 100}},
                "required": ["percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_brightness",
            "description": "Change backlight by a delta.",
            "parameters": {
                "type": "object",
                "properties": {"delta": {"type": "integer", "minimum": -100, "maximum": 100}},
                "required": ["delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_off",
            "description": "Sleep: turn the screen off. Wake word can turn it back on.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_on",
            "description": "Wake the speaker and restore the screen.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_radio",
            "description": (
                "Play internet radio. Call only when the user said the word "
                "«радио» (включи радио Европа Плюс, радио рок). "
                "The server finds a close match or asks to clarify. "
                "Do not invent station names or stream URLs. "
                "Without the word радио use play_music."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Station name or genre as spoken, not a URL.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": (
                "Play a song, artist, cartoon, podcast, or YouTube clip by spoken name "
                "(Кино Группа крови, хрум или сказочный детектив). "
                "Default for включи/поставь when the user did not say радио. "
                "другой / следующий / не то — next clip of the same show, not a new search. "
                "The server searches YouTube and streams audio only. "
                "Do not invent video IDs or URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Song, artist, or clip as spoken, not a URL.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_radio",
            "description": "Stop radio or YouTube music playback.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def apply_tool(name: str, args: dict, vol: int, bl: int) -> tuple[list[dict], int, int]:
    cmds = []
    if name == "set_volume":
        vol = clamp(args.get("percent", vol), 0, 100)
        cmds.append({"name": "volume", "value": vol})
    elif name == "adjust_volume":
        vol = clamp(vol + int(args.get("delta") or 0), 0, 100)
        cmds.append({"name": "volume", "value": vol})
    elif name == "set_brightness":
        bl = clamp(args.get("percent", bl), 5, 100)
        cmds.append({"name": "brightness", "value": bl})
    elif name == "adjust_brightness":
        bl = clamp(bl + int(args.get("delta") or 0), 5, 100)
        cmds.append({"name": "brightness", "value": bl})
    elif name == "power_off":
        cmds.append({"name": "power_off"})
    elif name == "power_on":
        cmds.append({"name": "power_on"})
    elif name == "stop_radio":
        cmds.append({"name": "radio_stop"})
    return cmds, vol, bl


def heuristic_commands(text: str, vol: int, bl: int) -> list[dict]:
    t = (text or "").lower()
    cmds = []
    if re.search(r"выключи\s+звук|без\s+звука|мут", t):
        vol = 0
        cmds.append({"name": "volume", "value": vol})
    elif re.search(r"громче|погромче|прибавь", t):
        vol = clamp(vol + 20, 0, 100)
        cmds.append({"name": "volume", "value": vol})
    elif re.search(r"тише|потише|убавь", t):
        vol = clamp(vol - 20, 0, 100)
        cmds.append({"name": "volume", "value": vol})
    elif re.search(r"максимум|на полную", t):
        vol = 100
        cmds.append({"name": "volume", "value": vol})

    if re.search(r"ярче|поярче", t):
        bl = clamp(bl + 20, 5, 100)
        cmds.append({"name": "brightness", "value": bl})
    elif re.search(r"темнее|потемнее|приглуши", t):
        bl = clamp(bl - 20, 5, 100)
        cmds.append({"name": "brightness", "value": bl})

    if re.search(
        r"выключи\s+радио|стоп\s+радио|останови\s+радио|выключи\s+музык|"
        r"стоп\s+музык|останови\s+песн|выключи\s+песн",
        t,
    ):
        cmds.append({"name": "radio_stop"})

    if re.search(r"включись|проснись|очнись|включи\s+экран", t):
        cmds.append({"name": "power_on"})
    elif re.search(r"выключись|усни|спи$|спать|погаси", t):
        cmds.append({"name": "power_off"})
    return cmds


_RADIO_STOP = re.compile(
    r"выключи\s+радио|стоп\s+радио|останови\s+радио|выруби\s+радио|"
    r"выключи\s+музык|стоп\s+музык|останови\s+песн|выключи\s+песн"
)
_PLAY = re.compile(
    r"(?:включ(?:и|ить|ай)|поставь|играй|запусти)\s+(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_RADIO_PLAY = re.compile(
    r"(?:включ(?:и|ить|ай)|поставь|играй|запусти)\s+(?:радио\s*)?(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_HAS_YOUTUBE = re.compile(r"youtube|ютуб", re.IGNORECASE)
_MUSIC_LEAD = re.compile(
    r"^(?:(?:с|на)\s+)?(?:песн[ауию]|трек|клип|музык[ауи]|ютуб[аеу]?|youtube)\b",
    re.IGNORECASE,
)
_STRIP_MUSIC_LEAD = re.compile(
    r"^(?:песн[ауию]|трек|клип|музык[ауи])\s+",
    re.IGNORECASE,
)
_NOT_STATION = re.compile(
    r"^(экран|колонк|звук|микрофон|себя|свет|яркост|громкост)"
)
_ONLY_NEXT = re.compile(
    r"^(?:следующ\w*|друг(?:ой|ая|ое|ую|ие)|ещё|еще|смени|измени|"
    r"не\s+то|не\s+это|дальше|next)"
    r"(?:\s+(?:один|раз|выпуск|сери\w*|трек|песн\w*))?$",
    re.IGNORECASE,
)


def radio_play_query(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if _RADIO_STOP.search(low):
        return None
    if "радио" not in low:
        return None
    if _HAS_YOUTUBE.search(low):
        return None
    obj_m = _PLAY.search(low)
    if obj_m and _MUSIC_LEAD.search((obj_m.group(1) or "").strip()):
        return None
    m = _RADIO_PLAY.search(low)
    if not m:
        return None
    query = (m.group(1) or "").strip(" \t.!?,…«»\"'")
    if _NOT_STATION.search(query):
        return None
    return query


def music_play_query(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if _RADIO_STOP.search(low):
        return None
    if radio_play_query(t) is not None:
        return None
    m = _PLAY.search(low)
    if not m:
        return None
    query = youtube.strip_service_words(m.group(1) or "")
    query = _STRIP_MUSIC_LEAD.sub("", query).strip()
    if _NOT_STATION.search(query):
        return None
    if music_next_intent(query):
        return None
    return query or None


def music_next_intent(text: str) -> bool:
    t = youtube.strip_service_words(text) or (text or "").strip()
    t = re.sub(r"^(?:поставь|играй|запусти)\s+", "", t, flags=re.I).strip()
    return bool(t and _ONLY_NEXT.match(t))


def attach_music_play(
    cmds: list[dict], user_text: str, pick_fn, last_query: str = ""
) -> tuple[list[dict], str | None]:
    cmds = list(cmds or [])
    if any(c.get("name") == "radio_play" for c in cmds):
        return cmds, None
    query = music_play_query(user_text)
    if query is None and music_next_intent(user_text):
        query = (last_query or "").strip()
        if not query:
            return cmds, "Сначала включите передачу или песню."
    if query is None:
        return cmds, None
    picked = pick_fn(query or user_text)
    if not picked or not (picked.get("url") or picked.get("video_id")):
        return cmds, "Не нашла трек. Назовите песню или исполнителя."
    cmds.append(youtube.device_music_cmd(picked))
    return cmds, None


def attach_radio_play(cmds: list[dict], user_text: str, pick_fn) -> tuple[list[dict], str | None]:
    cmds = list(cmds or [])
    if any(c.get("name") == "radio_play" for c in cmds):
        return cmds, None
    query = radio_play_query(user_text)
    if query is None:
        return cmds, None
    picked = pick_fn(query or user_text)
    if picked and picked.get("clarify"):
        return cmds, picked["clarify"]
    if not picked or not picked.get("url"):
        return cmds, "Не нашла станцию. Назовите название или жанр."
    cmds.append(radio.device_play_cmd(picked))
    return cmds, None


def spoken_ack(cmds: list[dict]) -> str:
    if not cmds:
        return ""
    last = cmds[-1]
    name = last.get("name")
    value = last.get("value")
    if name == "volume":
        return "Громкость %s." % value
    if name == "brightness":
        return "Яркость %s." % value
    if name == "power_off":
        return "Выключаюсь."
    if name == "power_on":
        return "Включилась."
    if name == "radio_stop":
        return "Радио выключено."
    if name == "radio_play":
        return "Включаю %s." % (last.get("title") or "радио")
    return "Готово."
