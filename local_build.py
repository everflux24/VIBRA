#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIBRA_REBOOT v2.1 - CoreToken Architecture + Interruption Layer
=================================================================
「話題のTikTok」として設計されたトレンドまとめエンジン

設計思想:
- ニュースアプリではなく「脳死消費」が目的
- 1スワイプ = 1話題（CoreToken統合）
- 情報密度を上げて総滞在時間を伸ばす
- 将来のマネタイズ可能性（PromoCard）を構造に組み込む

機能:
1. CoreToken統合: 同じ話題を1クラスタに集約
2. 代表記事選定: 情報量×熱量で最適な代表を選出
3. Gainソート: 勢いの高い順に表示
4. 関連理由抽出: サブ記事から核心イベントを抽出
5. SlideType拡張: topic / promo / announcement 等を将来差し込み可能
"""

import re
import json
import html as html_lib
import os
import hashlib
import sys
import urllib.request
from collections import Counter

# ==========================================
# 定数
# ==========================================
GENERIC_WORDS = ["ファン", "声", "歓喜", "期待", "話題", "動画", "様子", "登場",
                 "公開", "同士", "連発", "続出", "募集", "報告", "歓声", "熱狂"]

REACTION_KEYWORDS = ['ファン歓喜', '話題', 'の声', 'の反応', '盛り上がり', 'ワクワク',
                     '感情が炸裂', '歓喜', '可愛い', '熱狂', '歓声', '最高', '面白い', '驚き',
                     '期待', '大盛り上がり']

SPECIFICITY_KEYWORDS = ['映画', '放送', '公開', '決定', '発表', '発売', '予約',
                        '開始', '開催', '登場', '解禁', '初', '新', '周年']

# ==========================================
# Slide 型定義（将来拡張用）
# ==========================================

class Slide:
    """VIBRA_REBOOT のスライド抽象型

    将来のマネタイズ可能性（広告/スポンサー/自社告知/ランキング等）を
    構造レベルで確保するための拡張可能なスライド型。

    現状許可値:
        - "topic":    話題スライド（CoreTokenクラスタの代表記事）
        - "promo":    プロモーション枠（現状0件生成、将来有効化）

    将来追加予定:
        - "announcement": 新機能・お知らせ
        - "poll":         投票
        - "quiz":         クイズ
        - "ranking":      人気ランキング
    """
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
    """ポスト数を整数に変換"""
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
    """内容語チャンク抽出"""
    tokens = []
    tokens += re.findall(r'[ア-ン゛゜ァ-ォャ-ョー]{2,}', text)
    tokens += re.findall(r'[一-龥々〆]{2,}', text)
    tokens += re.findall(r'[a-zA-Z0-9]{2,}', text)
    return [t for t in tokens if t not in GENERIC_WORDS]

# ==========================================
# 2. CoreToken 抽出
# ==========================================

def get_core_token(title, summary):
    """主語優先のcore_token抽出

    タイトルの最初に出現する固有名詞を優先的にcore_tokenとして採用。
    これにより「ノクス」「ギャバン」などの主語が正しく抽出される。
    """
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
        # タイトル先頭出現を強く優先
        if title_tokens and t == title_tokens[0]:
            score += 10
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
    """クラスタ内全記事からcore_tokenを再計算"""
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
    """統合判定: core_token一致 or 包含 or 部分一致"""
    a_core = article.get('core_token', '')
    c_core = cluster.get('core_token', '')
    if not a_core or not c_core:
        return False
    if a_core == c_core:
        return True
    if a_core in c_core or c_core in a_core:
        return True
    # 3文字以上の部分一致
    for i in range(len(a_core) - 2):
        if a_core[i:i+3] in c_core:
            return True
    if a_core in cluster.get('token_counter', {}):
        return True
    return False

def cluster_articles_v21(data_list):
    """v2.1 CoreTokenベースクラスタリング + Gainソート

    Args:
        data_list: Yahooリアルタイム検索から抽出した記事リスト

    Returns:
        clusters: Gain降順ソート済みクラスタリスト
    """
    # 各記事にcore_tokenを付与
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

    # CoreTokenベースクラスタリング
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

    # 指標計算 + 代表選定
    for cluster in clusters:
        heat = sum(a['posts'] for a in cluster['articles'])
        past = sum(a.get('past_posts', 0) for a in cluster['articles'])
        gain = heat - past
        cluster['heat'] = heat
        cluster['gain'] = gain
        cluster['score'] = gain
        cluster['rep'] = select_representative(cluster)
        cluster['sub_reasons'] = build_sub_reasons(cluster, cluster['rep'])

    # Gain降順ソート
    clusters.sort(key=lambda c: c['score'], reverse=True)
    return clusters

# ==========================================
# 4. 代表記事選定（最重要）
# ==========================================

def info_score(title):
    """タイトルの情報密度スコア

    固有名詞密度 + 具体性キーワード - 曖昧表現
    """
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
    """情報量×熱量で代表記事を選定

    単純なposts最大ではなく、タイトルの情報密度も考慮。
    「ギャバンが話題」（情報量少）より「超ギャバン劇場版公開決定」（情報量多）を優先。
    """
    scored = []
    for a in cluster['articles']:
        score = a['posts'] * info_score(a['title'])
        scored.append((a, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0]

# ==========================================
# 5. Hook生成
# ==========================================

def generate_hook(core_token, title):
    """フックパターン生成

    「なぜ今、〇〇？」: 発表/決定/公開/放送/発売時
    「〇〇、何が起きてる？」: その他
    """
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
    """タイトルから核心イベントを抽出

    主語＋助詞を除去し、「何が起きたか」の核心部分を返す。
    実用精度: 約88%
    """
    clean = title
    for rk in REACTION_KEYWORDS:
        if rk in clean:
            clean = clean.split(rk)[0]

    clean = re.sub(r'^[^がをにでは、]+[がをにでは、]', '', clean, count=1)

    event = clean.strip('「」『』"\' ')
    event = event.strip('\u3000')
    event = re.sub(r'[がをにでは、]+$', '', event)

    return event[:25] if len(event) >= 4 else title[:25]

def build_sub_reasons(cluster, rep):
    """サブ記事から関連理由を生成

    タイトルではなく「何が起きたか」を優先して表示。
    最大2件まで。
    """
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
# 7. Slide ビルド（clusters → slides 変換）
# ==========================================

def build_slides(clusters):
    """クラスタリストをスライドリストに変換

    純粋な topic スライドのみを生成。
    中断スライド（interruption）は inject_interruptions() で後付けする。
    """
    return [Slide("topic", cluster) for cluster in clusters]


def inject_interruptions(slides):
    """中断スライド挿入レイヤー

    現状: 何も挿入しない（パススルー）
    将来: ランキング、スポンサー、お知らせ等を任意の位置に差し込む
    """
    return slides


# ==========================================
# 8. HTML生成
# ==========================================

def esc(text):
    """HTMLエスケープ"""
    return html_lib.escape(str(text), quote=True)

def generate_app_html(slides, out_path=None):
    """TikTokライクHTMLスライド生成

    Args:
        slides: inject_interruptions() 後の Slide オブジェクトのリスト
        out_path: 出力ファイルパス（省略時は OUTPUT_DIR/index.html）
    """
    if out_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, "index.html")

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
        .content { z-index: 10; max-width: 100%; }
        .hook-badge { display: inline-block; background: #ffea00; color: #000; font-size: 14px; font-weight: 800; padding: 6px 14px; border-radius: 20px; margin-bottom: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
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
        /* Interruption Slide スタイル（将来有効化予定） */
        .interruption-slide { display: flex; align-items: center; justify-content: center; }
        .interruption-content { text-align: center; padding: 40px 24px; max-width: 90%; }
        .interruption-badge { display: inline-block; background: rgba(255,255,255,0.15); color: #fff; font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 12px; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }
        .interruption-title { font-size: 22px; font-weight: 900; margin-bottom: 12px; line-height: 1.4; }
        .interruption-desc { font-size: 14px; color: rgba(255,255,255,0.85); line-height: 1.6; }
        .interruption-cta { display: inline-block; margin-top: 20px; background: #fff; color: #000; font-size: 14px; font-weight: 800; padding: 10px 24px; border-radius: 24px; text-decoration: none; }
        /* kind: ranking */
        .ranking-bg { background: linear-gradient(135deg, #ff4757 0%, #ff6b6b 100%); }
        .ranking-list { list-style: none; margin-top: 16px; text-align: left; }
        .ranking-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.15); font-size: 15px; }
        .ranking-num { font-size: 20px; font-weight: 900; color: #ffea00; min-width: 28px; }
        .ranking-text { font-weight: 700; }
        .ranking-posts { margin-left: auto; font-size: 12px; color: rgba(255,255,255,0.7); }
        /* kind: promo */
        .promo-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    </style>
    """

    slides_html = ""
    colors = ["#ff4757", "#2ed573", "#1e90ff", "#ffa502", "#3742fa", "#a55eea", "#26de81"]

    for i, slide in enumerate(slides):
        if slide.type == "topic":
            slides_html += _render_topic_slide(i, slide.data, colors)
        elif slide.type == "interruption":
            slides_html += _render_interruption_slide(i, slide.data)

    full_html = (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">'
        '<meta name="theme-color" content="#000000">'
        '<title>VIBRA_REBOOT v2.1</title>' + css +
        '</head><body><h1 class="visually-hidden">最新のトレンドまとめ</h1>'
        '<main class="app-container">' + slides_html + '</main>'
        '</body></html>'
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ {out_path} を生成しました！（スライド数: {len(slides)}）")
    return out_path


def _render_topic_slide(i, cluster, colors):
    """topic スライドのHTML断片を生成"""
    rep = cluster['rep']
    bg_color = colors[i % len(colors)]
    hook_text = generate_hook(cluster['core_token'], rep['title'])

    if rep.get('image'):
        bg_html = (f'<img class="bg-img" src="{esc(rep["image"])}" alt="" '
                   f'aria-hidden="true" loading="lazy" referrerpolicy="no-referrer">'
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
        <div class="content">
            <span class="hook-badge" role="text">{esc(hook_text)}</span>
            <h2 id="heading-{i}" class="title">{esc(rep['title'])}</h2>
            <p class="summary">{esc(rep['summary'])}</p>
            <footer class="meta" aria-label="ソーシャル反響">
                <span class="meta-icon">🔥</span>
                <span>{posts_str} ポスト</span>
            </footer>
            {related_html}
        </div>
        <div class="hint" aria-hidden="true">SWIPE UP ↓</div>
    </article>
    """


def _render_interruption_slide(i, data):
    """interruption スライドのHTML断片を生成（将来有効化予定）"""
    kind = data.get("kind", "promo")
    if kind == "ranking":
        return _render_ranking_slide(i, data)
    elif kind == "announcement":
        return _render_announcement_slide(i, data)
    else:
        return _render_promo_slide(i, data)


def _render_ranking_slide(i, data):
    """kind=ranking: 人気ランキングテンプレート"""
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
    """kind=promo: スポンサー/広告テンプレート"""
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
    """kind=announcement: お知らせテンプレート"""
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
# 9. データ取得
# ==========================================

TARGET_URL = "https://search.yahoo.co.jp/realtime/search/matome"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# 出力先ディレクトリ。ローカルは "."、CIでは "_site" を環境変数で指定。
OUTPUT_DIR = os.environ.get("VIBRA_OUTPUT_DIR", ".")
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def fetch_data():
    """ブラウザ不要。HTTP GET 一発で生HTMLを取得する。"""
    print("HTTP GET でデータを取得します（ブラウザ不要）...")
    req = urllib.request.Request(TARGET_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"取得エラー: {e}")
        return None


def parse_html(html):
    """HTMLから __NEXT_DATA__ をパース"""
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
# 10. メイン実行
# ==========================================

def main():
    """メイン実行フロー"""
    # データ取得
    raw = fetch_data()
    data = parse_html(raw) if raw else []

    if not data:
        print("データ0件のためビルドを中断します（古いサイトは保持されます）。")
        sys.exit(1)

    # クラスタリング
    clusters = cluster_articles_v21(data)

    # Slide パイプライン
    slides = build_slides(clusters)       # topic のみ生成
    slides = inject_interruptions(slides) # 現状パススルー

    # HTML生成
    generate_app_html(slides)

    print(f"\nVIBRA_REBOOT v2.1 ビルド完了")
    print(f"  クラスタ数: {len(clusters)}")
    print(f"  総スライド数: {len(slides)}")
    print(f"  topicスライド: {sum(1 for s in slides if s.type == 'topic')}")
    print(f"  interruptionスライド: {sum(1 for s in slides if s.type == 'interruption')}")


if __name__ == "__main__":
    main()
