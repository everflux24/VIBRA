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
