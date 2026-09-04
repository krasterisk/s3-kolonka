import re

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

    if re.search(r"включись|проснись|очнись|включи\s+экран", t):
        cmds.append({"name": "power_on"})
    elif re.search(r"выключись|усни|спи$|спать|погаси", t):
        cmds.append({"name": "power_off"})
    return cmds


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
    return "Готово."
