#!/usr/bin/env python3
"""Build the static, search-engine-friendly website from data/videos.json into _site/.

    SITE_URL=https://example.github.io/why-it-works-site python scripts/build_site.py

Every page is plain HTML (no JavaScript needed to see the content), with:
  * one page per video  -> /videos/<slug>/   (VideoObject + BreadcrumbList structured data)
  * one page per topic  -> /topics/<key>/
  * sitemap.xml with Google video-sitemap entries, robots.txt, 404.html
  * canonical links, Open Graph / Twitter cards on every page
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
DATA = json.loads((ROOT / "data" / "videos.json").read_text())

SITE_URL = os.environ.get("SITE_URL", "http://localhost:8765").rstrip("/")
BASE = urlparse(SITE_URL).path.rstrip("/")          # "/why-it-works-site" on a project site, "" on a custom domain
SITE_NAME = "Why It Works"
TAGLINE = "Everyday tech, explained step by step"
SITE_DESC = ("Phone tips, security settings, free AI tools and how the tech around you actually works, "
             "explained in short, no-fluff videos.")
CHANNEL = DATA["channel"]
LOGO = f"{SITE_URL}/assets/logo.jpg"

TOPIC_INTROS = {
    "phone": ("Phone tips for iPhone and Android",
              "Hidden settings, battery fixes, storage clean-ups and the features most people never find. "
              "Each video shows you one thing you can change on your phone right now."),
    "security": ("Phone and online security, explained",
                 "How scams work, why passkeys beat passwords, and the settings that keep your accounts, data "
                 "and phone safe. Practical steps, no jargon."),
    "ai": ("Free AI tools and AI news, explained",
           "The AI tools you can use today for free, tested and explained, plus the stories behind the AI "
           "companies and chips everyone is talking about."),
    "space": ("Science and space, explained simply",
              "Rockets, Mars, Voyager, earthquakes and the physics of everyday life. Short explainers on the "
              "science behind the headlines and the world around you."),
    "budget": ("Budget tech and getting value from your gadgets",
               "What's worth buying, when to upgrade, and how to get the most money back for your old devices "
               "without overspending."),
    "how": ("How everyday tech actually works",
            "Wi-Fi, GPS, outages, apps and the systems behind the gadgets you use every day, explained step by step."),
}

e = lambda s: html.escape(str(s or ""), quote=True)
videos = DATA["videos"]
topics = [t for t in DATA["topics"] if any(v["topic"] == t["key"] for v in videos)]
topic_label = {t["key"]: t["label"] for t in DATA["topics"]}


# ---------------------------------------------------------------- helpers

def url(path: str = "/") -> str:
    """Site-relative link that works on a GitHub project site and on a custom domain."""
    return f"{BASE}{path}"


def abs_url(path: str = "/") -> str:
    return f"{SITE_URL}{path}"


def vpath(v) -> str:
    return f"/videos/{v['slug']}/"


def dt(v) -> datetime:
    try:
        return datetime.fromisoformat(v["published"])
    except (KeyError, ValueError):
        return datetime.now(timezone.utc)


def nice_date(v) -> str:
    d = dt(v)
    return f"{d.day} {d:%b %Y}"


def fmt_views(n) -> str:
    if n is None:
        return ""
    if n >= 1_000_000:
        s = f"{n / 1e6:.1f}".rstrip("0").rstrip(".") + "M"
    elif n >= 1000:
        s = f"{n / 1e3:.1f}".rstrip("0").rstrip(".") + "K"
    else:
        s = str(n)
    return f"{s} view{'' if n == 1 else 's'}"


def iso_duration(secs: int) -> str:
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return "PT" + (f"{h}H" if h else "") + (f"{m}M" if m else "") + f"{s}S"


def clean_desc(text: str) -> str:
    """Description without hashtag-only lines, for meta descriptions."""
    lines = [l for l in text.splitlines() if l.strip() and not re.fullmatch(r"(\s*#[\w-]+)+\s*", l)]
    return " ".join(" ".join(lines).split())


def meta_desc(v) -> str:
    d = clean_desc(v.get("description", ""))
    if not d:
        d = f"{v['title']}. A short {topic_label.get(v['topic'], 'tech').lower()} explainer from {SITE_NAME}."
    if len(d) > 158:
        d = d[:155].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return d


def thumb(v, quality="hqdefault") -> str:
    return f"https://i.ytimg.com/vi/{v['id']}/{quality}.jpg"


def linkify(text: str) -> str:
    out = e(text)
    out = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" rel="nofollow noopener" target="_blank">\1</a>', out)
    return out


def paragraphs(text: str) -> str:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    blocks = [b for b in blocks if not re.fullmatch(r"(\s*#[\w-]+)+\s*", b)]
    return "\n".join(f"<p>{linkify(b).replace(chr(10), '<br>')}</p>" for b in blocks)


def jsonld(obj) -> str:
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
            + "</script>")


def video_schema(v, page_url: str) -> dict:
    d = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": v["title"],
        "description": clean_desc(v.get("description", "")) or v["title"],
        "thumbnailUrl": [thumb(v, "maxresdefault"), thumb(v, "hqdefault")],
        "uploadDate": v["published"],
        "embedUrl": f"https://www.youtube.com/embed/{v['id']}",
        "contentUrl": v["url"],
        "url": page_url,
        "inLanguage": "en",
        "publisher": {"@type": "Organization", "name": SITE_NAME, "logo": {"@type": "ImageObject", "url": LOGO}},
    }
    if v.get("tags"):
        d["keywords"] = ", ".join(v["tags"])
    if v.get("duration"):
        d["duration"] = iso_duration(v["duration"])
    if v.get("views") is not None:
        d["interactionStatistic"] = {
            "@type": "InteractionCounter",
            "interactionType": {"@type": "WatchAction"},
            "userInteractionCount": v["views"],
        }
    return d


def breadcrumb_schema(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": abs_url(path)}
            for i, (name, path) in enumerate(items)
        ],
    }


# ---------------------------------------------------------------- page shell

def page(*, path: str, title: str, description: str, body: str, image: str = LOGO,
         og_type: str = "website", schema: list[dict] = (), extra_head: str = "", noindex: bool = False) -> str:
    canonical = abs_url(path)
    sub = CHANNEL["subscribe_url"]
    head_schema = "\n  ".join(jsonld(s) for s in schema)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  {'<meta name="robots" content="noindex">' if noindex else f'<link rel="canonical" href="{e(canonical)}">'}
  <meta name="theme-color" content="#2f6ff0">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(canonical)}">
  <meta property="og:image" content="{e(image)}">
  <meta property="og:locale" content="en_US">
  <meta name="twitter:card" content="{'summary_large_image' if image != LOGO else 'summary'}">
  <meta name="twitter:title" content="{e(title)}">
  <meta name="twitter:description" content="{e(description)}">
  <meta name="twitter:image" content="{e(image)}">
  {extra_head}
  <link rel="icon" href="{url('/assets/logo.jpg')}">
  <link rel="apple-touch-icon" href="{url('/assets/logo.jpg')}">
  <link rel="alternate" type="application/rss+xml" title="{SITE_NAME} on YouTube"
        href="https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL['id']}">
  <link rel="preconnect" href="https://i.ytimg.com">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{url('/assets/style.css')}">
  {head_schema}
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="nav">
    <div class="wrap nav-inner">
      <a class="brand" href="{url('/')}">
        <img src="{url('/assets/logo.jpg')}" alt="" width="36" height="36">
        <span>{SITE_NAME}</span>
      </a>
      <nav class="nav-links" aria-label="Main">
        <a href="{url('/#videos')}">Videos</a>
        <a href="{url('/topics/')}">Topics</a>
        <a href="{url('/#about')}">About</a>
      </nav>
      <a class="btn btn-sub" href="{e(sub)}" target="_blank" rel="noopener">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8zM9.6 15.6V8.4l6.3 3.6-6.3 3.6z"/></svg>
        Subscribe
      </a>
    </div>
  </header>
  <main id="main">
{body}
  </main>
  <footer class="footer">
    <div class="wrap footer-grid">
      <div>
        <a class="brand" href="{url('/')}"><img src="{url('/assets/logo.jpg')}" alt="" width="32" height="32"><span>{SITE_NAME}</span></a>
        <p class="muted">{e(TAGLINE)}. New videos every week.</p>
      </div>
      <nav aria-label="Topics">
        <h2>Topics</h2>
        {''.join(f'<a href="{url(f"/topics/{t["key"]}/")}">{e(t["label"])}</a>' for t in topics)}
      </nav>
      <nav aria-label="Channel">
        <h2>Channel</h2>
        <a href="{e(CHANNEL['url'])}" target="_blank" rel="noopener">YouTube ↗</a>
        <a href="{e(sub)}" target="_blank" rel="noopener">Subscribe ↗</a>
        <a href="{url('/sitemap.xml')}">Sitemap</a>
      </nav>
    </div>
    <div class="wrap footer-bottom muted">
      <span>© {datetime.now().year} {SITE_NAME}</span>
      <span>Video list updated {datetime.now(timezone.utc):%d %b %Y}</span>
    </div>
  </footer>
  <script src="{url('/assets/app.js')}" defer></script>
</body>
</html>
"""


# ---------------------------------------------------------------- components

def card(v, heading="h3") -> str:
    search = " ".join([v["title"], *v.get("tags", []), clean_desc(v.get("description", ""))[:300]]).lower()
    return f"""<a class="card" href="{url(vpath(v))}" data-topic="{e(v['topic'])}" data-type="{e(v['type'])}" data-search="{e(search)}">
        <div class="thumb">
          <img loading="lazy" decoding="async" src="{e(thumb(v))}" alt="{e(v['title'])}" width="480" height="360">
          <span class="badge {'short' if v['type'] == 'short' else ''}">{'Short' if v['type'] == 'short' else 'Video'}</span>
          <span class="play" aria-hidden="true"></span>
        </div>
        <div class="info">
          <{heading}>{e(v['title'])}</{heading}>
          <div class="meta">
            <span class="tag">{e(topic_label.get(v['topic'], ''))}</span>
            <time datetime="{e(v['published'])}" data-ago>{nice_date(v)}</time>
            {f'<span>· {fmt_views(v["views"])}</span>' if v.get('views') is not None else ''}
          </div>
        </div>
      </a>"""


def player(v, eager=False) -> str:
    """Lightweight player: just a thumbnail until clicked (keeps pages fast). Works without JS as a link."""
    q = "maxresdefault" if v["type"] == "video" else "hqdefault"
    return f"""<a class="yt {'yt-short' if v['type'] == 'short' else ''}" href="{e(v['url'])}" data-yt="{e(v['id'])}"
         target="_blank" rel="noopener" aria-label="Play video: {e(v['title'])}">
        <img src="{e(thumb(v, q))}" onerror="this.onerror=null;this.src='{e(thumb(v))}'" alt="{e(v['title'])}"
             {'fetchpriority="high"' if eager else 'loading="lazy"'} width="1280" height="720">
        <span class="play" aria-hidden="true"></span>
      </a>"""


def meta_line(v) -> str:
    return f"""<div class="meta">
          <a class="tag" href="{url(f"/topics/{v['topic']}/")}">{e(topic_label.get(v['topic'], ''))}</a>
          <time datetime="{e(v['published'])}">{nice_date(v)}</time>
          {f'<span>· {fmt_views(v["views"])}</span>' if v.get('views') is not None else ''}
          {f'<span>· {v["duration"] // 60}:{v["duration"] % 60:02d}</span>' if v.get('duration') else ''}
        </div>"""


# ---------------------------------------------------------------- pages

def tlink(key: str, label: str) -> str:
    """Link to a topic page only if that page exists (topics with no videos yet get no page)."""
    if any(t["key"] == key for t in topics):
        return f'<a href="{url(f"/topics/{key}/")}"><b>{e(label)}</b></a>'
    return f"<b>{e(label)}</b>"


def home() -> str:
    v0 = videos[0] if videos else None
    total_views = sum(v.get("views") or 0 for v in videos)
    tv = f"{total_views / 1000:.1f}".rstrip("0").rstrip(".") + "K" if total_views >= 1000 else str(total_views)
    featured = ""
    if v0:
        featured = f"""
    <section id="latest" class="wrap section" aria-labelledby="latest-h">
      <div class="section-head"><h2 id="latest-h">Latest upload</h2></div>
      <article class="featured {'is-short' if v0['type'] == 'short' else ''}">
        {player(v0)}
        <div class="body">
          {meta_line(v0)}
          <h3><a href="{url(vpath(v0))}">{e(v0['title'])}</a></h3>
          <p>{e(meta_desc(v0))}</p>
          <div class="actions">
            <a class="btn btn-primary" href="{url(vpath(v0))}">Watch &amp; read more</a>
            <a class="btn btn-ghost" href="{e(v0['url'])}" target="_blank" rel="noopener">Open on YouTube ↗</a>
          </div>
        </div>
      </article>
    </section>"""

    chips = "".join(
        f'<button type="button" data-topic="{t["key"]}">{e(t["label"])}<span class="n">{sum(v["topic"] == t["key"] for v in videos)}</span></button>'
        for t in topics)
    body = f"""
    <section class="hero">
      <div class="wrap hero-inner">
        <div class="hero-copy">
          <p class="eyebrow"><span class="gear" aria-hidden="true"></span> New videos every week</p>
          <h1>Everyday tech,<br><span>explained step by step.</span></h1>
          <p class="lede">Phone tips, security settings, free AI tools and the science behind the gadgets you use every day. Short, no-fluff videos that show you one thing you can do right now.</p>
          <div class="hero-cta">
            <a class="btn btn-primary" href="#latest">Watch the latest</a>
            <a class="btn btn-ghost" href="{e(CHANNEL['subscribe_url'])}" target="_blank" rel="noopener">Subscribe on YouTube</a>
          </div>
          <dl class="stats">
            <div><dt>{len(videos)}</dt><dd>videos on the site</dd></div>
            <div><dt>{tv}</dt><dd>views</dd></div>
            <div><dt>{len(topics)}</dt><dd>topics</dd></div>
          </dl>
        </div>
        <div class="hero-art" aria-hidden="true">
          <div class="orb"><img src="{url('/assets/logo.jpg')}" alt="" width="400" height="400"></div>
          <div class="chip c1">🔋 Battery</div>
          <div class="chip c2">🔐 Passkeys</div>
          <div class="chip c3">🚀 Rockets</div>
          <div class="chip c4">🤖 Free AI</div>
        </div>
      </div>
    </section>
{featured}
    <section id="videos" class="wrap section" aria-labelledby="videos-h">
      <div class="section-head">
        <h2 id="videos-h">All videos</h2>
        <label class="search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.5 3a7.5 7.5 0 0 1 5.9 12.1l4.8 4.8-1.4 1.4-4.8-4.8A7.5 7.5 0 1 1 10.5 3zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11z"/></svg>
          <span class="sr">Search videos</span>
          <input id="q" type="search" placeholder="Search videos…" autocomplete="off">
        </label>
      </div>
      <div class="filters">
        <div id="topics" class="chips" aria-label="Filter by topic">
          <button type="button" data-topic="all" class="on">All topics<span class="n">{len(videos)}</span></button>{chips}
        </div>
        <div id="types" class="seg" aria-label="Filter by format">
          <button type="button" data-type="all" class="on">All</button>
          <button type="button" data-type="video">Videos</button>
          <button type="button" data-type="short">Shorts</button>
        </div>
      </div>
      <div id="grid" class="grid">
      {''.join(card(v) for v in videos)}
      </div>
      <p id="empty" class="empty" hidden>No videos match that yet. Try another topic or search.</p>
      <div class="more"><button id="more" type="button" class="btn btn-ghost" hidden>Show more</button></div>
    </section>

    <section id="about" class="about" aria-labelledby="about-h">
      <div class="wrap about-inner">
        <img src="{url('/assets/logo.jpg')}" alt="{SITE_NAME} logo" width="120" height="120" loading="lazy">
        <div>
          <h2 id="about-h">Hi, I'm Eric.</h2>
          <p>Each video shows you one thing you can do right now: a setting to change, a scam to avoid, a free tool to try, or the simple idea behind tech you use every day.</p>
          <ul class="topics-list">
            <li>{tlink('phone', 'Phone tips')} for iPhone and Android: battery, privacy and hidden features</li>
            <li>{tlink('security', 'Security')}: stop scams, protect your data, keep your phone safe from theft</li>
            <li>{tlink('ai', 'AI tools')}: free AI you can use today, tested and explained</li>
            <li>{tlink('how', 'How it works')}: Wi-Fi, GPS, satellites and the science behind your gadgets</li>
            <li>{tlink('budget', 'Budget tech')}: gear worth buying without overspending</li>
          </ul>
          <a class="btn btn-primary" href="{e(CHANNEL['subscribe_url'])}" target="_blank" rel="noopener">Subscribe for weekly videos</a>
        </div>
      </div>
    </section>"""

    org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": abs_url("/#org"),
        "name": SITE_NAME,
        "url": abs_url("/"),
        "logo": LOGO,
        "description": SITE_DESC,
        "sameAs": [CHANNEL["url"], f"https://www.youtube.com/channel/{CHANNEL['id']}"],
    }
    site = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": abs_url("/"),
        "description": SITE_DESC,
        "publisher": {"@id": abs_url("/#org")},
        "inLanguage": "en",
    }
    return page(path="/", title=f"{SITE_NAME}: {TAGLINE} (Phone tips, Security, AI, Science)",
                description=SITE_DESC, body=body, schema=[org, site])


def video_page(v, i: int) -> str:
    same = [x for x in videos if x["topic"] == v["topic"] and x["id"] != v["id"]]
    others = [x for x in videos if x["id"] != v["id"] and x not in same]
    related = (same + others)[:6]
    newer = videos[i - 1] if i > 0 else None
    older = videos[i + 1] if i + 1 < len(videos) else None
    tlabel = topic_label.get(v["topic"], "")
    crumbs = [("Home", "/"), (tlabel, f"/topics/{v['topic']}/"), (v["title"], vpath(v))]
    desc_html = paragraphs(v.get("description", "")) or f"<p>{e(v['title'])}.</p>"
    tags = "".join(f'<li>#{e(t)}</li>' for t in v.get("tags", []))

    body = f"""
    <div class="wrap">
      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="{url('/')}">Home</a><span aria-hidden="true">›</span>
        <a href="{url(f"/topics/{v['topic']}/")}">{e(tlabel)}</a><span aria-hidden="true">›</span>
        <span aria-current="page">{e(v['title'])}</span>
      </nav>
      <article class="watch {'is-short' if v['type'] == 'short' else ''}">
        <div class="watch-player">{player(v, eager=True)}</div>
        <div class="watch-body">
          {meta_line(v)}
          <h1>{e(v['title'])}</h1>
          <div class="watch-actions">
            <a class="btn btn-primary" href="{e(v['url'])}" target="_blank" rel="noopener">Watch on YouTube ↗</a>
            <a class="btn btn-ghost" href="{e(CHANNEL['subscribe_url'])}" target="_blank" rel="noopener">Subscribe</a>
            <button class="btn btn-ghost" type="button" data-share>Share</button>
          </div>
          <div class="desc">
            <h2 class="sr">About this video</h2>
            {desc_html}
          </div>
          {f'<ul class="hashtags" aria-label="Tags">{tags}</ul>' if tags else ''}
        </div>
      </article>
      <nav class="prevnext" aria-label="More videos">
        {f'<a href="{url(vpath(newer))}"><small>← Newer</small>{e(newer["title"])}</a>' if newer else '<span></span>'}
        {f'<a class="next" href="{url(vpath(older))}"><small>Older →</small>{e(older["title"])}</a>' if older else '<span></span>'}
      </nav>
      <section class="section" aria-labelledby="rel-h">
        <div class="section-head">
          <h2 id="rel-h">More {e(tlabel.lower()) if same else 'videos'}</h2>
          <a class="link" href="{url(f"/topics/{v['topic']}/")}">See all {e(tlabel.lower())} →</a>
        </div>
        <div class="grid">{''.join(card(x) for x in related)}</div>
      </section>
    </div>"""
    title = f"{v['title']} | {SITE_NAME}"
    extra = (f'<meta property="og:video" content="https://www.youtube.com/embed/{e(v["id"])}">'
             f'<meta property="article:published_time" content="{e(v["published"])}">')
    return page(path=vpath(v), title=title, description=meta_desc(v), body=body,
                image=thumb(v, "hqdefault"), og_type="video.other", extra_head=extra,
                schema=[video_schema(v, abs_url(vpath(v))), breadcrumb_schema(crumbs)])


def topic_page(t) -> str:
    items = [v for v in videos if v["topic"] == t["key"]]
    h1, intro = TOPIC_INTROS.get(t["key"], (t["label"], ""))
    others = "".join(f'<a href="{url(f"/topics/{o["key"]}/")}">{e(o["label"])}</a>' for o in topics if o["key"] != t["key"])
    body = f"""
    <div class="wrap">
      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="{url('/')}">Home</a><span aria-hidden="true">›</span>
        <a href="{url('/topics/')}">Topics</a><span aria-hidden="true">›</span>
        <span aria-current="page">{e(t['label'])}</span>
      </nav>
      <header class="topic-head">
        <p class="eyebrow">{len(items)} video{'s' if len(items) != 1 else ''}</p>
        <h1>{e(h1)}</h1>
        <p class="lede">{e(intro)}</p>
      </header>
      <div class="grid">{''.join(card(v, "h2") for v in items)}</div>
      <nav class="other-topics" aria-label="Other topics"><span class="muted">More topics:</span>{others}</nav>
    </div>"""
    item_list = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": h1,
        "description": intro,
        "url": abs_url(f"/topics/{t['key']}/"),
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": abs_url(vpath(v))}
                                for i, v in enumerate(items)],
        },
    }
    crumbs = [("Home", "/"), ("Topics", "/topics/"), (t["label"], f"/topics/{t['key']}/")]
    return page(path=f"/topics/{t['key']}/", title=f"{h1} | {SITE_NAME}", description=intro, body=body,
                image=thumb(items[0]) if items else LOGO, schema=[item_list, breadcrumb_schema(crumbs)])


def topics_index() -> str:
    cards = ""
    for t in topics:
        items = [v for v in videos if v["topic"] == t["key"]]
        h1, intro = TOPIC_INTROS.get(t["key"], (t["label"], ""))
        cards += f"""<a class="topic-card" href="{url(f"/topics/{t['key']}/")}">
          <img loading="lazy" src="{e(thumb(items[0]))}" alt="" width="480" height="360">
          <div><h2>{e(t['label'])}</h2><p>{e(intro)}</p><span class="muted">{len(items)} video{'s' if len(items) != 1 else ''} →</span></div>
        </a>"""
    body = f"""
    <div class="wrap">
      <nav class="crumbs" aria-label="Breadcrumb"><a href="{url('/')}">Home</a><span aria-hidden="true">›</span><span aria-current="page">Topics</span></nav>
      <header class="topic-head"><h1>Browse by topic</h1><p class="lede">{e(SITE_DESC)}</p></header>
      <div class="topic-grid">{cards}</div>
    </div>"""
    return page(path="/topics/", title=f"Topics | {SITE_NAME}", description=SITE_DESC, body=body,
                schema=[breadcrumb_schema([("Home", "/"), ("Topics", "/topics/")])])


def not_found() -> str:
    body = f"""
    <div class="wrap topic-head" style="text-align:center;padding:96px 0">
      <h1>That page isn't here</h1>
      <p class="lede" style="margin-inline:auto">It may have moved. Try the latest videos instead.</p>
      <a class="btn btn-primary" href="{url('/')}">Go to the homepage</a>
    </div>
    <div class="wrap"><div class="grid">{''.join(card(v) for v in videos[:6])}</div></div>"""
    return page(path="/404.html", title=f"Page not found | {SITE_NAME}", description=SITE_DESC, body=body, noindex=True)


def sitemap() -> str:
    def u(loc, lastmod=None, extra=""):
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        return f"  <url><loc>{e(abs_url(loc))}</loc>{lm}{extra}</url>"

    latest = videos[0]["published"][:10] if videos else None
    rows = [u("/", latest), u("/topics/", latest)]
    for t in topics:
        items = [v for v in videos if v["topic"] == t["key"]]
        rows.append(u(f"/topics/{t['key']}/", items[0]["published"][:10]))
    for v in videos:
        dur = f"<video:duration>{int(v['duration'])}</video:duration>" if v.get("duration") else ""
        views = f"<video:view_count>{v['views']}</video:view_count>" if v.get("views") is not None else ""
        tags = "".join(f"<video:tag>{e(t)}</video:tag>" for t in v.get("tags", [])[:32])
        video = (f"<video:video><video:thumbnail_loc>{e(thumb(v))}</video:thumbnail_loc>"
                 f"<video:title>{e(v['title'][:100])}</video:title>"
                 f"<video:description>{e((clean_desc(v.get('description', '')) or v['title'])[:2048])}</video:description>"
                 f"<video:player_loc>https://www.youtube.com/embed/{e(v['id'])}</video:player_loc>"
                 f"{dur}<video:publication_date>{e(v['published'])}</video:publication_date>{views}"
                 f"<video:family_friendly>yes</video:family_friendly>"
                 f"<video:uploader info=\"{e(CHANNEL['url'])}\">{SITE_NAME}</video:uploader>{tags}</video:video>")
        rows.append(u(vpath(v), v["published"][:10], video))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">\n'
            + "\n".join(rows) + "\n</urlset>\n")


def write(rel: str, content: str) -> None:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "assets", OUT / "assets")
    (OUT / ".nojekyll").write_text("")
    if os.environ.get("CUSTOM_DOMAIN"):
        (OUT / "CNAME").write_text(os.environ["CUSTOM_DOMAIN"].strip() + "\n")

    write("index.html", home())
    for i, v in enumerate(videos):
        write(f"videos/{v['slug']}/index.html", video_page(v, i))
    write("topics/index.html", topics_index())
    for t in topics:
        write(f"topics/{t['key']}/index.html", topic_page(t))
    write("404.html", not_found())
    write("sitemap.xml", sitemap())
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {abs_url('/sitemap.xml')}\n")
    shutil.copy(ROOT / "data" / "videos.json", OUT / "videos.json")
    print(f"Built {len(videos)} video pages and {len(topics)} topic pages into {OUT} for {SITE_URL}")


if __name__ == "__main__":
    main()
