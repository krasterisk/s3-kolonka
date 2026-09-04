import json
import logging
import urllib.error
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


_AUDIO_EXT = (".mp3", ".aac", ".wav", ".flac", ".m4a", ".amr", ".opus")


def player_uri(url):
    raw = (url or "").strip()
    if not raw:
        return raw
    no_frag = raw.split("#", 1)[0]
    path = urllib.parse.urlparse(no_frag).path or ""
    lower = path.lower()
    if any(lower.endswith(ext) for ext in _AUDIO_EXT):
        return raw
    if raw.endswith("#stream.mp3"):
        return raw
    return raw + "#stream.mp3"


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


def looks_like_mp3(body, content_type=""):
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if ctype in ("text/html", "text/plain", "application/json", "application/xml"):
        return False
    data = body or b""
    if data.startswith(b"ID3"):
        return True
    window = data[:64]
    for i in range(0, max(0, len(window) - 1)):
        if window[i] == 0xFF and (window[i + 1] & 0xE0) == 0xE0:
            return True
    if ctype.startswith("audio/"):
        return True
    return False


def probe_stream(url, cfg, opener=None, timeout=8):
    """Return the playable URL after redirects, or None if the stream is dead."""
    cfg = normalize_config(cfg)
    raw = (url or "").split("#", 1)[0].strip()
    if not raw:
        return None
    req = urllib.request.Request(
        raw,
        headers={
            "User-Agent": cfg["user_agent"],
            "Accept": "*/*",
            "Icy-MetaData": "0",
        },
        method="GET",
    )
    handle = opener or urllib.request.build_opener()
    final = raw
    try:
        with handle.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                log.warning("radio probe HTTP %s %s", status, raw)
                return None
            headers = getattr(resp, "headers", None)
            ctype = _header(headers, "Content-Type")
            body = resp.read(2048)
            if hasattr(resp, "geturl"):
                final = (resp.geturl() or raw).split("#", 1)[0].strip() or raw
    except urllib.error.HTTPError as exc:
        log.warning("radio probe HTTP %s %s", exc.code, raw)
        return None
    except Exception as exc:
        log.warning("radio probe fail %s: %s", raw, exc)
        return None
    if _icy_alive(headers) or looks_like_mp3(body, ctype):
        if final != raw:
            log.info("radio probe redirect %s -> %s", raw, final)
        return final
    log.warning("radio probe not mp3 %s ctype=%s", raw, ctype)
    return None


def _header(headers, name):
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    return (
        getter(name)
        or getter(name.lower())
        or getter(name.title())
        or ""
    )


def _icy_alive(headers):
    return bool(
        _header(headers, "icy-name")
        or _header(headers, "icy-metaint")
        or _header(headers, "icy-br")
        or _header(headers, "ice-audio-info")
    )


def resolve_station(query, cfg, search_fn=None, picker_fn=None, opener=None, probe_fn=None):
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
        picked = dict(cands[0])
        picked["title"] = picked.get("name")
    if not picked:
        return None
    ordered = [picked] + [c for c in cands if c["uuid"] != picked["uuid"]]
    probe = probe_fn if probe_fn is not None else (lambda u: probe_stream(u, cfg, opener=opener))
    for cand in ordered:
        url = cand.get("url") or ""
        if search_fn is None:
            clicked = resolve_click(cand["uuid"], cfg, opener=opener)
            if clicked:
                url = clicked
        url = player_uri(url)
        if not url:
            continue
        probed = probe(url)
        if not probed:
            log.warning("radio skip dead %s %s", cand.get("name"), url)
            continue
        if probed is not True:
            url = player_uri(str(probed))
        out = dict(cand)
        out["url"] = url
        if cand["uuid"] == picked["uuid"]:
            out["title"] = picked.get("title") or out.get("name")
        else:
            out["title"] = out.get("name") or picked.get("title")
            log.info("radio fallback %s -> %s", picked.get("name"), out["title"])
        log.info("radio use %s %s", out.get("title"), url)
        return out
    return None
