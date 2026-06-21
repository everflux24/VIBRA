#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aoaeola Archive Utilities v2.5
- 4時間枠アーカイブ生成（現在時刻を含む1枠のみ）
- 背景グラデーション（トークンハッシュから決定的に生成）
- 365日ローリングクリーンアップ
- 直接HTMLファイルリンク
NO f-string VERSION
"""
import hashlib
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

def get_color_from_token(token):
    """
    トークン文字列から決定的なHSLグラデーションを生成。
    同じトークンは常に同じ色を返す。
    """
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    # 色相: 0-360
    hue_start = int(h[0:4], 16) % 360
    hue_end = (hue_start + 40) % 360  # 40度ずらした補色系
    return {
        "start": "hsl(" + str(hue_start) + ", 70%, 45%)",
        "end": "hsl(" + str(hue_end) + ", 70%, 55%)",
        "hue_start": hue_start,
        "hue_end": hue_end,
    }

def get_archive_path(base_dir, dt):
    """archive/YYYY/MM/DD/HH-00.html のパスを生成"""
    return Path(base_dir) / ("archive/" + str(dt.year) + "/" + "{:02d}".format(dt.month) + "/" + "{:02d}".format(dt.day) + "/" + "{:02d}".format(dt.hour) + "-00.html")

def get_archive_hour_blocks(dt):
    """
    指定日時を含む4時間枠の開始時刻を1つのみ返す。
    0,4,8,12,16,20 のどれかに丸める。
    """
    hour_block = (dt.hour // 4) * 4
    return [dt.replace(hour=hour_block, minute=0, second=0, microsecond=0)]

def cleanup_old_archives(base_dir, cutoff_days=365):
    """
    cutoff_days 日より古い archive/YYYY/MM/DD/ ディレクトリを削除。
    削除したパスのリストを返す。
    """
    archive_root = Path(base_dir) / "archive"
    if not archive_root.exists():
        return []

    cutoff = datetime.now(JST) - timedelta(days=cutoff_days)
    deleted = []

    for year_dir in archive_root.iterdir():
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = int(year_dir.name)
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            month = int(month_dir.name)
            for day_dir in month_dir.iterdir():
                if not day_dir.is_dir() or not day_dir.name.isdigit():
                    continue
                day = int(day_dir.name)
                try:
                    dir_date = datetime(year, month, day, tzinfo=JST)
                except ValueError:
                    continue
                if dir_date < cutoff:
                    shutil.rmtree(day_dir)
                    deleted.append(str(day_dir))
                    # 空になった親ディレクトリも削除
                    if not any(month_dir.iterdir()):
                        month_dir.rmdir()
                    if not any(year_dir.iterdir()):
                        year_dir.rmdir()

    return deleted

def get_recent_archive_links(base_dir, days=7):
    """
    過去N日分のアーカイブ日付リンク情報を返す。
    各日付のHTMLファイルへの直接リンクを生成。
    戻り値: [{"date_str": "06/17", "path": "archive/2026/06/17/16-00.html", "has_data": True}, ...]
    """
    archive_root = Path(base_dir).resolve() / "archive"
    links = []
    today = datetime.now(JST)

    for i in range(days):
        d = today - timedelta(days=i)
        date_path = archive_root / (str(d.year) + "/" + "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day))
        has_data = date_path.exists() and any(date_path.iterdir())

        # 日付ディレクトリ内のHTMLファイルを探す
        html_file = ""
        if has_data:
            try:
                html_files = sorted([f.name for f in date_path.iterdir() if f.suffix == ".html"])
                if html_files:
                    html_file = html_files[-1]  # 最新のファイル
            except (OSError, PermissionError):
                pass

        if html_file:
            path = "archive/" + str(d.year) + "/" + "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day) + "/" + html_file
        else:
            path = "archive/" + str(d.year) + "/" + "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day) + "/"

        links.append({
            "date_str": "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day),
            "path": path,
            "has_data": has_data,
        })

    return links

def generate_archive_title(dt):
    """アーカイブページの<title>を生成"""
    return "{:02d}".format(dt.month) + "月" + "{:02d}".format(dt.day) + "日 " + "{:02d}".format(dt.hour) + "時台のトレンド｜Aoaeola"

def get_same_day_hour_links(base_dir, current_dt):
    """
    同じ日の全4時間枠アーカイブリンクを生成。
    戻り値: [{"url": "04-00.html", "text": "04:00", "is_current": True}, ...]
    """
    links = []
    for h in range(0, 24, 4):
        file_name = "{:02d}-00.html".format(h)
        file_path = os.path.join(
            base_dir, "archive", str(current_dt.year),
            "{:02d}".format(current_dt.month), "{:02d}".format(current_dt.day),
            file_name
        )
        is_current = (h == current_dt.hour)
        has_file = os.path.exists(file_path)
        links.append({
            "url": file_name,
            "text": "{:02d}:00".format(h),
            "is_current": is_current,
            "has_file": has_file,
        })
    return links

def get_same_day_hour_nav_html(base_dir, current_dt):
    """
    同じ日の4時間枠ナビゲーションHTMLを生成。
    """
    links = get_same_day_hour_links(base_dir, current_dt)
    html_parts = ['<nav class="hour-blocks-nav">']
    html_parts.append('<div class="hour-blocks-label">本日のアーカイブ</div>')
    html_parts.append('<div class="hour-blocks-links">')
    for link in links:
        if link["has_file"]:
            cls = "hour-block-link"
            if link["is_current"]:
                cls = "hour-block-link current"
            html_parts.append(
                '<a href="' + link["url"] + '" class="' + cls + '">' + link["text"] + '</a>'
            )
        else:
            html_parts.append('<span class="hour-block-link empty">' + link["text"] + '</span>')
    html_parts.append('</div></nav>')
    return "".join(html_parts)

def get_adjacent_archive_links(base_dir, dt):
    """
    指定日時の前後4時間枠のアーカイブリンクを生成。
    ファイルが存在する場合のみリンクを返す。
    戻り値: {"prev": {"url": "...", "text": "..."}, "next": {...}} または None
    """
    links = {"prev": None, "next": None}
    jst = timezone(timedelta(hours=9))

    # 前の4時間枠
    prev_hour = dt.hour - 4
    prev_dt = dt
    if prev_hour < 0:
        prev_hour = 20
        prev_dt = dt - timedelta(days=1)
    prev_path = os.path.join(
        base_dir, "archive", str(prev_dt.year),
        "{:02d}".format(prev_dt.month), "{:02d}".format(prev_dt.day),
        "{:02d}-00.html".format(prev_hour)
    )
    if os.path.exists(prev_path):
        rel_path = ("archive/" + str(prev_dt.year) + "/" +
                    "{:02d}".format(prev_dt.month) + "/" +
                    "{:02d}".format(prev_dt.day) + "/" +
                    "{:02d}".format(prev_hour) + "-00.html")
        links["prev"] = {
            "url": rel_path,
            "text": ("{:02d}".format(prev_dt.month) + "/" +
                     "{:02d}".format(prev_dt.day) + " " +
                     "{:02d}".format(prev_hour) + ":00")
        }

    # 次の4時間枠
    next_hour = dt.hour + 4
    next_dt = dt
    if next_hour >= 24:
        next_hour = 0
        next_dt = dt + timedelta(days=1)
    next_path = os.path.join(
        base_dir, "archive", str(next_dt.year),
        "{:02d}".format(next_dt.month), "{:02d}".format(next_dt.day),
        "{:02d}-00.html".format(next_hour)
    )
    if os.path.exists(next_path):
        rel_path = ("archive/" + str(next_dt.year) + "/" +
                    "{:02d}".format(next_dt.month) + "/" +
                    "{:02d}".format(next_dt.day) + "/" +
                    "{:02d}".format(next_hour) + "-00.html")
        links["next"] = {
            "url": rel_path,
            "text": ("{:02d}".format(next_dt.month) + "/" +
                     "{:02d}".format(next_dt.day) + " " +
                     "{:02d}".format(next_hour) + ":00")
        }

    return links

def get_archive_nav_html(base_dir, current_dt, days=7):
    """
    アーカイブページ内に表示する過去N日のアーカイブナビゲーションHTMLを生成。
    """
    links = get_recent_archive_links(base_dir, days=days)
    current_date_str = "{:02d}/{:02d}".format(current_dt.month, current_dt.day)
    html_parts = ['<nav class="archive-nav">']
    html_parts.append('<div class="archive-nav-label">過去7日のアーカイブ</div>')
    html_parts.append('<div class="archive-nav-links">')
    for link in links:
        if link["has_data"]:
            cls = "archive-nav-link"
            if link["date_str"] == current_date_str:
                cls = "archive-nav-link current"
            html_parts.append(
                '<a href="' + link["path"] + '" class="' + cls + '">' + link["date_str"] + '</a>'
            )
        else:
            html_parts.append('<span class="archive-nav-link empty">' + link["date_str"] + '</span>')
    html_parts.append('</div></nav>')
    return "".join(html_parts)



def safe_replace(template, key, value):
    """<!--KEY-->形式のプレースホルダーを安全に置換"""
    return template.replace("<!--" + key + "-->", value)


def extract_content_cards(html):
    """HTMLから content-cards 部分を抽出"""
    match = re.search(r'<main class="content-cards">(.*?)</main>', html, re.S)
    if match:
        return match.group(1).strip()
    return ""


def render_single_archive_page(base_dir, template_path, dt, content_cards_html):
    """
    単一アーカイブページをレンダリング（安全な置換）。
    """
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    adj = get_adjacent_archive_links(base_dir, dt)
    pager = get_archive_pager_html(adj)
    hour_nav = get_same_day_hour_nav_html(base_dir, dt)
    archive_nav = get_archive_nav_html(base_dir, dt, days=7)

    result = template
    result = safe_replace(result, "ARCHIVE_TITLE", generate_archive_title(dt))
    result = safe_replace(result, "CANONICAL_URL",
        "https://everflux24.github.io/Aoaeola/archive/" +
        str(dt.year) + "/" + "{:02d}".format(dt.month) + "/" +
        "{:02d}".format(dt.day) + "/" + "{:02d}".format(dt.hour) + "-00.html")
    result = safe_replace(result, "DISPLAY_DATETIME",
        str(dt.year) + "年" + "{:02d}".format(dt.month) + "月" +
        "{:02d}".format(dt.day) + "日 " + "{:02d}".format(dt.hour) + ":00")
    result = safe_replace(result, "ISO_DATETIME", dt.isoformat())
    result = safe_replace(result, "PAGER_TOP", pager)
    result = safe_replace(result, "HOUR_BLOCKS_NAV", hour_nav)
    result = safe_replace(result, "CONTENT_CARDS", content_cards_html)
    result = safe_replace(result, "PAGER_BOTTOM", pager)
    result = safe_replace(result, "ARCHIVE_NAV", archive_nav)
    result = safe_replace(result, "GENERATION_TIME",
        datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"))

    return result


def save_archive_page(base_dir, dt, html_content):
    """アーカイブページをファイルに保存"""
    path = get_archive_path(base_dir, dt)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return str(path)


def regenerate_same_day_archives(base_dir, template_path, current_dt, content_generator):
    """
    A方式核心：同日全アーカイブ再生成 + 既存コンテンツ保持 + 前後日隣接枠更新。
    新規アーカイブ生成時に、同日の既存アーカイブもナビゲーションを更新して再生成する。
    """
    updated_files = []

    # 1. 同日の全4時間枠をスキャン
    same_day_hours = []
    for h in range(0, 24, 4):
        file_path = os.path.join(base_dir, "archive", str(current_dt.year),
                                 "{:02d}".format(current_dt.month), "{:02d}".format(current_dt.day),
                                 "{:02d}-00.html".format(h))
        if os.path.exists(file_path):
            same_day_hours.append(h)

    current_hour = current_dt.hour
    if current_hour not in same_day_hours:
        same_day_hours.append(current_hour)
    same_day_hours = sorted(set(same_day_hours))

    # 2. 同日の全枠を再生成（既存コンテンツを保持）
    for h in same_day_hours:
        dt = current_dt.replace(hour=h, minute=0, second=0, microsecond=0)
        file_path = get_archive_path(base_dir, dt)

        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                existing_html = f.read()
            content = extract_content_cards(existing_html)
        else:
            content = content_generator(dt)

        html = render_single_archive_page(base_dir, template_path, dt, content)
        path = save_archive_page(base_dir, dt, html)
        updated_files.append(path)

    # 3. 前日の最後の枠を更新（次へリンクを更新するため）
    prev_dt = current_dt - timedelta(days=1)
    prev_hour = 20
    prev_path = os.path.join(base_dir, "archive", str(prev_dt.year),
                             "{:02d}".format(prev_dt.month), "{:02d}".format(prev_dt.day),
                             "{:02d}-00.html".format(prev_hour))
    if os.path.exists(prev_path):
        dt = prev_dt.replace(hour=prev_hour, minute=0, second=0, microsecond=0)
        with open(prev_path, "r", encoding="utf-8") as f:
            existing_html = f.read()
        content = extract_content_cards(existing_html)
        html = render_single_archive_page(base_dir, template_path, dt, content)
        path = save_archive_page(base_dir, dt, html)
        updated_files.append(path)

    # 4. 翌日の最初の枠を更新（前へリンクを更新するため）
    next_dt = current_dt + timedelta(days=1)
    next_hour = 0
    next_path = os.path.join(base_dir, "archive", str(next_dt.year),
                             "{:02d}".format(next_dt.month), "{:02d}".format(next_dt.day),
                             "{:02d}-00.html".format(next_hour))
    if os.path.exists(next_path):
        dt = next_dt.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        with open(next_path, "r", encoding="utf-8") as f:
            existing_html = f.read()
        content = extract_content_cards(existing_html)
        html = render_single_archive_page(base_dir, template_path, dt, content)
        path = save_archive_page(base_dir, dt, html)
        updated_files.append(path)

    return updated_files
