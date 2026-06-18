"""
Aoaeola Archive Utilities v2.5
- 4時間枠アーカイブ生成
- 背景グラデーション（トークンハッシュから決定的に生成）
- 365日ローリングクリーンアップ
"""
import hashlib
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


JST = timezone(timedelta(hours=9))


def get_color_from_token(token: str) -> dict:
    """
    トークン文字列から決定的なHSLグラデーションを生成。
    同じトークンは常に同じ色を返す。
    """
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    # 色相: 0-360
    hue_start = int(h[0:4], 16) % 360
    hue_end = (hue_start + 40) % 360  # 40度ずらした補色系
    return {
        "start": f"hsl({hue_start}, 70%, 45%)",
        "end": f"hsl({hue_end}, 70%, 55%)",
        "hue_start": hue_start,
        "hue_end": hue_end,
    }


def get_archive_path(base_dir: str, dt: datetime) -> Path:
    """archive/YYYY/MM/DD/HH-00.html のパスを生成"""
    return Path(base_dir) / f"archive/{dt.year}/{dt.month:02d}/{dt.day:02d}/{dt.hour:02d}-00.html"


def get_archive_hour_blocks(dt: datetime) -> list:
    """
    指定日時を含む4時間枠の開始時刻リストを返す。
    0,4,8,12,16,20 のどれかに丸める。
    """
    return [
        dt.replace(hour=h, minute=0, second=0, microsecond=0)
        for h in range(0, 24, 4)
    ]


def cleanup_old_archives(base_dir: str, cutoff_days: int = 365) -> list:
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


def get_recent_archive_links(base_dir: str, days: int = 7) -> list:
    """
    過去N日分のアーカイブ日付リンク情報を返す。
    各日付の最新HTMLファイルへの直接リンクを生成。
    戻り値: [{"date_str": "06/17", "path": "archive/2026/06/17/16-00.html", "has_data": True}, ...]
    """
    archive_root = Path(base_dir).resolve() / "archive"
    links = []
    today = datetime.now(JST)

    for i in range(days):
        d = today - timedelta(days=i)
        date_path = archive_root / f"{d.year}/{d.month:02d}/{d.day:02d}"
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
            path = f"archive/{d.year}/{d.month:02d}/{d.day:02d}/{html_file}"
        else:
            path = f"archive/{d.year}/{d.month:02d}/{d.day:02d}/"

        links.append({
            "date_str": f"{d.month:02d}/{d.day:02d}",
            "path": path,
            "has_data": has_data,
        })

    return links


def generate_archive_title(dt: datetime) -> str:
    """アーカイブページの<title>を生成"""
    return f"{dt.month}月{dt.day}日 {dt.hour}時台のトレンド｜Aoaeola"
