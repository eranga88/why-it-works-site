#!/usr/bin/env python3
"""Pull the latest videos from the YouTube channel into data/videos.json.

Runs on a schedule in GitHub Actions (see .github/workflows/update-videos.yml).
Uses only the Python standard library and YouTube's public RSS feed, so no
API key is needed.

    python scripts/update_videos.py

Optional: set a YOUTUBE_API_KEY environment variable (or repository secret)
to pull the channel's FULL upload history through the official YouTube Data API.

The feed only lists the newest 15 uploads, so each run MERGES into the
existing file instead of replacing it. Videos are never dropped, which means
the list keeps growing as long as the job runs at least once every 15 uploads.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CHANNEL_ID = "UCqCqSKPXFDCm9wZlIKk3stQ"
CHANNEL_HANDLE = "HeresWhyItWorks"
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
OUT = Path(__file__).resolve().parent.parent / "data" / "videos.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}

# Topic buckets match the sections in the channel's About text.
TOPICS = [
    ("phone", "Phone tips", r"iphone|android|\bphones?\b|battery|charg|imessage|\bios\b|samsung|pixel|whatsapp|storage|apple|appletips"),
    ("security", "Security", r"scam|passkey|password|privacy|hack|secur|phish|theft|stolen|2fa|spy|malware|virus"),
    ("ai", "AI tools", r"\bai\b|chatgpt|gemini|claude|copilot|artificial intelligence|nvidia|\bllm"),
    ("space", "Science & space", r"space|nasa|rocket|mars|moon|planet|voyager|satellite|physics|science|time travel|earthquake|beach|ocean|gravity|universe"),
    ("budget", "Budget tech", r"budget|cheap|money|saving|deal|worth buying|upgrade|trade.in|value"),
    ("how", "How it works", r".*"),  # fallback: everyday tech explained
]


def fetch(url: str, data: bytes | None = None, headers: dict | None = None) -> str:
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return ""


def split_title(raw: str) -> tuple[str, list[str]]:
    """'Why passkeys matter #privacy #tech' -> ('Why passkeys matter', ['privacy', 'tech'])"""
    tags = re.findall(r"#([\w-]+)", raw)
    title = re.sub(r"\s*#[\w-]+", "", raw).strip(" -|")
    return (title or raw.strip()), [t.lower() for t in tags if t.lower() not in ("shorts", "short")]


def classify(title: str, tags: list[str], description: str) -> str:
    """Pick a topic from the title and hashtags; fall back to the description's first lines."""
    for text in (" ".join([title, *tags]), description[:200]):
        text = text.lower()
        for key, _label, pattern in TOPICS[:-1]:
            if re.search(pattern, text):
                return key
    return TOPICS[-1][0]


def slugify(title: str) -> str:
    """'Why rockets don't need air to fly' -> 'why-rockets-dont-need-air-to-fly'"""
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"['\u2019]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > 60:
        text = text[:60].rsplit("-", 1)[0]
    return text


def assign_slugs(videos: dict[str, dict]) -> None:
    """Give every video a page address. Once set, a slug never changes (so links never break)."""
    used = {v["slug"] for v in videos.values() if v.get("slug")}
    for v in sorted(videos.values(), key=lambda v: v.get("published", "")):
        if v.get("slug"):
            continue
        slug = slugify(v["title"]) or v["id"].lower()
        if slug in used:
            slug = f"{slug}-{v['id'][:6].lower()}"
        v["slug"] = slug
        used.add(slug)


def make_video(vid: str, raw_title: str, published: str, description: str, is_short: bool,
               views: int | None = None) -> dict:
    title, tags = split_title(raw_title)
    return {
        "id": vid,
        "title": title,
        "tags": tags,
        "published": published,
        "description": description.strip(),
        "type": "short" if is_short else "video",
        "topic": classify(title, tags, description),
        "views": views,
        "url": f"https://www.youtube.com/{'shorts/' + vid if is_short else 'watch?v=' + vid}",
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
    }


def from_feed() -> dict[str, dict]:
    root = ET.fromstring(fetch(FEED_URL))
    out = {}
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        link = e.find("a:link", NS).get("href", "")
        stats = e.find("media:group/media:community/media:statistics", NS)
        out[vid] = make_video(
            vid,
            e.findtext("a:title", namespaces=NS) or "",
            e.findtext("a:published", namespaces=NS) or "",
            e.findtext("media:group/media:description", default="", namespaces=NS),
            "/shorts/" in link,
            int(stats.get("views")) if stats is not None and stats.get("views") else None,
        )
    return out


# ---------- full history via the official YouTube Data API (optional) ----------

def from_api(api_key: str) -> dict[str, dict]:
    """Every upload, using the official YouTube Data API v3 (free key from Google Cloud)."""
    base = "https://www.googleapis.com/youtube/v3"
    uploads = "UU" + CHANNEL_ID[2:]  # the channel's "uploads" playlist
    ids, page = [], ""
    while True:
        q = f"{base}/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads}&key={api_key}"
        data = json.loads(fetch(q + (f"&pageToken={page}" if page else "")))
        ids += [i["contentDetails"]["videoId"] for i in data.get("items", [])]
        page = data.get("nextPageToken")
        if not page:
            break
    out = {}
    for n in range(0, len(ids), 50):
        chunk = ",".join(ids[n:n + 50])
        data = json.loads(fetch(f"{base}/videos?part=snippet,contentDetails,statistics&id={chunk}&key={api_key}"))
        for it in data.get("items", []):
            sn, cd = it["snippet"], it["contentDetails"]
            m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", cd.get("duration", ""))
            secs = sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0
            raw = sn.get("title", "")
            is_short = secs <= 180 and ("#shorts" in (raw + sn.get("description", "")).lower() or secs <= 60)
            views = it.get("statistics", {}).get("viewCount")
            out[it["id"]] = make_video(it["id"], raw, sn.get("publishedAt", ""), sn.get("description", ""),
                                       is_short, int(views) if views else None)
            if secs:
                out[it["id"]]["duration"] = secs  # seconds; used in the video sitemap / structured data
    return out


def main() -> int:
    existing: dict[str, dict] = {}
    if OUT.exists():
        existing = {v["id"]: v for v in json.loads(OUT.read_text())["videos"]}

    latest = from_feed()
    merged = dict(existing)
    for vid, v in latest.items():
        merged[vid] = {**existing.get(vid, {}), **v}

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if api_key:
        try:
            for vid, v in from_api(api_key).items():
                if vid in merged and merged[vid].get("type") == "short":
                    v["type"], v["url"] = "short", merged[vid]["url"]  # the feed knows Shorts for sure
                merged[vid] = {**merged.get(vid, {}), **v}
        except Exception as exc:  # the RSS result is still good; don't fail the run
            print(f"YouTube Data API step skipped: {exc}")

    # keep hand-edited topics: set "topic_locked": true next to "topic" in the JSON
    for vid, old in existing.items():
        if old.get("topic_locked"):
            merged[vid]["topic"], merged[vid]["topic_locked"] = old["topic"], True

    assign_slugs(merged)
    videos = sorted(merged.values(), key=lambda v: v.get("published", ""), reverse=True)
    payload = {
        "channel": {
            "id": CHANNEL_ID,
            "handle": CHANNEL_HANDLE,
            "url": f"https://www.youtube.com/@{CHANNEL_HANDLE}",
            "subscribe_url": f"https://www.youtube.com/@{CHANNEL_HANDLE}?sub_confirmation=1",
        },
        "topics": [{"key": k, "label": l} for k, l, _ in TOPICS],
        "count": len(videos),
        "videos": videos,
    }

    old = OUT.read_text() if OUT.exists() else ""
    old_videos = json.loads(old)["videos"] if old else None
    if old_videos == videos:
        print(f"No changes ({len(videos)} videos).")
        return 0
    payload["updated"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(videos)} videos ({len(videos) - len(existing)} new) to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
