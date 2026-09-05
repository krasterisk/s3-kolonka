import json
import logging
import re
import subprocess
from pathlib import Path

from s3_kolonka_gw.radio import PCM_URI, device_play_cmd

log = logging.getLogger("gw.youtube")

DEFAULTS = {
    "enabled": True,
    "cache_dir": "/var/cache/s3-kolonka-yt",
    "search_limit": 8,
    "search_timeout": 20,
    "ytdlp": "",
    "ffmpeg": "",
}

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")


def normalize_config(cfg=None):
    out = dict(DEFAULTS)
    if cfg:
        out.update({k: v for k, v in cfg.items() if v is not None and v != ""})
    out["search_limit"] = int(out.get("search_limit") or 5)
    out["search_timeout"] = int(out.get("search_timeout") or 20)
    out["enabled"] = bool(out.get("enabled", True))
    out["cache_dir"] = str(out.get("cache_dir") or DEFAULTS["cache_dir"])
    return out


def _which(name, configured=""):
    import sys
    from shutil import which

    if configured:
        return configured
    sibling = Path(sys.executable).parent / name
    if sibling.is_file():
        return str(sibling)
    return which(name) or name


def watch_url(video_id):
    return "https://www.youtube.com/watch?v=%s" % video_id


def is_youtube_source(source):
    raw = (source or "").strip()
    if raw.startswith("yt://"):
        return True
    if "youtube.com/watch" in raw or "youtu.be/" in raw:
        return True
    return False


def video_id_from_source(source):
    raw = (source or "").strip()
    if raw.startswith("yt://"):
        vid = raw[5:].split("?", 1)[0].strip()
        return vid if _ID_RE.match(vid) else ""
    if "youtu.be/" in raw:
        vid = raw.rsplit("youtu.be/", 1)[-1].split("?", 1)[0].split("/", 1)[0]
        return vid if _ID_RE.match(vid) else ""
    if "v=" in raw:
        vid = raw.split("v=", 1)[1].split("&", 1)[0]
        return vid if _ID_RE.match(vid) else ""
    return ""


def cache_path(video_id, cfg):
    cfg = normalize_config(cfg)
    safe = video_id if _ID_RE.match(video_id or "") else "unknown"
    return Path(cfg["cache_dir"]) / safe


_STT_ALIASES = {
    "хром": "хрум",
    "крум": "хрум",
    "chrome": "хрум",
}


def strip_service_words(text):
    q = (text or "").strip()
    q = re.sub(r"^(?:включ(?:и|ить|ай)|поставь|играй|запусти)\s+", "", q, flags=re.I)
    q = re.sub(r"\b(?:с|на)\s+(?:youtube|ютуб[аеу]?)\b", " ", q, flags=re.I)
    q = re.sub(r"\b(?:youtube|ютуб[аеу]?)\b", " ", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip(" \t.!?,…«»\"'")
    if q and _STT_ALIASES:
        pat = re.compile(
            r"\b(%s)\b" % "|".join(re.escape(k) for k in sorted(_STT_ALIASES, key=len, reverse=True)),
            re.I,
        )
        q = pat.sub(lambda m: _STT_ALIASES.get(m.group(0).lower(), m.group(0)), q)
    return q


def query_alternatives(query):
    q = strip_service_words(query)
    if not q:
        return []
    parts = [p.strip(" \t.!?,…") for p in re.split(r"\s+или\s+", q, flags=re.I) if p.strip()]
    out = []
    for part in parts:
        if part and part not in out:
            out.append(part)
    out.sort(key=lambda s: (-len(s), s))
    return out


def query_search_terms(query):
    q = strip_service_words(query)
    if not q:
        return []
    out = [q]
    for part in query_alternatives(q):
        if part and part not in out:
            out.append(part)
    return out


_SHOW_RE = re.compile(
    r"выпуск|\bаудио\b|подкаст|передач|эфир|детск\w*\s+радио",
    re.I,
)
_SONG_RE = re.compile(
    r"\bпесн[яи]|гимн|instrumental|минус\b|ai song|рок-н-ролл|solar125",
    re.I,
)


def title_relevance(title, query):
    raw = title or ""
    tl = raw.lower()
    q = strip_service_words(query).lower()
    score = 0
    if q and q in tl:
        score += 30
    for tok in q.split():
        if len(tok) > 2 and tok in tl:
            score += 4
    if _SHOW_RE.search(raw):
        score += 20
    if _SONG_RE.search(raw):
        score -= 18
    return score


def rank_track_candidates(rows, query, exclude_ids=None):
    skip = set(exclude_ids or [])
    scored = []
    for row in rows or []:
        vid = (row.get("video_id") or "").strip()
        if not vid or vid in skip:
            continue
        scored.append((title_relevance(row.get("title") or "", query), row))
    scored.sort(key=lambda item: (-item[0], item[1].get("title") or ""))
    return [row for _score, row in scored]


def _played_path(cfg):
    cfg = normalize_config(cfg)
    return Path(cfg["cache_dir"]) / "played.json"


def _read_played(cfg):
    path = _played_path(cfg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def remember_played(query, video_id, cfg=None):
    key = strip_service_words(query).lower()
    vid = (video_id or "").strip()
    if not key or not vid:
        return
    data = _read_played(cfg)
    ids = [i for i in (data.get(key) or []) if i != vid]
    ids.append(vid)
    data[key] = ids[-24:]
    data["__last__"] = key
    path = _played_path(cfg)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("played save failed: %s", exc)


def played_ids(query, cfg=None):
    key = strip_service_words(query).lower()
    data = _read_played(cfg)
    return list(data.get(key) or [])


def last_played_query(cfg=None):
    return str(_read_played(cfg).get("__last__") or "").strip()


def parse_search_lines(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        vid, title = line.split("\t", 1)
        vid = vid.strip()
        title = title.strip()
        if not _ID_RE.match(vid):
            continue
        out.append({"video_id": vid, "title": title or vid, "url": "yt://%s" % vid})
    return out


def _ytmusic_rows(rows):
    out = []
    for row in rows or []:
        vid = (row.get("videoId") or "").strip()
        if not _ID_RE.match(vid):
            continue
        artists = ", ".join(
            a.get("name") or "" for a in (row.get("artists") or []) if a.get("name")
        )
        title = (row.get("title") or "").strip() or vid
        if artists:
            title = "%s — %s" % (artists, title)
        out.append({"video_id": vid, "title": title, "url": "yt://%s" % vid})
    return out


def search_ytmusic(query, limit=5, kind="videos"):
    try:
        from ytmusicapi import YTMusic
    except ImportError:
        return []
    client = YTMusic()
    if kind:
        rows = client.search(query, filter=kind, limit=limit) or []
    else:
        rows = client.search(query, limit=limit) or []
    return _ytmusic_rows(rows)


def search_ytdlp(query, cfg, runner=None):
    cfg = normalize_config(cfg)
    ytdlp = _which("yt-dlp", cfg.get("ytdlp") or "")
    cmd = [
        ytdlp,
        "--flat-playlist",
        "--skip-download",
        "--no-warnings",
        "--print",
        "%(id)s\t%(title)s",
        "ytsearch%s:%s" % (cfg["search_limit"], query),
    ]
    run = runner or (lambda c: subprocess.run(
        c, capture_output=True, text=True, timeout=cfg["search_timeout"], check=False
    ))
    try:
        proc = run(cmd)
    except Exception as exc:
        log.warning("yt-dlp search failed: %s", exc)
        return []
    out = parse_search_lines(getattr(proc, "stdout", "") or "")
    if not out:
        err = (getattr(proc, "stderr", "") or "")[:200]
        if err:
            log.warning("yt-dlp search empty: %s", err)
    return out


def search_tracks(query, cfg=None):
    cfg = normalize_config(cfg)
    q = strip_service_words(query)
    if not q:
        return []
    seen = set()
    out = []
    batches = [search_ytdlp(q, cfg)]
    for kind in ("videos", "songs"):
        batches.append(search_ytmusic(q, limit=cfg["search_limit"], kind=kind))
    for rows in batches:
        for row in rows or []:
            vid = (row.get("video_id") or "").strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append(row)
    return out


def iter_track_candidates(query, cfg=None, search_fn=None):
    finder = search_fn or search_tracks
    seen = set()
    for part in query_search_terms(query) or [strip_service_words(query)]:
        if not part:
            continue
        for row in finder(part, cfg) or []:
            vid = (row.get("video_id") or "").strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            item = dict(row)
            item["query"] = part
            yield item


def resolve_track(query, cfg=None, search_fn=None, exclude_ids=None):
    rows = list(iter_track_candidates(query, cfg, search_fn))
    ranked = rank_track_candidates(rows, query, exclude_ids=exclude_ids)
    if ranked:
        return dict(ranked[0])
    if exclude_ids:
        ranked = rank_track_candidates(rows, query)
        if ranked:
            return dict(ranked[0])
    return None


def ytdlp_error_unavailable(err):
    msg = (err or "").lower()
    return any(
        needle in msg
        for needle in (
            "not available",
            "video unavailable",
            "private video",
            "copyright",
        )
    )


def first_playable_track(candidates, download_fn, limit=8):
    for i, row in enumerate(candidates or []):
        if i >= limit:
            break
        try:
            download_fn(row)
        except Exception:
            continue
        return dict(row)
    return None


def device_music_cmd(picked):
    picked = picked or {}
    return device_play_cmd(
        {
            "url": (picked.get("url") or "").strip() or ("yt://%s" % (picked.get("video_id") or "")),
            "title": picked.get("title") or "YouTube",
        }
    )


def ytdlp_download_cmd(source, dest, ytdlp=None):
    watch = watch_url(video_id_from_source(source)) if video_id_from_source(source) else (source or "")
    if not watch:
        raise ValueError("bad youtube source")
    if not dest:
        raise ValueError("bad youtube dest")
    ytdlp = ytdlp or _which("yt-dlp")
    return [
        ytdlp,
        "-f",
        "ba/bestaudio/best",
        "--no-playlist",
        "--no-warnings",
        "--extractor-args",
        "youtube:player_client=android,android_vr,web,default",
        "-o",
        str(dest),
        watch,
    ]


def youtube_pcm_cmds(source, ytdlp=None, ffmpeg=None, sample_rate=16000):
    watch = watch_url(video_id_from_source(source)) if video_id_from_source(source) else (source or "")
    if not watch:
        raise ValueError("bad youtube source")
    ytdlp = ytdlp or _which("yt-dlp")
    ffmpeg = ffmpeg or _which("ffmpeg")
    ytdlp_cmd = ytdlp_download_cmd(source, "-", ytdlp=ytdlp)
    ff_cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    return ytdlp_cmd, ff_cmd


def ffmpeg_file_cmd(path, ffmpeg=None, sample_rate=16000):
    ffmpeg = ffmpeg or _which("ffmpeg")
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]


def cached_file(source, cfg=None):
    cfg = normalize_config(cfg)
    vid = video_id_from_source(source)
    if not vid:
        return None
    path = cache_path(vid, cfg)
    try:
        if path.is_file() and path.stat().st_size > 4096:
            return path
    except OSError:
        return None
    return None


# Keep PCM_URI imported for tests that go through device_play_cmd.
__all__ = [
    "PCM_URI",
    "cached_file",
    "cache_path",
    "device_music_cmd",
    "ffmpeg_file_cmd",
    "first_playable_track",
    "is_youtube_source",
    "iter_track_candidates",
    "last_played_query",
    "normalize_config",
    "parse_search_lines",
    "played_ids",
    "query_search_terms",
    "rank_track_candidates",
    "remember_played",
    "resolve_track",
    "search_tracks",
    "video_id_from_source",
    "watch_url",
    "youtube_pcm_cmds",
    "ytdlp_download_cmd",
    "ytdlp_error_unavailable",
]
