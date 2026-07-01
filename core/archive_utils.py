#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aoaeola Archive Utilities v2.5.5 - マーカー方式（ナビ部分のみ置換）
"""
import hashlib
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_URL = "https://everflux24.github.io/Aoaeola"


def get_color_from_token(token):
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    hue_start = int(h[0:4], 16) % 360
    hue_end = (hue_start + 40) % 360
    return {
        "start": "hsl(" + str(hue_start) + ", 70%, 45%)",
        "end": "hsl(" + str(hue_end) + ", 70%, 55%)",
        "hue_start": hue_start,
        "hue_end": hue_end,
    }


def get_archive_path(base_dir, dt):
    return Path(base_dir) / ("archive/" + str(dt.year) + "/" + "{:02d}".format(dt.month) + "/" + "{:02d}".format(dt.day) + "/" + "{:02d}".format(dt.hour) + "-00.html")


def get_archive_hour_blocks(dt):
    hour_block = (dt.hour // 4) * 4
    return [dt.replace(hour=hour_block, minute=0, second=0, microsecond=0)]


def cleanup_old_archives(base_dir, cutoff_days=365):
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
                    if not any(month_dir.iterdir()):
                        month_dir.rmdir()
                    if not any(year_dir.iterdir()):
                        year_dir.rmdir()
    return deleted


def _archive_url(dt):
    """アーカイブページの絶対URLを生成"""
    return BASE_URL + "/archive/" + str(dt.year) + "/" + "{:02d}".format(dt.month) + "/" + "{:02d}".format(dt.day) + "/" + "{:02d}".format(dt.hour) + "-00.html"


def get_same_day_hour_links(base_dir, current_dt):
    """同じ日の全4時間枠リンク（絶対URL）"""
    links = []
    for h in range(0, 24, 4):
        file_name = "{:02d}-00.html".format(h)
        file_path = os.path.join(base_dir, "archive", str(current_dt.year), "{:02d}".format(current_dt.month), "{:02d}".format(current_dt.day), file_name)
        is_current = (h == current_dt.hour)
        has_file = os.path.exists(file_path)
        if has_file:
            url = BASE_URL + "/archive/" + str(current_dt.year) + "/" + "{:02d}".format(current_dt.month) + "/" + "{:02d}".format(current_dt.day) + "/" + file_name
        else:
            url = ""
        links.append({
            "url": url,
            "text": "{:02d}:00".format(h),
            "is_current": is_current,
            "has_file": has_file,
        })
    return links


def get_same_day_hour_nav_html(base_dir, current_dt):
    links = get_same_day_hour_links(base_dir, current_dt)
    html_parts = ['<nav class="hour-blocks-nav">']
    html_parts.append('<div class="hour-blocks-label">本日のアーカイブ</div>')
    html_parts.append('<div class="hour-blocks-links">')
    for link in links:
        if link["has_file"]:
            cls = "hour-block-link"
            if link["is_current"]:
                cls = "hour-block-link current"
            html_parts.append('<a href="' + link["url"] + '" class="' + cls + '">' + link["text"] + '</a>')
        else:
            html_parts.append('<span class="hour-block-link empty">' + link["text"] + '</span>')
    html_parts.append('</div></nav>')
    return "".join(html_parts)


def get_adjacent_archive_links(base_dir, dt):
    """前後4時間枠リンク（絶対URL）"""
    links = {"prev": None, "next": None}

    prev_hour = dt.hour - 4
    prev_dt = dt
    if prev_hour < 0:
        prev_hour = 20
        prev_dt = dt - timedelta(days=1)
    prev_path = os.path.join(base_dir, "archive", str(prev_dt.year), "{:02d}".format(prev_dt.month), "{:02d}".format(prev_dt.day), "{:02d}-00.html".format(prev_hour))
    if os.path.exists(prev_path):
        links["prev"] = {
            "url": _archive_url(prev_dt.replace(hour=prev_hour, minute=0, second=0, microsecond=0)),
            "text": "{:02d}".format(prev_dt.month) + "/" + "{:02d}".format(prev_dt.day) + " " + "{:02d}".format(prev_hour) + ":00"
        }

    next_hour = dt.hour + 4
    next_dt = dt
    if next_hour >= 24:
        next_hour = 0
        next_dt = dt + timedelta(days=1)
    next_path = os.path.join(base_dir, "archive", str(next_dt.year), "{:02d}".format(next_dt.month), "{:02d}".format(next_dt.day), "{:02d}-00.html".format(next_hour))
    if os.path.exists(next_path):
        links["next"] = {
            "url": _archive_url(next_dt.replace(hour=next_hour, minute=0, second=0, microsecond=0)),
            "text": "{:02d}".format(next_dt.month) + "/" + "{:02d}".format(next_dt.day) + " " + "{:02d}".format(next_hour) + ":00"
        }

    return links


def get_archive_pager_html(adj_links):
    html_parts = ['<div class="archive-pager">']
    if adj_links["prev"]:
        html_parts.append('<a href="' + adj_links["prev"]["url"] + '">← ' + adj_links["prev"]["text"] + '</a>')
    else:
        html_parts.append('<span class="disabled">← 前へ</span>')
    if adj_links["next"]:
        html_parts.append('<a href="' + adj_links["next"]["url"] + '">' + adj_links["next"]["text"] + ' →</a>')
    else:
        html_parts.append('<span class="disabled">次へ →</span>')
    html_parts.append('</div>')
    return "".join(html_parts)


def get_recent_archive_links(base_dir, days=7):
    """過去N日のアーカイブリンク（絶対URL）"""
    archive_root = Path(base_dir).resolve() / "archive"
    links = []
    today = datetime.now(JST)

    for i in range(days):
        d = today - timedelta(days=i)
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

        if html_file:
            path = BASE_URL + "/archive/" + str(d.year) + "/" + "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day) + "/" + html_file
        else:
            path = ""

        links.append({
            "date_str": "{:02d}".format(d.month) + "/" + "{:02d}".format(d.day),
            "path": path,
            "has_data": has_data,
        })

    return links


def get_archive_nav_html(base_dir, current_dt, days=7):
    """過去N日のアーカイブナビゲーション（絶対URL）"""
    links = get_recent_archive_links(base_dir, days=days)
    current_date_str = "{:02d}/{:02d}".format(current_dt.month, current_dt.day)
    html_parts = ['<nav class="archive-nav">']
    html_parts.append('<div class="archive-nav-label">過去7日のアーカイブ</div>')
    html_parts.append('<div class="archive-nav-links">')
    for link in links:
        if link["has_data"] and link["path"]:
            cls = "archive-nav-link"
            if link["date_str"] == current_date_str:
                cls = "archive-nav-link current"
            html_parts.append('<a href="' + link["path"] + '" class="' + cls + '">' + link["date_str"] + '</a>')
        else:
            html_parts.append('<span class="archive-nav-link empty">' + link["date_str"] + '</span>')
    html_parts.append('</div></nav>')
    return "".join(html_parts)


def safe_replace(template, key, value):
    return template.replace("<!--" + key + "-->", value)


def update_nav_marker(html, nav_type, new_nav_html):
    """マーカーで囲まれたナビゲーション部分を置換。コンテンツは保持。"""
    start_marker = "<!--NAV:" + nav_type + "-->"
    end_marker = "<!--/NAV:" + nav_type + "-->"
    pattern = re.escape(start_marker) + ".*?" + re.escape(end_marker)
    replacement = start_marker + "\n" + new_nav_html + "\n" + end_marker
    result = re.sub(pattern, replacement, html, flags=re.S)
    if result == html:
        # マーカーがない場合は通常のsafe_replaceをフォールバック
        result = safe_replace(html, nav_type, new_nav_html)
    return result


def generate_archive_title(dt):
    return "{:02d}".format(dt.month) + "月" + "{:02d}".format(dt.day) + "日 " + "{:02d}".format(dt.hour) + "時台のトレンド｜Aoaeola"


def render_single_archive_page(base_dir, template_path, dt, content_cards_html):
    """新規アーカイブページをレンダリング（マーカー方式）"""
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    date_token = str(dt.year) + "{:02d}".format(dt.month) + "{:02d}".format(dt.day)
    colors = get_color_from_token(date_token)

    adj = get_adjacent_archive_links(base_dir, dt)
    pager = get_archive_pager_html(adj)
    hour_nav = get_same_day_hour_nav_html(base_dir, dt)
    archive_nav = get_archive_nav_html(base_dir, dt, days=7)

    result = template
    result = safe_replace(result, "ARCHIVE_TITLE", generate_archive_title(dt))
    result = safe_replace(result, "CANONICAL_URL", _archive_url(dt))
    result = safe_replace(result, "DISPLAY_DATETIME", str(dt.year) + "年" + "{:02d}".format(dt.month) + "月" + "{:02d}".format(dt.day) + "日 " + "{:02d}".format(dt.hour) + ":00")
    result = safe_replace(result, "ISO_DATETIME", dt.isoformat())
    result = safe_replace(result, "GRADIENT_START", colors["start"])
    result = safe_replace(result, "GRADIENT_END", colors["end"])
    result = safe_replace(result, "HUE_START", str(colors["hue_start"]))
    result = safe_replace(result, "CONTENT_CARDS", content_cards_html)
    result = safe_replace(result, "GENERATION_TIME", datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"))
    result = safe_replace(result, "HOME_URL", BASE_URL + "/")

    # マーカー方式のナビゲーション
    result = update_nav_marker(result, "PAGER_TOP", pager)
    result = update_nav_marker(result, "PAGER_BOTTOM", pager)
    result = update_nav_marker(result, "HOUR_BLOCKS", hour_nav)
    result = update_nav_marker(result, "ARCHIVE_NAV", archive_nav)

    return result


def update_existing_archive_nav(base_dir, template_path, dt):
    """既存アーカイブのナビゲーション部分のみを更新。コンテンツは保持。マーカーがない場合はNone。"""
    file_path = get_archive_path(base_dir, dt)
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        existing_html = f.read()

    # マーカーがない古いファイルは更新しない（フル再生成が必要）
    if "<!--NAV:" not in existing_html:
        return None

    adj = get_adjacent_archive_links(base_dir, dt)
    pager = get_archive_pager_html(adj)
    hour_nav = get_same_day_hour_nav_html(base_dir, dt)
    archive_nav = get_archive_nav_html(base_dir, dt, days=7)

    result = existing_html
    result = update_nav_marker(result, "PAGER_TOP", pager)
    result = update_nav_marker(result, "PAGER_BOTTOM", pager)
    result = update_nav_marker(result, "HOUR_BLOCKS", hour_nav)
    result = update_nav_marker(result, "ARCHIVE_NAV", archive_nav)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result)

    return str(file_path)


def save_archive_page(base_dir, dt, html_content):
    path = get_archive_path(base_dir, dt)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return str(path)


def regenerate_same_day_archives(base_dir, template_path, current_dt, content_generator):
    """マーカー方式：同日の全アーカイブのナビゲーションを更新。新規のみコンテンツ生成。"""
    updated_files = []

    # 同日の全4時間枠をスキャン
    same_day_hours = []
    for h in range(0, 24, 4):
        file_path = os.path.join(base_dir, "archive", str(current_dt.year), "{:02d}".format(current_dt.month), "{:02d}".format(current_dt.day), "{:02d}-00.html".format(h))
        if os.path.exists(file_path):
            same_day_hours.append(h)

    current_hour = current_dt.hour
    if current_hour not in same_day_hours:
        same_day_hours.append(current_hour)
    same_day_hours = sorted(set(same_day_hours))

    # 同日の全枠を処理
    for h in same_day_hours:
        dt = current_dt.replace(hour=h, minute=0, second=0, microsecond=0)
        file_path = get_archive_path(base_dir, dt)

        if file_path.exists():
            # 既存：ナビゲーションのみ更新、コンテンツは保持
            path = update_existing_archive_nav(base_dir, template_path, dt)
            if path:
                updated_files.append(path)
                print("Updated nav: " + path)
        else:
            # 新規：フルレンダリング
            content = content_generator(dt)
            html = render_single_archive_page(base_dir, template_path, dt, content)
            path = save_archive_page(base_dir, dt, html)
            updated_files.append(path)
            print("Generated new: " + path)

    return updated_files
