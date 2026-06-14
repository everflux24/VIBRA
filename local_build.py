#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIBRA_REBOOT v2.1 - CoreToken Architecture + Interruption Layer + Heat Delta
==========================================================================
「話題のTikTok」として設計されたトレンドまとめエンジン
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

# ==========================================
# 定数
# ==========================================

# SVG data URI favicon（外部ファイル0依存）
FAVICON_SVG = (
    '<link rel="icon" type="image/svg+xml" '
    'href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 '
    'viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E🔥%3C/text%3E%3C/svg%3E">'
)

GENERIC_WORDS = [
    "ファン", "声", "歓喜", "期待", "話題", "動画", "様子", "登場",
    "公開", "同士", "連発", "続出", "募集", "報告", "歓声", "熱狂",
    # スポーツ用語: core_token から除外
    "ホームラン", "打点", "勝利", "敗北", "引き分け", "完封", "サヨナラ",
    "逆転", "延長", "決勝", "準決勝",
]

REACTION_KEYWORDS = [
    'ファン歓喜', '話題', 'の声', 'の反応', '盛り上がり', 'ワクワク',
    '感情が炸裂', '歓喜', '可愛い', '熱狂', '歓声', '最高', '面白い', '驚き',
    '期待', '大盛り上がり'
]

SPECIFICITY_KEYWORDS = [
    '映画', '放送', '公開', '決定', '発表', '発売', '予約',
    '開始', '開催', '登場', '解禁', '初', '新', '周年'
]

# ==========================================
# Slide 型定義
# ==========================================

class Slide:
    __slots__ = ("type", "data")

    def __init__(self, slide_type: str, data: dict):
        self.type = slide_type
        self.data = data

    def to_dict(self):
        return {"type": self.type, "data": self.data}


# ==========================================
# 1. データ前処理
# ==========================================

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

def extract_tokens(text):
    tokens = []
    tokens += re.findall(r'[ア-ン゛゜ァ-ォャ-ョー]{2,}', text)
    tokens += re.findall(r'[一-龥々〆]{2,}', text)
    tokens += re.findall(r'[a-zA-Z0-9]{2,}', text)
    return [t for t in tokens if t not in GENERIC_WORDS]

# ==========================================
# 2. CoreToken 抽出
# ==========================================

def get_core_token(title, summary):
    text = title + ' ' + summary
    tokens = extract_tokens(text)
    if not tokens:
        return title[:10] if len(title) > 10 else title

    title_tokens = extract_tokens(title)
    freq = Counter(tokens)
    scored = []
    for t, count in freq.items():
        score = count * 2
        score += min(len(t), 8)
        # タイトル先頭出現を優先（+10 → +5 に緩和）
        if title_tokens and t == title_tokens[0]:
            score += 5
        elif t in title_tokens:
            score += 5
        if re.fullmatch(r'[ァ-ヴーヷ-ヺ・]+', t):
            score += 3
        if re.fullmatch(r'[一-龥々〆]{3,}', t):
            score += 2
        scored.append((t, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored else title[:10]

def update_cluster_core_token(cluster):
    all_text = ' '.join(a['title'] + ' ' + a.get('summary', '') for a in cluster['articles'])
    tokens = extract_tokens(all_text)
    freq = Counter(tokens)
    if freq:
        cluster['core_token'] = freq.most_common(1)[0][0]
        cluster['token_counter'] = dict(freq.most_common(10))
    else:
        cluster['core_token'] = cluster['articles'][0].get('core_token', 'unknown')

# ==========================================
# 3. クラスタリング
# ==========================================

def should_merge(article, cluster):
    a_core = article.get('core_token', '')
    c_core = cluster.get('core_token', '')
    if not a_core or not c_core:
        return False
    if a_core == c_core:
        return True
    # 緩和: 4文字以上のトークン同士で部分一致を許可
    if a_core in c_core or c_core in a_core:
        if len(a_core) <= 3 or len(c_core) <= 3:
            return False
        return True
    # 3文字部分一致を復活（制限付き: 両方4文字以上の場合のみ）
    if len(a_core) >= 4 and len(c_core) >= 4:
        for i in range(len(a_core) - 2):
            if a_core[i:i+3] in c_core:
                return True
    if a_core in cluster.get('token_counter', {}):
        return True
    return False

def cluster_articles_v21(data_list):
    articles = []
    for item in data_list:
        posts_num = parse_posts(item.get('posts', 0))
        core = get_core_token(item['title'], item.get('summary', ''))
        articles.append({
            'title': item['title'],
            'summary': item.get('summary', ''),
            'posts': posts_num,
            'image': item.get('image', ''),
            'positive': item.get('positive'),
            'core_token': core,
        })

    clusters = []
    for article in articles:
        merged = False
        for cluster in clusters:
            if should_merge(article, cluster):
                cluster['articles'].append(article)
                update_cluster_core_token(cluster)
                merged = True
                break
        if not merged:
            clusters.append({
                'core_token': article['core_token'],
                'token_counter': {article['core_token']: 1} if article['core_token'] else {},
                'articles': [article]
            })

    for cluster in clusters:
        heat = sum(a['posts'] for a in cluster['articles'])
        past = sum(a.get('past_posts', 0) for a in cluster['articles'])
        gain = heat - past
        cluster['heat'] = heat
        cluster['gain'] = gain
        cluster['score'] = gain
        cluster['rep'] = select_representative(cluster)
        cluster['sub_reasons'] = build_sub_reasons(cluster, cluster['rep'])

    clusters.sort(key=lambda c: c['score'], reverse=True)
    return clusters

# ==========================================
# 4. 代表記事選定
# ==========================================

def info_score(title):
    score = 0
    score += len(re.findall(r'[ア-ン]{3,}', title)) * 2
    score += len(re.findall(r'[一-龥]{2,}', title)) * 2
    for kw in SPECIFICITY_KEYWORDS:
        if kw in title:
            score += 3
    score += len(re.findall(r'\d+', title)) * 2
    vague = ['について', 'の話題', 'と話題', 'が話題', 'される', '可能性']
    for v in vague:
        if v in title:
            score -= 2
    return max(score, 1)

def select_representative(cluster):
    scored = []
    c_core = cluster.get('core_token', '')
    for a in cluster['articles']:
        score = a['posts'] * info_score(a['title'])
        # core_tokenがクラスターと一致する記事を大幅優先（代表記事の整合性確保）
        if a.get('core_token') == c_core:
            score *= 3
        scored.append((a, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0]

# ==========================================
# 5. Hook生成
# ==========================================

def generate_hook(core_token, title):
    patterns = [
        f"なぜ今、{core_token}？",
        f"{core_token}、何が起きてる？",
        f"{core_token}、ここがポイント",
    ]
    if any(w in title for w in ['発表', '決定', '公開', '放送', '発売']):
        return patterns[0]
    h = hashlib.md5(title.encode()).hexdigest()
    return patterns[int(h, 16) % 2]

# ==========================================
# 6. 関連理由抽出
# ==========================================

def extract_event(title):
    clean = title
    for rk in REACTION_KEYWORDS:
        if rk in clean:
            clean = clean.split(rk)[0]
    clean = re.sub(r'^[^がをにでは、]+[がをにでは、]', '', clean, count=1)
    event = clean.strip("\u300c\u300d\u300e\u300f\"' ")
    event = event.strip('\u3000')
    event = re.sub(r'[がをにでは、]+$', '', event)
    return event[:25] if len(event) >= 4 else title[:25]

def build_sub_reasons(cluster, rep):
    reasons = []
    seen = set()
    for a in cluster['articles']:
        if a == rep:
            continue
        event = extract_event(a['title'])
        if event and event not in seen and len(event) >= 4:
            reasons.append({'text': event, 'posts': a['posts']})
            seen.add(event)
        if len(reasons) >= 2:
            break
    return reasons

# ==========================================
# 7. Slide ビルド
# ==========================================

def build_slides(clusters):
    return [Slide("topic", cluster) for cluster in clusters]


def inject_interruptions(slides):
    return slides


# ==========================================
# 8. 前回ビルドデータ管理（キャッシュ）
# ==========================================

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
    # 修正: ディレクトリが存在しない場合は作成（初回保存時のエラー防止）
    meta_dir = os.path.dirname(META_PATH)
    if meta_dir and not os.path.exists(meta_dir):
        os.makedirs(meta_dir, exist_ok=True)

    try:
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"メタデータ保存警告: {e}")


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


# ==========================================
# 9. HTML生成
# ==========================================

def esc(text):
    return html_lib.escape(str(text), quote=True)

def generate_app_html(slides, out_path=None):
    if out_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, "index.html")

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    build_timestamp = now.strftime('%Y-%m-%d %H:%M JST')
    time_str = now.strftime("%H:%M")

    css = """
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", "Noto Sans JP", sans-serif; background: #000; color: #fff; overflow: hidden; }
        .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
        .app-container { height: 100vh; width: 100%; overflow-y: scroll; scroll-snap-type: y mandatory; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
        .app-container::-webkit-scrollbar { display: none; }
        .slide { height: 100vh; width: 100%; scroll-snap-align: start; display: flex; flex-direction: column; justify-content: flex-end; padding: 28px 24px 80px; position: relative; overflow: hidden; }
        .bg-img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; z-index: -2; filter: brightness(0.7); }
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
        /* Toast notification */
        .vibra-toast { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.8); color: #fff; font-size: 13px; font-weight: 700; padding: 10px 20px; border-radius: 20px; backdrop-filter: blur(10px); z-index: 100; animation: toastIn 0.3s ease, toastOut 0.3s ease 1.5s forwards; }
        @keyframes toastIn { from { opacity: 0; transform: translateX(-50%) translateY(10px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        @keyframes toastOut { from { opacity: 1; } to { opacity: 0; } }
    </style>
    """

    slides_html = ""
    colors = ["#ff4757", "#2ed573", "#1e90ff", "#ffa502", "#3742fa", "#a55eea", "#26de81"]

    for i, slide in enumerate(slides):
        if slide.type == "topic":
            slides_html += _render_topic_slide(i, slide.data, colors, time_str)
        elif slide.type == "interruption":
            slides_html += _render_interruption_slide(i, slide.data)

    full_html = (
        f'<!DOCTYPE html><!-- VIBRA_BUILD: {build_timestamp} --><html lang="ja"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">'
        '<meta name="theme-color" content="#000000"><meta name="google-site-verification" content="teiftQqNINv-6xUwSh2bHx9fYM2_XtNd3yhuS0e1kNQ"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"><meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0"><meta http-equiv="refresh" content="600"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"><meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">'
        '<meta name="description" content="X（Twitter）の最新話題を10分ごとに自動更新。'
        'TikTok風の縦スワイプUIで、ニュースやSNSの流行をすばやくチェックできます。">'
        '<meta property="og:title" content="X（Twitter）トレンドまとめ｜VIBRA">'
        '<meta property="og:description" content="X（Twitter）の最新話題を10分ごとに自動更新。'
        'TikTok風の縦スワイプUIで、ニュースやSNSの流行をすばやくチェックできます。">'
        '<meta property="og:type" content="website">'
        + FAVICON_SVG +
        '<title>X（Twitter）トレンドまとめ｜VIBRA</title>' + css +
        '</head><body><h1 class="visually-hidden">今日の日本トレンドまとめ</h1>'
        '<main class="app-container">' + slides_html + '</main>'
        '<script>(function(){var touchStartY=0,touchStartTime=0;var lastTapTime=0;var longPressTimer=null;var container=document.querySelector(".app-container");if(!container)return;function getShareText(slide){var titleEl=slide.querySelector("h2.title");var metaEl=slide.querySelector(".meta span:last-child");var title=titleEl?titleEl.textContent.trim():"";var meta=metaEl?metaEl.textContent.trim():"";return "🔥 "+title+"\n"+meta+"\nhttps://vibra-reboot.github.io";}function copyToClipboard(text){if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).then(function(){showToast("コピーしました");}).catch(function(){fallbackCopy(text);});}else{fallbackCopy(text);}}function fallbackCopy(text){var ta=document.createElement("textarea");ta.value=text;ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.select();try{document.execCommand("copy");showToast("コピーしました");}catch(e){showToast("コピーに失敗しました");}document.body.removeChild(ta);}function showToast(msg){var existing=document.querySelector(".vibra-toast");if(existing)existing.remove();var t=document.createElement("div");t.className="vibra-toast";t.textContent=msg;t.style.cssText="position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.8);color:#fff;font-size:13px;font-weight:700;padding:10px 20px;border-radius:20px;backdrop-filter:blur(10px);z-index:100;animation:toastIn 0.3s ease,toastOut 0.3s ease 1.5s forwards;";document.body.appendChild(t);setTimeout(function(){if(t.parentNode)t.parentNode.removeChild(t);},2000);}container.addEventListener("touchstart",function(e){touchStartY=e.touches[0].clientY;touchStartTime=Date.now();var slide=e.target.closest(".slide");if(slide){longPressTimer=setTimeout(function(){copyToClipboard(getShareText(slide));longPressTimer=null;},600);}},{passive:true});container.addEventListener("touchmove",function(e){if(longPressTimer){var dy=Math.abs(e.touches[0].clientY-touchStartY);if(dy>10){clearTimeout(longPressTimer);longPressTimer=null;}}},{passive:true});container.addEventListener("touchend",function(e){if(longPressTimer){clearTimeout(longPressTimer);longPressTimer=null;}var dy=Math.abs(e.changedTouches[0].clientY-touchStartY);var dt=Date.now()-touchStartTime;if(dy<10 && dt<300){var now=Date.now();var slide=e.target.closest(".slide");if(!slide)return;if(now-lastTapTime<300){copyToClipboard(getShareText(slide));lastTapTime=0;}else{var content=slide.querySelector(".content");if(content)content.classList.toggle("hidden");lastTapTime=now;}}},{passive:true});container.addEventListener("click",function(e){var slide=e.target.closest(".slide");if(slide){var content=slide.querySelector(".content");if(content)content.classList.toggle("hidden");}});var style=document.createElement("style");style.textContent="@keyframes toastIn{from{opacity:0;transform:translateX(-50%) translateY(10px);}to{opacity:1;transform:translateX(-50%) translateY(0);}}@keyframes toastOut{from{opacity:1;}to{opacity:0;}}";document.head.appendChild(style);})();</script>'
        '</body></html>'
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ {out_path} を生成しました！（スライド数: {len(slides)}）")
    return out_path


def generate_sitemap(base_url="https://vibra-reboot.github.io"):
    """sitemap.xml を生成"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    lastmod = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>always</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
    sitemap_path = os.path.join(OUTPUT_DIR, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"✅ {sitemap_path} を生成しました")


def generate_robots_txt(base_url="https://vibra-reboot.github.io"):
    """robots.txt を生成"""
    robots = f"""User-agent: *
Allow: /

Sitemap: {base_url}/sitemap.xml"""
    robots_path = os.path.join(OUTPUT_DIR, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(robots)
    print(f"✅ {robots_path} を生成しました")


def _render_topic_slide(i, cluster, colors, time_str):
    rep = cluster['rep']
    bg_color = colors[i % len(colors)]
    hook_text = generate_hook(cluster['core_token'], rep['title'])

    hs = cluster.get("heat_status", {})
    badge_color = hs.get("badge_color", "#ffea00")
    is_new = hs.get("is_new", False)
    new_tag = '<span class="new-tag">新着</span>' if is_new else ''

    # 画像整合性チェック: 代表記事のタイトルにクラスターのcore_tokenが含まれていれば画像を使用
    c_core = cluster.get('core_token', '')
    rep_title = rep.get('title', '')
    image_url = rep.get('image', '') if c_core in rep_title else ''

    if image_url:
        bg_html = (f'<img class="bg-img" src="{esc(image_url)}" alt="" '
                   f'aria-hidden="true" loading="lazy" decoding="async" referrerpolicy="no-referrer">'
                   f'<div class="bg-gradient" aria-hidden="true"></div>')
    else:
        bg_html = (f'<div class="bg-fallback" style="background: {bg_color};" aria-hidden="true"></div>'
                   f'<div class="bg-gradient" aria-hidden="true"></div>')

    posts_num = cluster['heat']
    if posts_num >= 10000:
        posts_str = f"{posts_num/10000:.1f}万" if posts_num % 10000 != 0 else f"{posts_num//10000}万"
    else:
        posts_str = f"{posts_num:,}"

    related_html = ""
    if cluster.get('sub_reasons'):
        related_html = '<div class="related"><div class="related-label">関連</div>'
        for sub in cluster['sub_reasons']:
            sub_posts = sub['posts']
            if sub_posts >= 10000:
                sub_posts_str = f"{sub_posts//10000}万"
            elif sub_posts >= 1000:
                sub_posts_str = f"{sub_posts//1000}k"
            else:
                sub_posts_str = str(sub_posts)
            related_html += (f'<div class="related-item">'
                             f'<span class="related-text">{esc(sub["text"])}</span>'
                             f'<span class="related-posts">🔥 {sub_posts_str}</span>'
                             f'</div>')
        related_html += '</div>'

    return f"""
    <article class="slide" aria-labelledby="heading-{i}">
        {bg_html}
        <span class="update-badge">🔄 {esc(time_str)} 更新</span>
        <div class="content">
            <span class="hook-badge" role="text" style="background: {badge_color};">{esc(hook_text)}</span>
            <h2 id="heading-{i}" class="title">{esc(rep['title'])}</h2>
            <p class="summary">{esc(rep['summary'])}</p>
            <footer class="meta" aria-label="ソーシャル反響">
                <span class="meta-icon">🔥</span>
                <span>{posts_str} ポスト{new_tag}</span>
            </footer>
            {related_html}
        </div>
        <div class="hint" aria-hidden="true">SWIPE UP ↓</div>
    </article>
    """


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
            posts_str = f"{posts//10000}万"
        elif posts >= 1000:
            posts_str = f"{posts//1000}k"
        else:
            posts_str = str(posts)
        items_html += (f'<li class="ranking-item">'
                       f'<span class="ranking-num">{idx}</span>'
                       f'<span class="ranking-text">{text}</span>'
                       f'<span class="ranking-posts">{posts_str} ポスト</span>'
                       f'</li>')

    return f"""
    <article class="slide interruption-slide ranking-bg" aria-labelledby="ranking-heading-{i}">
        <div class="interruption-content">
            <span class="interruption-badge">Ranking</span>
            <h2 id="ranking-heading-{i}" class="interruption-title">{title}</h2>
            <ul class="ranking-list">{items_html}</ul>
        </div>
        <div class="hint" aria-hidden="true">SWIPE UP ↓</div>
    </article>
    """


def _render_promo_slide(i, data):
    badge = esc(data.get("badge", "Sponsored"))
    title = esc(data.get("title", ""))
    description = esc(data.get("description", ""))
    cta = esc(data.get("cta", "詳しく見る"))
    cta_url = esc(data.get("cta_url", "#"))

    return f"""
    <article class="slide interruption-slide promo-bg" aria-labelledby="promo-heading-{i}">
        <div class="interruption-content">
            <span class="interruption-badge">{badge}</span>
            <h2 id="promo-heading-{i}" class="interruption-title">{title}</h2>
            <p class="interruption-desc">{description}</p>
            <a href="{cta_url}" class="interruption-cta" target="_blank" rel="noopener noreferrer">{cta}</a>
        </div>
        <div class="hint" aria-hidden="true">SWIPE UP ↓</div>
    </article>
    """


def _render_announcement_slide(i, data):
    badge = esc(data.get("badge", "News"))
    title = esc(data.get("title", ""))
    description = esc(data.get("description", ""))
    cta = esc(data.get("cta", "確認する"))
    cta_url = esc(data.get("cta_url", "#"))

    return f"""
    <article class="slide interruption-slide" style="background: linear-gradient(135deg, #2ed573 0%, #1e90ff 100%);" aria-labelledby="announce-heading-{i}">
        <div class="interruption-content">
            <span class="interruption-badge">{badge}</span>
            <h2 id="announce-heading-{i}" class="interruption-title">{title}</h2>
            <p class="interruption-desc">{description}</p>
            <a href="{cta_url}" class="interruption-cta" target="_blank" rel="noopener noreferrer">{cta}</a>
        </div>
        <div class="hint" aria-hidden="true">SWIPE UP ↓</div>
    </article>
    """


# ==========================================
# 10. データ取得
# ==========================================

TARGET_URL = "https://search.yahoo.co.jp/realtime/search/matome"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
OUTPUT_DIR = os.environ.get("VIBRA_OUTPUT_DIR", ".")
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def fetch_data():
    print("HTTP GET でデータを取得します（ブラウザ不要）...")
    req = urllib.request.Request(TARGET_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"取得エラー: {e}")
        return None


def parse_html(html):
    if not html:
        return []
    m = NEXT_DATA_RE.search(html)
    if not m:
        print("__NEXT_DATA__ が見つかりません（DOM構造変更の可能性）")
        return []
    try:
        data = json.loads(m.group(1))
        items = data["props"]["pageProps"]["pageData"]["matomeList"]["items"]
    except (KeyError, json.JSONDecodeError) as e:
        print(f"JSON構造の解析に失敗: {e}")
        return []

    data_list = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        summary = (it.get("summary") or "詳細なし").strip()
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
    print(f"{len(data_list)} 件のトレンドを抽出しました。")
    return data_list


# ==========================================
# 11. メイン実行
# ==========================================

def main():
    prev_meta = load_prev_meta()
    prev_map = {c["core_token"]: c["heat"] for c in prev_meta.get("clusters", [])}
    print(f"前回クラスタ数: {len(prev_map)}")

    raw = fetch_data()
    data = parse_html(raw) if raw else []

    if not data:
        print("データ0件のためビルドを中断します（古いサイトは保持されます）。")
        sys.exit(1)

    clusters = cluster_articles_v21(data)

    for cluster in clusters:
        cluster["heat_status"] = compute_heat_status(cluster, prev_map)

    save_meta(clusters)

    slides = build_slides(clusters)
    slides = inject_interruptions(slides)

    generate_app_html(slides)
    generate_sitemap()
    generate_robots_txt()

    new_count = sum(1 for c in clusters if c["heat_status"]["is_new"])
    surge_count = sum(1 for c in clusters if c["heat_status"]["status"] == "surge")
    print(f"\nVIBRA_REBOOT v2.1 ビルド完了")
    print(f"  クラスタ数: {len(clusters)}")
    print(f"  新着: {new_count} | 急上昇: {surge_count}")
    print(f"  総スライド数: {len(slides)}")


if __name__ == "__main__":
    main()
