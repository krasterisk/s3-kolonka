import json
import logging
import urllib.parse
import urllib.request

log = logging.getLogger("gw.radio")

DEFAULTS = {
    "provider": "radio-browser",
    "base_url": "https://de1.api.radio-browser.info",
    "user_agent": "s3-kolonka-gw/1.0",
    "codec": "MP3",
    "hide_broken": True,
    "reject_hls": True,
    "bitrate_min": 128,
    "country_hint": "RU",
    "limit": 8,
}

PICKER_PROMPT = (
    "Ты выбираешь интернет-радиостанцию для умной колонки.\n"
    "Каталог: Radio Browser. Играем только MP3 Icecast, не HLS и не AAC.\n"
    "Пользователь сказал: %s\n"
    "Кандидаты (JSON): %s\n"
    "Верни только JSON вида {\"uuid\":\"<stationuuid или null>\",\"title\":\"<имя>\"}.\n"
    "uuid обязан быть из списка. Не выдумывай URL."
)


def normalize_config(cfg=None):
    out = dict(DEFAULTS)
    if cfg:
        out.update({k: v for k, v in cfg.items() if v is not None and v != ""})
    out["base_url"] = str(out["base_url"]).rstrip("/")
    out["codec"] = str(out.get("codec") or "MP3")
    out["limit"] = int(out.get("limit") or 8)
    out["bitrate_min"] = int(out.get("bitrate_min") or 0)
    out["hide_broken"] = bool(out.get("hide_broken", True))
    out["reject_hls"] = bool(out.get("reject_hls", True))
    out["country_hint"] = str(out.get("country_hint") or "").upper()
    out["user_agent"] = str(out.get("user_agent") or DEFAULTS["user_agent"])
    return out


def search_url(cfg, query):
    cfg = normalize_config(cfg)
    params = {
        "name": query or "",
        "codec": cfg["codec"],
        "hidebroken": "true" if cfg["hide_broken"] else "false",
        "order": "votes",
        "reverse": "true",
        "limit": str(cfg["limit"] * 3),
    }
    if cfg["country_hint"]:
        params["countrycode"] = cfg["country_hint"]
    return cfg["base_url"] + "/json/stations/search?" + urllib.parse.urlencode(params)


def click_url(cfg, uuid):
    cfg = normalize_config(cfg)
    return cfg["base_url"] + "/json/url/" + urllib.parse.quote(uuid)


def filter_stations(raw, cfg):
    cfg = normalize_config(cfg)
    want = (cfg["codec"] or "MP3").upper()
    out = []
    for row in raw or []:
        codec = str(row.get("codec") or "").upper()
        url = (row.get("url_resolved") or row.get("url") or "").strip()
        uuid = (row.get("stationuuid") or row.get("uuid") or "").strip()
        if not uuid or not url:
            continue
        if cfg["reject_hls"] and int(row.get("hls") or 0):
            continue
        if want and codec != want:
            continue
        bitrate = int(row.get("bitrate") or 0)
        if bitrate > 0 and bitrate < cfg["bitrate_min"]:
            continue
        if ".m3u8" in url.lower() or url.lower().endswith(".m3u"):
            continue
        out.append(
            {
                "uuid": uuid,
                "name": (row.get("name") or "").strip() or uuid,
                "url": url,
                "codec": codec,
                "bitrate": bitrate,
                "countrycode": (row.get("countrycode") or "").strip(),
            }
        )
        if len(out) >= cfg["limit"]:
            break
    return out


def parse_picker_reply(text, candidates):
    by_uuid = {c["uuid"]: c for c in candidates or []}
    if not text or not by_uuid:
        return None
    raw = text.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    uuid = (payload.get("uuid") or "").strip()
    if not uuid or uuid not in by_uuid:
        return None
    chosen = dict(by_uuid[uuid])
    title = (payload.get("title") or chosen["name"]).strip()
    chosen["title"] = title
    return chosen


def fetch_json(url, cfg, opener=None):
    cfg = normalize_config(cfg)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": cfg["user_agent"], "Accept": "application/json"},
        method="GET",
    )
    handle = opener or urllib.request.build_opener()
    with handle.open(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_stations(query, cfg, opener=None):
    return fetch_json(search_url(cfg, query), cfg, opener=opener)


def resolve_click(uuid, cfg, opener=None):
    try:
        payload = fetch_json(click_url(cfg, uuid), cfg, opener=opener)
    except Exception as exc:
        log.warning("radio click failed: %s", exc)
        return None
    url = (payload.get("url_resolved") or payload.get("url") or "").strip()
    return url or None


def resolve_station(query, cfg, search_fn=None, picker_fn=None, opener=None):
    cfg = normalize_config(cfg)
    if search_fn:
        raw = search_fn(query, cfg)
    else:
        raw = search_stations(query, cfg, opener=opener)
    cands = filter_stations(raw, cfg)
    if not cands:
        return None
    if picker_fn:
        picked = parse_picker_reply(picker_fn(query, cands), cands)
    else:
        picked = cands[0]
        picked = dict(picked)
        picked["title"] = picked.get("name")
    if not picked:
        return None
    clicked = resolve_click(picked["uuid"], cfg, opener=opener) if search_fn is None else None
    if clicked:
        picked["url"] = clicked
    return picked
