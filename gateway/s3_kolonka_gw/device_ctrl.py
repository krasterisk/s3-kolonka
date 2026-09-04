import re

from s3_kolonka_gw import radio

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
                "Play an internet radio station by spoken name or style, "
                "for example Европа Плюс or jazz radio. Search happens on the server."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Station name or genre as the user said it.",
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
            "description": "Stop internet radio playback.",
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

    if re.search(r"выключи\s+радио|стоп\s+радио|останови\s+радио", t):
        cmds.append({"name": "radio_stop"})

    if re.search(r"включись|проснись|очнись|включи\s+экран", t):
        cmds.append({"name": "power_on"})
    elif re.search(r"выключись|усни|спи$|спать|погаси", t):
        cmds.append({"name": "power_off"})
    return cmds


_RADIO_STOP = re.compile(
    r"выключи\s+радио|стоп\s+радио|останови\s+радио|выруби\s+радио"
)
_RADIO_PLAY = re.compile(
    r"(?:включ(?:и|ить|ай)|поставь|играй|запусти)\s+радио(?:\s+(.+))?",
    re.IGNORECASE | re.DOTALL,
)


def radio_play_query(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if _RADIO_STOP.search(low):
        return None
    m = _RADIO_PLAY.search(low)
    if not m:
        return None
    return (m.group(1) or "").strip(" \t.!?,…")


def attach_radio_play(cmds: list[dict], user_text: str, pick_fn) -> tuple[list[dict], str | None]:
    cmds = list(cmds or [])
    if any(c.get("name") == "radio_play" for c in cmds):
        return cmds, None
    query = radio_play_query(user_text)
    if query is None:
        return cmds, None
    picked = pick_fn(query or user_text)
    if not picked or not picked.get("url"):
        return cmds, "Не нашла станцию."
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
