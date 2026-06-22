#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aoaeola v2.5 - CoreToken Architecture + Interruption Layer + Heat Delta
                      + SEO Structured Data + Summary Quality Filter
                      + Archive System (4h blocks / 365d rolling / Gradient BG)
                      + A方式: 同日全アーカイブ再生成（SEO最適）
NO f-string VERSION
============================================================================
"""

import re
import json
import html as html_lib
import os
import hashlib
import sys
import urllib.request
import datetime
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# ============================================================
# Core Logic Import (Secrets or local)
# ============================================================
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

# ============================================================
# Archive Utilities (committed to repo)
# ============================================================
from core.archive_utils import (
    get_color_from_token,
    get_archive_path,
    get_archive_hour_blocks,
    cleanup_old_archives,
    get_recent_archive_links,
    get_top_page_archive_links,
    get_adjacent_archive_links,
    get_archive_nav_html,
    get_same_day_hour_nav_html,
    generate_archive_title,
    safe_replace,
    extract_content_cards,
    render_single_archive_page,
    save_archive_page,
    regenerate_same_day_archives,
)


# ============================================================
# Constants
# ============================================================
FAVICON_SVG = (
    '<link rel="icon" type="image/svg+xml" '
    'href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 '
    'viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E'
    + chr(0x1F525)
    + '%3C/text%3E%3C/svg%3E">'
)

TARGET_URL = "https://search.yahoo.co.jp/realtime/search/matome"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUTPUT_DIR = os.environ.get("VIBRA_OUTPUT_DIR", "_site")
META_PATH = os.path.join(OUTPUT_DIR, "build_meta.json")
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ET.register_namespace("", SITEMAP_NS)


# ============================================================
# Summary Quality Filter (v2.5)
# ============================================================
AI_PATTERNS = [
    r'と話題になっている',
    r'とSNSで話題に',
    r'達成したよ',
    r'発売されたよ',
    r'公開されたよ',
    r'開始されたよ',
    r'決定したよ',
    r'みたいです',
    r'みたいで',
    r'ようです',
    r'ようだ',
    r'様子がうかがえる',
    r'とみられる',
    r'と思われる',
    r'と思われ',
    r'と考えられる',
    r'と推測される',
    r'の可能性がある',
    r'かもしれない',
    r'かもしれません',
    r'だろう',
    r'でしょう',
    r'のようだ',
    r'のような',
    r'といった',
    r'などと',
    r'などが',
    r'などの',
    r' reportedly',
    r' allegedly',
]


def clean_summary(summary):
    """生成AIによる安定的表現を除去し、サマリー品質を向上"""
    if not summary or summary == "詳細なし":
        return summary
    original = summary
    for pattern in AI_PATTERNS:
        summary = re.sub(pattern, '', summary)
    summary = re.sub(r'\s*よ\s*。', '。', summary)
    summary = re.sub(r'\s*だよ\s*。', '。', summary)
    summary = re.sub(r'\s*なんだ\s*。', '。', summary)
    summary = re.sub(r'\s*みたい\s*。', '。', summary)
    summary = re.sub(r'\s*みたいです\s*。', '。', summary)
    summary = re.sub(r'\s*ようです\s*。', '。', summary)
    summary = re.sub(r'\s+', ' ', summary)
    summary = summary.strip()
    if summary.endswith('が') or summary.endswith('を') or summary.endswith('に'):
        summary = summary + '。'
    if not summary.strip():
        summary = original
    return summary


# ============================================================
# Slide Model
# ============================================================
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
    if not post_str or post_str in ("0", "詳細なし"):
        return 0
    s = str(post_str).replace("ポスト", "").replace(",", "").strip()
    try:
        return int(float(s.replace("万", "")) * 10000) if "万" in s else int(s)
    except:
        return 0


def build_slides(clusters):
    """Build slides: surge/new first, then normal clusters."""
    surge_clusters = []
    normal_clusters = []
    for c in clusters:
        hs = c.get("heat_status", {})
        if hs.get("status") == "surge" or hs.get("is_new", False):
            surge_clusters.append(c)
        else:
            normal_clusters.append(c)
    slides = []
    for c in surge_clusters:
        slides.append(Slide("topic", c))
    for c in normal_clusters:
        slides.append(Slide("topic", c))
    return slides


def inject_interruptions(slides):
    """
    新着・急上昇記事をピックアップして先頭に配置。
    ピックアップが5件未満の場合、heat順で上位を追加して5件を確保。
    ピックアップ済み記事は後続の通常表示から除外（重複なし）。
    """
    if not slides:
        return slides

    pickup_slides = []
    normal_slides = []
    picked_indices = set()

    # 1. 新着・急上昇をピックアップ
    for i, slide in enumerate(slides):
        if slide.type != "topic":
            continue
        hs = slide.data.get("heat_status", {})
        if hs.get("is_new") or hs.get("status") == "surge":
            pickup_slides.append(slide)
            picked_indices.add(i)

    # 2. 5件未満なら heat 順で上位を追加
    if len(pickup_slides) < 5:
        needed = 5 - len(pickup_slides)
        for i, slide in enumerate(slides):
            if i in picked_indices or slide.type != "topic":
                continue
            pickup_slides.append(slide)
            picked_indices.add(i)
            if len(pickup_slides) >= 5:
                break

    # 3. ピックアップ内を「新着→surge→その他」の順に並べ替え
    def _pickup_sort_key(slide):
        hs = slide.data.get("heat_status", {})
        if hs.get("is_new"):
            return (0, -slide.data.get("heat", 0))
        elif hs.get("status") == "surge":
            return (1, -slide.data.get("heat", 0))
        else:
            return (2, -slide.data.get("heat", 0))

    pickup_slides.sort(key=_pickup_sort_key)

    # 4. 残りを通常スライドに
    for i, slide in enumerate(slides):
        if i not in picked_indices:
            normal_slides.append(slide)

    return pickup_slides + normal_slides


# ============================================================
# Meta / Heat Delta
# ============================================================
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
    if delta_pct >= 20:
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


# ============================================================
# JSON-LD / SEO
# ============================================================
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
                "url": "https://everflux24.github.io/Aoaeola/"
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


# ============================================================
# Archive Footer HTML Generator
# ============================================================
def generate_top_footer_archive_links(now, output_dir):
    """過去7日のアーカイブリンクをフッターとして生成（トップページ用：絶対パス）"""
    archive_root = Path(output_dir).resolve() / "archive"
    links = []
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))

    for i in range(7):
        d = today - datetime.timedelta(days=i)
        date_path = archive_root / (str(d.year) + "/" + "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day))
        has_data = date_path.exists() and any(date_path.iterdir())

        html_file = ""
        if has_data:
            try:
                html_files = sorted([f.name for f in date_path.iterdir() if f.suffix == ".html"])
                if html_files:
                    html_file = html_files[-1]
            except (OSError, PermissionError):
                pass

        # トップページからは絶対パス /archive/YYYY/MM/DD/HH-00.html
        if html_file:
            path = "https://everflux24.github.io/Aoaeola/archive/" + str(d.year) + "/" + "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day) + "/" + html_file
        else:
            path = ""

        links.append({
            "date_str": "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day),
            "path": path,
            "has_data": has_data,
        })

    if not any(link["has_data"] for link in links):
        return ""

    html_parts = ['<footer class="archive-footer">']
    html_parts.append('<div class="archive-footer-label">過去7日のアーカイブ</div>')
    html_parts.append('<div class="archive-footer-links">')
    for link in links:
        cls = "archive-footer-link" if link["has_data"] else "archive-footer-link empty"
        if link["has_data"] and link["path"]:
            html_parts.append(
                '<a href="' + link["path"] + '" class="' + cls + '">' + link["date_str"] + '</a>'
            )
        else:
            html_parts.append('<span class="' + cls + '">' + link["date_str"] + '</span>')
    html_parts.append('</div></footer>')
    return "".join(html_parts)


# ============================================================
# Main HTML Generator
# ============================================================
def generate_app_html(slides, out_path=None):
    if out_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, "index.html")
    else:
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    build_timestamp = now.strftime('%Y-%m-%d %H:%M JST')
    version = now.strftime('%Y%m%d_%H%M')
    time_str = now.strftime("%H:%M")
    iso_time = now.isoformat()
    ogp_image_url = "https://everflux24.github.io/Aoaeola/ogp-default.png?v=" + version

    page_title = "Aoaeola｜ゆるく瞰めるXトレンド"
    page_desc = "暇つぶしのついでに、世の中の空気がなんとなくわかる。Xで話題のニュースやトレンドを30分ごとにまとめる、ゆるく瞰めるためのサービスです。"
    ogp_desc = "ニュースや流行の“みんなの反応”を、縦スワイプで気軽にチェック。少し空いた時間の暇つぶしに。"

    json_ld = generate_json_ld(slides, iso_time, page_title, page_desc)

    # v2.5: Archive footer CSS
    archive_css = """
    .archive-footer {
      background: rgba(0,0,0,0.6);
      backdrop-filter: blur(10px);
      padding: 1rem 0;
      text-align: center;
      border-top: 1px solid rgba(255,255,255,0.1);
    }
    .archive-footer-label {
      font-size: 0.75rem;
      color: rgba(255,255,255,0.5);
      margin-bottom: 0.5rem;
      letter-spacing: 0.5px;
    }
    .archive-footer-links {
      display: flex;
      justify-content: center;
      gap: 0.5rem;
      flex-wrap: wrap;
      padding: 0 1rem;
    }
    .archive-footer-link {
      display: inline-block;
      padding: 0.4rem 0.8rem;
      background: rgba(255,255,255,0.1);
      color: rgba(255,255,255,0.8);
      text-decoration: none;
      border-radius: 6px;
      font-size: 0.8rem;
      transition: background 0.2s;
    }
    .archive-footer-link:hover {
      background: rgba(255,255,255,0.2);
    }
    .archive-footer-link.empty {
      opacity: 0.4;
      pointer-events: none;
    }
    .archive-footer-slide {
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      background: linear-gradient(180deg, rgba(0,0,0,0.95) 0%, #111 100%) !important;
    }
    .archive-footer-slide .archive-footer {
      background: transparent !important;
      backdrop-filter: none !important;
      border-top: none !important;
      padding: 2rem 0 !important;
    }
    .archive-footer-slide .archive-footer-label {
      font-size: 1rem !important;
      color: rgba(255,255,255,0.7) !important;
      margin-bottom: 1rem !important;
    }
    .archive-footer-slide .archive-footer-link {
      padding: 0.6rem 1rem !important;
      font-size: 0.9rem !important;
    }
    """

    css = '<style>' + archive_css + """
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
        h3.title { font-size: 22px; font-weight: 900; line-height: 1.3; margin-bottom: 12px; text-shadow: 0 2px 16px rgba(0,0,0,0.8); }
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
    </style>"""

    slides_html = ""
    colors = ["#ff4757", "#2ed573", "#1e90ff", "#ffa502", "#3742fa", "#a55eea", "#26de81"]
    for i, slide in enumerate(slides):
        if slide.type == "topic":
            slides_html += _render_topic_slide(i, slide.data, colors, time_str, iso_time, is_h3=True)
        elif slide.type == "interruption":
            slides_html += _render_interruption_slide(i, slide.data)

    parts = []
    parts.append('<!DOCTYPE html><!-- Aoaeola_BUILD: ' + build_timestamp + ' --><html lang="ja"><head><meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">')
    parts.append('<meta name="theme-color" content="#000000"><meta name="google-site-verification" content="teiftQqNINv-6xUwSh2bHx9fYM2_XtNd3yhuS0e1kNQ"><meta http-equiv="refresh" content="1800">')
    parts.append('<meta name="description" content="' + esc(page_desc) + '">')
    parts.append('<meta property="og:title" content="' + esc(page_title) + '">')
    parts.append('<meta property="og:description" content="' + esc(ogp_desc) + '">')
    parts.append('<meta property="og:type" content="website"><meta property="og:url" content="https://everflux24.github.io/Aoaeola/">')
    parts.append('<meta property="og:image" content="' + esc(ogp_image_url) + '"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image">')
    parts.append(FAVICON_SVG)
    parts.append('<title>' + esc(page_title) + '</title>' + css)
    parts.append('<script type="application/ld+json">' + json_ld + '</script>')
    parts.append('</head><body><h1 class="visually-hidden">今日の日本トレンドまとめ</h1>')
    # v2.5: Archive footer as last slide
    archive_footer_html = generate_top_footer_archive_links(now, OUTPUT_DIR)
    if archive_footer_html:
        footer_slide = ('<article class="slide archive-footer-slide" aria-label="アーカイブフッター">'
                       + archive_footer_html
                       + '</article>')
        slides_html += footer_slide

    parts.append('<main class="app-container">' + slides_html + '</main>')
    parts.append('</body></html>')

    full_html = "".join(parts)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print("Generated: " + out_path + " (slides: " + str(len(slides)) + ")")
    return out_path


# ============================================================
# Slide Renderers
# ============================================================
def _render_topic_slide(i, cluster, colors, time_str, iso_time, is_h3=False):
    rep = cluster['rep']
    bg_color = colors[i % len(colors)]
    cluster_size = len(cluster.get('articles', []))
    hook_text = generate_hook(cluster['core_token'], rep['title'])
    hs = cluster.get("heat_status", {})
    badge_color = hs.get("badge_color", "#ffea00")
    is_new = hs.get("is_new", False)
    new_tag = '<span class="new-tag">新着</span>' if is_new else ''
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
        posts_str = str(round(posts_num / 10000, 1)) + "万" if posts_num % 10000 != 0 else str(posts_num // 10000) + "万"
    else:
        posts_str = "{:,}".format(posts_num)
    related_html = ""
    if cluster.get('sub_reasons'):
        related_html = '<div class="related"><div class="related-label">関連</div>'
        for sub in cluster['sub_reasons']:
            sub_posts = sub['posts']
            if sub_posts >= 10000:
                sub_posts_str = str(sub_posts // 10000) + "万"
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
    parts.append('<time datetime="' + esc(iso_time) + '" class="update-badge">' + chr(0x1F504) + ' ' + esc(time_str) + ' 更新</time>')
    parts.append('<div class="content">')
    parts.append('<span class="hook-badge" role="text" style="background: ' + badge_color + ';">' + esc(hook_text) + '</span>')
    tag_name = "h3" if is_h3 else "h2"
    parts.append('<' + tag_name + ' id="heading-' + str(i) + '" class="title">' + esc(rep['title']) + '</' + tag_name + '>')
    parts.append('<p class="summary">' + esc(rep['summary']) + '</p>')
    parts.append('<footer class="meta" aria-label="ソーシャル反響">')
    parts.append('<span class="meta-icon">' + chr(0x1F525) + '</span>')
    parts.append('<span>' + posts_str + ' ポスト' + new_tag + '</span>')
    parts.append('</footer>')
    parts.append(related_html)
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">※自動取得・自動要約。背景ミスマッチ、原文のニュアンスが損なわれる場合があり、内容の正確性を保証するものではありません。</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP ↓</div>')
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
    title = esc(data.get("title", "人気ランキング"))
    items = data.get("items", [])
    items_html = ""
    for idx, item in enumerate(items[:5], 1):
        text = esc(item.get("text", ""))
        posts = item.get("posts", 0)
        if posts >= 10000:
            posts_str = str(posts // 10000) + "万"
        elif posts >= 1000:
            posts_str = str(posts // 1000) + "k"
        else:
            posts_str = str(posts)
        items_html += ('<li class="ranking-item">'
                       '<span class="ranking-num">' + str(idx) + '</span>'
                       '<span class="ranking-text">' + text + '</span>'
                       '<span class="ranking-posts">' + posts_str + ' ポスト</span>'
                       '</li>')
    parts = []
    parts.append('<article class="slide interruption-slide ranking-bg" aria-labelledby="ranking-heading-' + str(i) + '">')
    parts.append('<div class="interruption-content">')
    parts.append('<span class="interruption-badge">Ranking</span>')
    parts.append('<h2 id="ranking-heading-' + str(i) + '" class="interruption-title">' + title + '</h2>')
    parts.append('<ul class="ranking-list">' + items_html + '</ul>')
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">※自動取得・自動要約。原文のニュアンスが損なわれる場合があり、内容の正確性を保証するものではありません。</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP ↓</div>')
    parts.append('</article>')
    return "".join(parts)


def _render_promo_slide(i, data):
    badge = esc(data.get("badge", "Sponsored"))
    title = esc(data.get("title", ""))
    description = esc(data.get("description", ""))
    cta = esc(data.get("cta", "詳しく見る"))
    cta_url = esc(data.get("cta_url", "#"))
    parts = []
    parts.append('<article class="slide interruption-slide promo-bg" aria-labelledby="promo-heading-' + str(i) + '">')
    parts.append('<div class="interruption-content">')
    parts.append('<span class="interruption-badge">' + badge + '</span>')
    parts.append('<h2 id="promo-heading-' + str(i) + '" class="interruption-title">' + title + '</h2>')
    parts.append('<p class="interruption-desc">' + description + '</p>')
    parts.append('<a href="' + cta_url + '" class="interruption-cta" target="_blank" rel="noopener noreferrer">' + cta + '</a>')
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">※自動取得・自動要約。原文のニュアンスが損なわれる場合があり、内容の正確性を保証するものではありません。</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP ↓</div>')
    parts.append('</article>')
    return "".join(parts)


def _render_announcement_slide(i, data):
    badge = esc(data.get("badge", "News"))
    title = esc(data.get("title", ""))
    description = esc(data.get("description", ""))
    cta = esc(data.get("cta", "確認する"))
    cta_url = esc(data.get("cta_url", "#"))
    parts = []
    parts.append('<article class="slide interruption-slide" style="background: linear-gradient(135deg, #2ed573 0%, #1e90ff 100%);" aria-labelledby="announce-heading-' + str(i) + '">')
    parts.append('<div class="interruption-content">')
    parts.append('<span class="interruption-badge">' + badge + '</span>')
    parts.append('<h2 id="announce-heading-' + str(i) + '" class="interruption-title">' + title + '</h2>')
    parts.append('<p class="interruption-desc">' + description + '</p>')
    parts.append('<a href="' + cta_url + '" class="interruption-cta" target="_blank" rel="noopener noreferrer">' + cta + '</a>')
    parts.append('</div>')
    parts.append('<div class="disclaimer" aria-hidden="true">※自動取得・自動要約。原文のニュアンスが損なわれる場合があり、内容の正確性を保証するものではありません。</div>')
    parts.append('<div class="hint" aria-hidden="true">SWIPE UP ↓</div>')
    parts.append('</article>')
    return "".join(parts)


# ============================================================
# Sitemap Generator (v2.5 unified)
# ============================================================
def generate_sitemap(base_url="https://everflux24.github.io/Aoaeola"):
    """sitemap.xml を生成：トップページ + 全アーカイブURL"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    base = Path(OUTPUT_DIR)
    urlset = ET.Element(f"{{{SITEMAP_NS}}}urlset")

    # 1. トップページ
    _add_sitemap_url(urlset, base_url + "/", now, "always", "1.0")

    # 2. アーカイブURL（_site/archive/ 以下を自動検出）
    archive_root = base / "archive"
    if archive_root.exists():
        for html_file in sorted(archive_root.rglob("*.html")):
            rel = html_file.relative_to(base)
            url = base_url + "/" + str(rel).replace("\\", "/")
            mtime = datetime.datetime.fromtimestamp(html_file.stat().st_mtime, tz=jst)
            _add_sitemap_url(urlset, url, mtime, "weekly", "0.5")

    tree = ET.ElementTree(urlset)
    sitemap_path = base / "sitemap.xml"
    tree.write(sitemap_path, encoding="utf-8", xml_declaration=True)

    url_count = len(list(urlset.iter(f"{{{SITEMAP_NS}}}url")))
    print("Generated sitemap.xml: " + str(url_count) + " URLs")
    print("  - Top page: 1")
    print("  - Archives: " + str(url_count - 1))
    return str(sitemap_path)


def _add_sitemap_url(parent, loc, lastmod, changefreq, priority):
    """sitemapエントリを追加"""
    url = ET.SubElement(parent, f"{{{SITEMAP_NS}}}url")
    ET.SubElement(url, f"{{{SITEMAP_NS}}}loc").text = loc
    ET.SubElement(url, f"{{{SITEMAP_NS}}}lastmod").text = lastmod.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    ET.SubElement(url, f"{{{SITEMAP_NS}}}changefreq").text = changefreq
    ET.SubElement(url, f"{{{SITEMAP_NS}}}priority").text = priority


# ============================================================
# robots.txt Generator
# ============================================================
def generate_robots_txt(base_url="https://everflux24.github.io/Aoaeola"):
    robots = "User-agent: *\nAllow: /\n\nSitemap: " + base_url + "/sitemap.xml"
    robots_path = os.path.join(OUTPUT_DIR, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(robots)
    print("Generated: " + robots_path)


# ============================================================
# Archive Generator (v2.5 - A方式)
# ============================================================
def save_archive(clusters, now, iso_time):
    """
    4時間枠アーカイブを生成（A方式：同日全再生成）。
    新規アーカイブ生成時に、同日の既存アーカイブもナビゲーションを更新して再生成する。
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    template_path = os.path.join(os.path.dirname(__file__), "templates", "archive_page.html")
    if not os.path.exists(template_path):
        print("WARNING: Archive template not found: " + template_path)
        print("  Skipping archive generation.")
        return

    # テンプレート検証
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()
    if '<base' in template_content:
        print("CRITICAL WARNING: Template contains <base> tag! Removing...")
        template_content = template_content.replace('<base target="_blank">', '')
        template_content = template_content.replace("<base target='_blank'>", '')
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix='.html')
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            f.write(template_content)
        template_path = temp_path
    else:
        print("Template validation passed: no <base> tag")

    # コンテンツカード生成関数
    def generate_content_cards(dt):
        content = ""
        for c in clusters:
            rep = c.get("rep", {})
            title = rep.get("title", "")
            summary = rep.get("summary", "")
            posts = c.get("heat", 0)
            if posts >= 10000:
                posts_str = str(round(posts / 10000, 1)) + "万"
            else:
                posts_str = "{:,}".format(posts)
            content += (
                '<article class="card">'
                '<h2>' + esc(title) + '</h2>'
                '<p>' + esc(summary) + '</p>'
                '<div class="meta">' + chr(0x1F525) + ' ' + posts_str + ' ポスト</div>'
                '</article>'
            )
        if not content.strip():
            print("WARNING: Empty content for " + str(dt))
            content = '<article class="card"><h2>データ取得中</h2><p>コンテンツを読み込めませんでした。</p></article>'
        return content

    # v2.5.1: updated_files をループ外で初期化
    all_updated_files = []
    hour_blocks = get_archive_hour_blocks(now)
    for block_time in hour_blocks:
        updated_files = regenerate_same_day_archives(
            OUTPUT_DIR, template_path, block_time, generate_content_cards
        )
        all_updated_files.extend(updated_files)

    print("Archive generated: " + str(len(list(hour_blocks))) + " new blocks, " +
          str(len(all_updated_files)) + " total files updated")


# ============================================================
# Data Fetcher
# ============================================================
def fetch_data():
    print("HTTP GET fetching data...")
    req = urllib.request.Request(TARGET_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            html = res.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("Fetch error: " + str(e))
        return None
    data = parse_html(html) if html else []
    print("Extracted " + str(len(data)) + " trends.")
    return data


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
        summary = (it.get("summary") or "詳細なし").strip()
        summary = clean_summary(summary)
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
    return data_list


# ============================================================
# Main
# ============================================================
def main():
    prev_meta = load_prev_meta()
    prev_map = {c["core_token"]: c["heat"] for c in prev_meta.get("clusters", [])}
    print("Previous clusters: " + str(len(prev_map)))

    data = fetch_data()
    if not data:
        print("No data. Build aborted (old site preserved).")
        sys.exit(1)

    clusters = cluster_articles_v21(data)
    for cluster in clusters:
        cluster_size = len(cluster.get('articles', []))
        cluster['sub_reasons'] = build_sub_reasons(cluster, cluster['rep'])
        cluster["heat_status"] = compute_heat_status(cluster, prev_map)

    save_meta(clusters)

    slides = build_slides(clusters)
    slides = inject_interruptions(slides)

    # OGP image copy
    ogp_src = os.path.join(os.path.dirname(__file__), "ogp-default.png")
    ogp_dst = os.path.join(OUTPUT_DIR, "ogp-default.png")
    if os.path.exists(ogp_src):
        shutil.copy2(ogp_src, ogp_dst)
        print("Copied: " + ogp_src + " -> " + ogp_dst)
    else:
        print("OGP image not found: " + ogp_src)

    # HTML generation
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    iso_time = now.isoformat()

    # v2.5: Archive generation FIRST (before footer link generation)
    save_archive(clusters, now, iso_time)

    generate_app_html(slides)
    generate_sitemap()
    generate_robots_txt()

    # v2.5: 365-day cleanup
    deleted = cleanup_old_archives(OUTPUT_DIR, cutoff_days=365)
    if deleted:
        print("Cleaned up " + str(len(deleted)) + " old archive directories")

    new_count = sum(1 for c in clusters if c["heat_status"]["is_new"])
    surge_count = sum(1 for c in clusters if c["heat_status"]["status"] == "surge")
    print("\nAoaeola v2.5 build complete")
    print("  Clusters: " + str(len(clusters)))
    print("  New: " + str(new_count) + " | Surge: " + str(surge_count))
    print("  Total slides: " + str(len(slides)))


if __name__ == "__main__":
    main()
