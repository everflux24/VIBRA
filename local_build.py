#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aoaeola Archive Diagnostic Script
Tests archive generation step-by-step to identify failure points.
"""

import os
import sys
import datetime

# ============================================================
# Step 1: Environment Check
# ============================================================
print("=" * 60)
print("STEP 1: Environment Check")
print("=" * 60)

print("Python version:", sys.version)
print("Working directory:", os.getcwd())
print("VIBRA_OUTPUT_DIR:", os.environ.get("VIBRA_OUTPUT_DIR", "NOT SET"))
print("Script location (__file__):", __file__)
print("Script directory:", os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Step 2: File Existence Check
# ============================================================
print("\n" + "=" * 60)
print("STEP 2: File Existence Check")
print("=" * 60)

base_dir = os.path.dirname(os.path.abspath(__file__))
template_path = os.path.join(base_dir, "templates", "archive_page.html")
archive_utils_path = os.path.join(base_dir, "core", "archive_utils.py")

print("Template path:", template_path)
print("Template exists:", os.path.exists(template_path))

print("\nArchive utils path:", archive_utils_path)
print("Archive utils exists:", os.path.exists(archive_utils_path))

# List directory contents
print("\nDirectory listing:")
for item in os.listdir(base_dir):
    full_path = os.path.join(base_dir, item)
    if os.path.isdir(full_path):
        print("  [DIR] ", item)
        try:
            for sub in os.listdir(full_path):
                print("    -", sub)
        except PermissionError:
            print("    (permission denied)")
    else:
        print("  [FILE]", item)

# ============================================================
# Step 3: Import Test
# ============================================================
print("\n" + "=" * 60)
print("STEP 3: Import Test")
print("=" * 60)

try:
    from core.archive_utils import (
        get_color_from_token,
        get_archive_path,
        get_archive_hour_blocks,
        cleanup_old_archives,
        get_recent_archive_links,
        generate_archive_title,
    )
    print("✅ core.archive_utils imported successfully")

    # Test get_archive_hour_blocks
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    print("\nCurrent time:", now)
    blocks = get_archive_hour_blocks(now)
    print("Archive hour blocks:", blocks)
    print("Number of blocks:", len(blocks))

except Exception as e:
    print("❌ Import failed:", str(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================
# Step 4: Template Load Test
# ============================================================
print("\n" + "=" * 60)
print("STEP 4: Template Load Test")
print("=" * 60)

try:
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    print("✅ Template loaded successfully")
    print("Template size:", len(template), "bytes")
    print("Template first 200 chars:")
    print(template[:200])
except Exception as e:
    print("❌ Template load failed:", str(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================
# Step 5: Archive Path Generation Test
# ============================================================
print("\n" + "=" * 60)
print("STEP 5: Archive Path Generation Test")
print("=" * 60)

OUTPUT_DIR = os.environ.get("VIBRA_OUTPUT_DIR", ".")
print("OUTPUT_DIR:", OUTPUT_DIR)

try:
    for block_time in blocks:
        archive_file = get_archive_path(OUTPUT_DIR, block_time)
        print("Archive file path:", archive_file)
        print("Archive parent exists:", archive_file.parent.exists())

        # Try to create directory
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        print("✅ Directory created/verified")

        # Try to write test file
        test_content = "<!-- test -->"
        with open(archive_file, "w", encoding="utf-8") as f:
            f.write(test_content)
        print("✅ Test archive file written")

        # Verify
        if os.path.exists(archive_file):
            print("✅ File exists after write")
            print("File size:", os.path.getsize(archive_file))
        else:
            print("❌ File does not exist after write!")

except Exception as e:
    print("❌ Archive path generation failed:", str(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================
# Step 6: Full Archive Write Test
# ============================================================
print("\n" + "=" * 60)
print("STEP 6: Full Archive Write Test")
print("=" * 60)

try:
    colors = get_color_from_token("test")
    print("Colors:", colors)

    # Simulate minimal save_archive logic
    html = template.replace("{{archive_title}}", "Test Title")
    html = html.replace("{{canonical_url}}", "https://example.com/test")
    html = html.replace("{{gradient_start}}", colors["start"])
    html = html.replace("{{gradient_end}}", colors["end"])
    html = html.replace("{{hue_start}}", str(colors["hue_start"]))
    html = html.replace("{{iso_datetime}}", blocks[0].isoformat())
    html = html.replace("{{display_datetime}}", blocks[0].strftime("%Y年%m月%d日 %H:%M"))
    html = html.replace("{{content_cards}}", "<p>Test content</p>")
    html = html.replace("{{generation_time}}", now.strftime("%Y-%m-%d %H:%M:%S"))

    archive_file = get_archive_path(OUTPUT_DIR, blocks[0])
    with open(archive_file, "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Full archive file written")
    print("File size:", os.path.getsize(archive_file))

    # List output directory
    print("\nOutput directory contents:")
    output_path = os.path.join(OUTPUT_DIR, "archive")
    if os.path.exists(output_path):
        for root, dirs, files in os.walk(output_path):
            level = root.replace(output_path, "").count(os.sep)
            indent = " " * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = " " * 2 * (level + 1)
            for file in files:
                print(f"{subindent}{file}")
    else:
        print("  (archive directory not found)")

except Exception as e:
    print("❌ Full archive write failed:", str(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
