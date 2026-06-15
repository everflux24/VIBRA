#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIBRA_REBOOT v2.2 - CoreToken Architecture + Interruption Layer + Heat Delta
                      + SEO Structured Data (<time datetime>, JSON-LD, OGP fix)
                      NO f-string VERSION
==========================================================================
"""

import re
import json
import html as html_lib
import os
import hashlib
import sys
import urllib.request
import datetime
from collections import Counter

try:
    from core.token_cluster import (
        extract_tokens, get_core_token, update_cluster_core_token,
        should_merge, cluster_articles_v21, info_score, select_representative
    )
    from core.hook_reason import (
        generate_hook, extract_event, build_sub_reasons,
        GENERIC_WORDS, REACTION_KEYWORDS, SPECIFICITY_KEYWORDS
    )
    CORE_LOGIC_AVAILABLE = True
except ImportError:
    CORE_LOGIC_AVAILABLE = False
    print("WARNING: Core logic not found. Check core/token_cluster.py and core/hook_reason.py")
    sys.exit(1)


FAVICON_SVG = (
    '<link rel="icon" type="image/svg+xml" '
    'href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 '
    'viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E'
    + chr(0x1F525)
    + '%3C/text%3E%3C/svg%3E">'
)


class Slide:
    __slots__ = ("type", "data")

    def __init__(self, slide_type, data):
        self.type = slide_type
        self.data = data

    def to_dict(self):
        return {"type": self.type, "data": self.data}


def parse_posts(post_str):
    if isinstance(post_str, int):
        return post_str
    if not post_str or post_str in ("0", "\u8a73\u7d30\u306a\u3057"):
        return 0
    s = str(post_str).replace("\u30dd\u30b9\u30c8", "").replace(",", "").strip()
    try:
        return int(float(s.replace("\u4e07", "")) * 10000) if "\u4e07" in s else int(s)
    except:
        return 0


def build_slides(clusters):
    return [Slide("topic", cluster) for cluster in clusters]


def inject_interruptions(slides):
    return slides


META_PATH = os.path.join(os.environ.get("VIBRA_OUTPUT_DIR", "."), "build_meta.json")

def load_prev_meta():
    if not os.path.exists(META_PATH):
        return {}
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_meta(clusters):
    jst = datetime.timezone(datetime.timedelta(hours=9))
    meta = {
        "timestamp": datetime.datetime.now(jst).isoformat(),
        "clusters": [
            {"core_token": c["core_token"], "heat": c["heat"]}
            for c in clusters
        ]
    }
    meta_dir = os.path.dirname(META_PATH)
    if meta_dir and not os.path.exists(meta_dir):
        os.makedirs(meta_dir, exist_ok=True)

    try:
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("Meta save warning: " + str(e))


def compute_heat_status(cluster, prev_map):
    core = cluster["core_token"]
    heat = cluster["heat"]

    if core not in prev_map:
        return {
            "is_new": True,
            "delta_pct": 0.0,
            "status": "new",
            "badge_color": "#2ed573",
        }

    prev_heat = prev_map[core]
    if prev_heat == 0:
        delta_pct = 999.0 if heat > 0 else 0.0
    else:
        delta_pct = ((heat - prev_heat) / prev_heat) * 100

    if delta_pct >= 30:
        status, color = "surge", "#ff4757"
    elif delta_pct >= 10:
        status, color = "rise", "#ffa502"
    elif delta_pct <= -10:
        status, color = "fall", "#a4b0be"
    else:
        status, color = "stable", "#ffea00"

    return {
        "is_new": False,
        "delta_pct": round(delta_pct, 1),
        "status": status,
        "badge_color": color,
    }


def generate_json_ld(slides, iso_time, page_title, page_desc):
    item_list = []
    position = 1
    for slide in slides:
        if slide.type != "topic":
            continue
        cluster = slide.data
        rep = cluster.get("rep", {})
        title = rep.get("title", "")
        summary = rep.get("summary", "")
        desc = summary[:150] + "..." if len(summary) > 150 else summary
        if not title:
            continue
        item_list.append({
            "@type": "ListItem",
            "position": position,
            "item": {
                "@type": "NewsArticle",
                "headline": title,
                "description": desc,
                "datePublished": iso_time,
                "dateModified": iso_time,
                "url": "https://everflux24.github.io/VIBRA/"
            }
        })
        position += 1

    data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": page_title,
        "description": page_desc,
        "dateModified": iso_time,
        "itemListElement": item_list
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def esc(text):
    return html_lib.escape(str(text), quote=True)


def generate_app_html(slides, out_path=None):
    if out_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, "index.html")

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    build_timestamp = now.strftime('%Y-%m-%d %H:%M JST')
    version = now.strftime('%Y%m%d_%H%M')
    time_str = now.strftime("%H:%M")
    iso_time = now.isoformat()

    ogp_image_url = "https://everflux24.github.io/VIBRA/ogp-default.png?v=" + version

    page_title = "X\uff08Twitter\uff09\u30c8\u30ec\u30f3\u30c9\u307e\u3068\u3081\uff5cVIBRA"
    page_desc = "X\uff08Twitter\uff09\u306e\u6700\u65b0\u8a71\u984c\u309230\u5206\u3054\u3068\u306b\u81ea\u52d5\u66f4\u65b0\u3002TikTok\u98a8\u306e\u7e26\u30b9\u30ef\u30a4\u30d7UI\u3067\u3001\u30cb\u30e5\u30fc\u30b9\u3084SNS\u306e\u6d41\u884c\u3092\u3059\u3070\u3084\u304f\u30c1\u30a7\u30c3\u30af\u3067\u304d\u307e\u3059\u3002"

    json_ld = generate_json_ld(slides, iso_time, page_title, page_desc)

    css = """
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", "Noto Sans JP", sans-serif; background: #000; color: #fff; overflow: hidden; }
        .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
        .app-container { height: 100vh; width: 100%; overflow-y: scroll; scroll-snap-type: y mandatory; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
        .app-container::-webkit-scrollbar { display: none; }
        .slide { height: 100vh; width: 100%; scroll-snap-align: start; display: flex; flex-direction: column; justify-content: flex-end; padding: 28px 24px 80px; position: relative; overflow: hidden; }
        .bg-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain; z-index: -2; filter: brightness(0.7); background: #111; }
        .bg-gradient { position: absolute; inset: 0; z-index: -1; background: linear-gradient(180deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.4) 40%, rgba(0,0,0,0.85) 80%, rgba(0,0,0,0.95) 100%); }
        .bg-fallback { position: absolute; inset: 0; z-index: -2; filter: blur(60px); opacity: 0.6; }
        .content { z-index: 10; max-width: 100%; transition: opacity 0.35s ease; }
        .content.hidden { opacity: 0; pointer-events: none; }
        .hook-badge { display: inline-block; color: #000; font-size: 14px; font-weight: 800; padding: 6px 14px; border-radius: 20px; margin-bottom: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        h2.title { font-size: 26px; font-weight: 900; line-height: 1.3; margin-bottom: 12px; text-shadow: 0 2px 16px rgba(0,0,0,0.8); }
        p.summary { font-size: 15px; line-height: 1.65; color: #eee; background: rgba(20,20,20,0.5); padding: 16px; border-radius: 12px; backdrop-filter: blur(6px); margin-bottom: 16px; }
        .meta { font-size: 16px; color: #ff6b6b; font-weight: 800; display: flex; align-items: center; gap: 6px; text-shadow: 0 1px 4px rgba(0,0,0,0.8); margin-bottom: 14px; }
        .meta-icon { font-size: 18px; }
        .related { margin-top: 4px; }
        .related-label { font-size: 12px; color: #aaa; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
        .related-item { background: rgba(255,255,255,0.08); padding: 10px 14px; border-radius: 8px; margin-bottom: 6px; backdrop-filter: blur(4px); font-size: 13px; color: #ddd; display: flex; justify-content: space-between; align-items: center; }
        .related-text { font-weight: 600; color: #fff; }
        .related-posts { color: #ff6b6b; font-weight: 700; font-size: 12px; }
        .hint { position: absolute; bottom: 20px; width: 100%; left: 0; text-align: center; font-size: 12px; color: rgba(255,255,255,0.4); animation: bounce 2.5s infinite; letter-spacing: 1px; }
        @keyframes bounce { 0%, 20%, 50%, 80%, 100% {transform: translateY(0);} 40% {transform: translateY(-8px);} 60% {transform: translateY(-4px);} }
        .update-badge { position: absolute; top: 16px; left: 16px; z-index: 50; background: rgba(0,0,0,0.4); color: #fff; font-size: 11px; font-weight: 700; padding: 5px 10px; border-radius: 12px; backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.1); letter-spacing: 0.3px; }
        .new-tag { display: inline-block; background: #ff4757; color: #fff; font-size: 10px; font-weight: 900; padding: 2px 7px; border-radius: 8px; margin-left: 6px; vertical-align: middle; letter-spacing: 0.5px; }
        .interruption-slide { display: flex; align-items: center; justify-content: center; }
        .interruption-content { text-align: center; padding: 40px 24px; max-width: 90%; }
        .interruption-badge { display: inline-block; background: rgba(255,255,255,0.15); color: #fff; font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 12px; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }
        .interruption-title { font-size: 22px; font-weight: 900; margin-bottom: 12px; line-height: 1.4; }
        .interruption-desc { font-size: 14px; color: rgba(255,255,255,0.85); line-height: 1.6; }
        .interruption-cta { display: inline-block; margin-top: 20px; background: #fff; color: #000; font-size: 14px; font-weight: 800; padding: 10px 24px; border-radius: 24px; text-decoration: none; }
        .ranking-bg { background: linear-gradient(135deg, #ff4757 0%, #ff6b6b 100%); }
        .ranking-list { list-style: none; margin-top: 16px; text-align: left; }
        .ranking-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.15); font-size: 15px; }
        .ranking-num { font-size: 20px; font-weight: 900; color: #ffea00; min-width: 28px; }
        .ranking-text { font-weight: 700; }
        .ranking-posts { margin-left: auto; font-size: 12px; color: rgba(255,255,255,0.7); }
        .promo-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .disclaimer { position: absolute; bottom: 48px; right: 16px; font-size: 9px; color: rgba(255,255,255,0.22); text-align: right; line-height: 1.5; max-width: 240px; z-index: 20; letter-spacing: 0.3px; pointer-events: none; mix-blend-mode: luminosity; }
        @keyframes toastIn { from { opacity: 0; transform: translateX(-50%) translateY(10px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        @keyframes toastOut { from { opacity: 1; } to { opacity: 0; } }
    </style>
    """

    slides_html = ""
    colors = ["#ff4757", "#2ed573", "#1e90ff", "#ffa502", "#3742fa", "#a55eea", "#26de81"]

    for i, slide in enumerate(slides):
        if slide.type == "topic":
            slides_html += _render_topic_slide(i, slide.data, colors, time_str, iso_time)
        elif slide.type == "interruption":
            slides_html += _render_interruption_slide(i, slide.data)

    parts = []
    parts.append('<!DOCTYPE html><!-- VIBRA_BUILD: ' + build_timestamp + ' --><html lang="ja"><head><meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">')
    parts.append('<meta name="theme-color" content="#000000"><meta name="google-site-verification" content="teiftQqNINv-6xUwSh2bHx9fYM2_XtNd3yhuS0e1kNQ"><meta http-equiv="refresh" content="1800">')
    parts.append('<meta name="description" content="' + esc(page_desc) + '">')
    parts.append('<meta property="og:title" content="' + esc(page_title) + '">')
    parts.append('<meta property="og:description" content="' + esc(page_desc) + '">')
    parts.append('<meta property="og:type" content="website"><meta property="og:url" content="https://everflux24.github.io/VIBRA/">')
    parts.append('<meta property="og:image" content="' + esc(ogp_image_url) + '"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image">')
    parts.append(FAVICON_SVG)
    parts.append('<title>' + esc(page_title) + '</title>' + css)
    parts.append('<script type="application/ld+json">' + json_ld + '</script>')
    parts.append('</head><body><h1 class="visually-hidden">\u4eca\u65e5\u306e\u65e5\u672c\u30c8\u30ec\u30f3\u30c9\u307e\u3068\u3081</h1>')
    parts.append('<main class="app-container">' + slides_html + '</main>')
    parts.append('</body></html>')

    full_html = "".join(parts)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print("Generated: " + out_path + " (slides: " + str(len(slides)) + ")")
    return out_path


def generate_sitemap(base_url="https://everflux24.github.io/VIBRA"):
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    lastmod = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n  <url>\n    <loc>" + base_url + "/</loc>\n    <lastmod>" + lastmod + "</lastmod>\n    <changefreq>always</changefreq>\n    <priority>1.0</priority>\n  </url>\n</urlset>"
    sitemap_path = os.path.join(OUTPUT_DIR, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print("Generated: " + sitemap_path)


def generate_robots_txt(base_url="https://everflux24.github.io/VIBRA"):
    robots = "User-agent: *\nAllow: /\n\nSitemap: " + base_url + "/sitemap.xml"
    robots_path = os.path.join(OUTPUT_DIR, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(robots)
    print("Generated: " + robots_path)


def _render_topic_slide(i, cluster, colors, time_str, iso_time):
    rep = cluster['rep']
    bg_color = colors[i % len(colors)]
    hook_text = generate_hook(cluster['core_token'], rep['title'])

    hs = cluster.get("heat_status", {})
    badge_color = hs.get("badge_color", "#ffea00")
    is_new = hs.get("is_new", False)
    new_tag = '<span class="new-tag">\u65b0\u7740</span>' if is_new else ''

    c_core = cluster.get('core_token', '')
    rep_title = rep.get('title', '')
    image_url = rep.get('image', '') if c_core in rep_title else ''

    if image_url:
        bg_html = ('<img class="bg-img" src="' + esc(image_url) + '" alt="" '
                   'aria-hidden="true" loading="lazy" decoding="async" referrerpolicy="no-referrer">'
                   '<div class="bg-gradient" aria-hidden="true"></div>')
    else:
        bg_html = ('<div class="bg-fallback" style="background: ' + bg_color + ';" aria-hidden="true"></div>'
                   '<div class="bg-gradient" aria-hidden="true"></div>')

    posts_num = cluster['heat']
    if posts_num >= 10000:
        posts_str = str(round(posts_num / 10000, 1)) + "\u4e07" if posts_num % 10000 != 0 else str(posts_num // 10000) + "\u4e07"
    else:
        posts_str = "{:,}".format(posts_num)

    related_html = ""
    if cluster.get('sub_reasons'):
        related_html = '<div class="related"><div class="related-label">\u95a2\u9023</div>'
        for sub in cluster['sub_reasons']:
            sub_posts = sub['posts']
            if sub_posts >= 10000:
                sub_posts_str = str(sub_posts // 10000) + "\u4e07"
            elif sub_posts >= 1000:
                sub_posts_str = str(sub_posts // 1000) + "k"
            else:
                sub_posts_str = str(sub_posts)
            related_html += ('<div class="related-item">'
                             '<span class="related-text">' + esc(sub["text"]) + '</span>'
                             '<span class="related-posts">' + chr(0x1F525) + ' ' + sub_posts_str + '</span>'
                             '</div>')
        related_html += '</div>'

    parts = []
    parts.append('<article class="slide" aria-labelledby="heading-' + str(i) + '">')
    parts.append(bg_html)
    parts.append('<time datetime="' + esc(iso_time) + '" class="update-badge">' + chr(0x1F504) + ' ' + esc(time_str) + ' \u66f4\u65b0</time>')
    parts.append('<div class="content">')
    parts.append('<span class="hook-badge" role="text" style="background: ' + badge_color + ';">' + esc(hook_text) + '</span>')
    parts.append('<h2 id="heading-' + str(i) + '" class="title">' + esc(rep['title']) + '</h2>')
    parts.append('<p class="summary">' + esc(rep['summary']) + '</p>')
    parts.append('<footer class="meta" aria-label="\u30bd\u30fc\u30b7\u30e3\u30eb\u53cd\u97ff">')
    parts.append('<span class="meta-icon">' + chr(0x1F525) + '</span>')
    parts.append('<span>' + posts_str + ' \u30dd\u30b9\u30c8' + new_tag + '</span>')
    parts.append('</footer>')
    parts.append(related_html)
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">\u203b\u81ea\u52d5\u53d6\u5f97\u30fb\u81ea\u52d5\u8981\u7d04\u3002\u80cc\u666f\u30df\u30b9\u30de\u30c3\u30c1\u3001\u539f\u6587\u306e\u30cb\u30e5\u30a2\u30f3\u30b9\u304c\u640d\u306a\u308f\u308c\u308b\u5834\u5408\u304c\u3042\u308a\u3001\u5185\u5bb9\u306e\u6b63\u78ba\u6027\u3092\u4fdd\u8a3c\u3059\u308b\u3082\u306e\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP \u2193</div>')
    parts.append('</article>')
    return "".join(parts)


def _render_interruption_slide(i, data):
    kind = data.get("kind", "promo")
    if kind == "ranking":
        return _render_ranking_slide(i, data)
    elif kind == "announcement":
        return _render_announcement_slide(i, data)
    else:
        return _render_promo_slide(i, data)


def _render_ranking_slide(i, data):
    title = esc(data.get("title", "\u4eba\u6c17\u30e9\u30f3\u30ad\u30f3\u30b0"))
    items = data.get("items", [])
    items_html = ""
    for idx, item in enumerate(items[:5], 1):
        text = esc(item.get("text", ""))
        posts = item.get("posts", 0)
        if posts >= 10000:
            posts_str = str(posts // 10000) + "\u4e07"
        elif posts >= 1000:
            posts_str = str(posts // 1000) + "k"
        else:
            posts_str = str(posts)
        items_html += ('<li class="ranking-item">'
                       '<span class="ranking-num">' + str(idx) + '</span>'
                       '<span class="ranking-text">' + text + '</span>'
                       '<span class="ranking-posts">' + posts_str + ' \u30dd\u30b9\u30c8</span>'
                       '</li>')

    parts = []
    parts.append('<article class="slide interruption-slide ranking-bg" aria-labelledby="ranking-heading-' + str(i) + '">')
    parts.append('<div class="interruption-content">')
    parts.append('<span class="interruption-badge">Ranking</span>')
    parts.append('<h2 id="ranking-heading-' + str(i) + '" class="interruption-title">' + title + '</h2>')
    parts.append('<ul class="ranking-list">' + items_html + '</ul>')
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">\u203b\u81ea\u52d5\u53d6\u5f97\u30fb\u81ea\u52d5\u8981\u7d04\u3002\u539f\u6587\u306e\u30cb\u30e5\u30a2\u30f3\u30b9\u304c\u640d\u306a\u308f\u308c\u308b\u5834\u5408\u304c\u3042\u308a\u3001\u5185\u5bb9\u306e\u6b63\u78ba\u6027\u3092\u4fdd\u8a3c\u3059\u308b\u3082\u306e\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP \u2193</div>')
    parts.append('</article>')
    return "".join(parts)


def _render_promo_slide(i, data):
    badge = esc(data.get("badge", "Sponsored"))
    title = esc(data.get("title", ""))
    description = esc(data.get("description", ""))
    cta = esc(data.get("cta", "\u8a73\u3057\u304f\u898b\u308b"))
    cta_url = esc(data.get("cta_url", "#"))

    parts = []
    parts.append('<article class="slide interruption-slide promo-bg" aria-labelledby="promo-heading-' + str(i) + '">')
    parts.append('<div class="interruption-content">')
    parts.append('<span class="interruption-badge">' + badge + '</span>')
    parts.append('<h2 id="promo-heading-' + str(i) + '" class="interruption-title">' + title + '</h2>')
    parts.append('<p class="interruption-desc">' + description + '</p>')
    parts.append('<a href="' + cta_url + '" class="interruption-cta" target="_blank" rel="noopener noreferrer">' + cta + '</a>')
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">\u203b\u81ea\u52d5\u53d6\u5f97\u30fb\u81ea\u52d5\u8981\u7d04\u3002\u539f\u6587\u306e\u30cb\u30e5\u30a2\u30f3\u30b9\u304c\u640d\u306a\u308f\u308c\u308b\u5834\u5408\u304c\u3042\u308a\u3001\u5185\u5bb9\u306e\u6b63\u78ba\u6027\u3092\u4fdd\u8a3c\u3059\u308b\u3082\u306e\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP \u2193</div>')
    parts.append('</article>')
    return "".join(parts)


def _render_announcement_slide(i, data):
    badge = esc(data.get("badge", "News"))
    title = esc(data.get("title", ""))
    description = esc(data.get("description", ""))
    cta = esc(data.get("cta", "\u78ba\u8a8d\u3059\u308b"))
    cta_url = esc(data.get("cta_url", "#"))

    parts = []
    parts.append('<article class="slide interruption-slide" style="background: linear-gradient(135deg, #2ed573 0%, #1e90ff 100%);" aria-labelledby="announce-heading-' + str(i) + '">')
    parts.append('<div class="interruption-content">')
    parts.append('<span class="interruption-badge">' + badge + '</span>')
    parts.append('<h2 id="announce-heading-' + str(i) + '" class="interruption-title">' + title + '</h2>')
    parts.append('<p class="interruption-desc">' + description + '</p>')
    parts.append('<a href="' + cta_url + '" class="interruption-cta" target="_blank" rel="noopener noreferrer">' + cta + '</a>')
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">\u203b\u81ea\u52d5\u53d6\u5f97\u30fb\u81ea\u52d5\u8981\u7d04\u3002\u539f\u6587\u306e\u30cb\u30e5\u30a2\u30f3\u30b9\u304c\u640d\u306a\u308f\u308c\u308b\u5834\u5408\u304c\u3042\u308a\u3001\u5185\u5bb9\u306e\u6b63\u78ba\u6027\u3092\u4fdd\u8a3c\u3059\u308b\u3082\u306e\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP \u2193</div>')
    parts.append('</article>')
    return "".join(parts)


TARGET_URL = "https://search.yahoo.co.jp/realtime/search/matome"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
OUTPUT_DIR = os.environ.get("VIBRA_OUTPUT_DIR", ".")
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def fetch_data():
    print("HTTP GET fetching data...")
    req = urllib.request.Request(TARGET_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("Fetch error: " + str(e))
        return None


def parse_html(html):
    if not html:
        return []
    m = NEXT_DATA_RE.search(html)
    if not m:
        print("__NEXT_DATA__ not found (DOM structure may have changed)")
        return []
    try:
        data = json.loads(m.group(1))
        items = data["props"]["pageProps"]["pageData"]["matomeList"]["items"]
    except (KeyError, json.JSONDecodeError) as e:
        print("JSON parse error: " + str(e))
        return []

    data_list = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        summary = (it.get("summary") or "\u8a73\u7d30\u306a\u3057").strip()
        posts = it.get("tweetCount", 0)
        image = ""
        img = it.get("image")
        if isinstance(img, dict):
            image = img.get("url", "")
        elif isinstance(img, str):
            image = img
        sentiment = it.get("sentiment") or {}
        data_list.append({
            "title": title,
            "summary": summary,
            "posts": posts,
            "image": image,
            "url": it.get("url", ""),
            "positive": sentiment.get("positive"),
            "negative": sentiment.get("negative"),
        })
    print("Extracted " + str(len(data_list)) + " trends.")
    return data_list


def main():
    prev_meta = load_prev_meta()
    prev_map = {c["core_token"]: c["heat"] for c in prev_meta.get("clusters", [])}
    print("Previous clusters: " + str(len(prev_map)))

    raw = fetch_data()
    data = parse_html(raw) if raw else []

    if not data:
        print("No data. Build aborted (old site preserved).")
        sys.exit(1)

    clusters = cluster_articles_v21(data)

    for cluster in clusters:
        cluster['sub_reasons'] = build_sub_reasons(cluster, cluster['rep'])
        cluster["heat_status"] = compute_heat_status(cluster, prev_map)

    save_meta(clusters)

    slides = build_slides(clusters)
    slides = inject_interruptions(slides)

    ogp_src = os.path.join(os.path.dirname(__file__), "ogp-default.png")
    ogp_dst = os.path.join(OUTPUT_DIR, "ogp-default.png")
    if os.path.exists(ogp_src):
        import shutil
        shutil.copy2(ogp_src, ogp_dst)
        print("Copied: " + ogp_src + " -> " + ogp_dst)
    else:
        print("OGP image not found: " + ogp_src)

    generate_app_html(slides)
    generate_sitemap()
    generate_robots_txt()

    new_count = sum(1 for c in clusters if c["heat_status"]["is_new"])
    surge_count = sum(1 for c in clusters if c["heat_status"]["status"] == "surge")
    print("\nVIBRA_REBOOT v2.2 build complete")
    print("  Clusters: " + str(len(clusters)))
    print("  New: " + str(new_count) + " | Surge: " + str(surge_count))
    print("  Total slides: " + str(len(slides)))


if __name__ == "__main__":
    main()
