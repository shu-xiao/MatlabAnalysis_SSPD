"""
rename_old_to_new.py
Recursively rename old SMSPD txt filenames to new format.

Folder structure expected:
    root\
      └── 20250609_231205\            <- timestamp folder, TDMS files live here
          ├── file_100uA_12mV.tdms
          └── Pulse_800_300000nW_0degrees\   <- converted txt files live here
              ├── SMSPD_..._12_mV.txt
              └── SMSPD_..._15_mV.txt

Old txt format:  SMSPD_NbTiN_1_1-1_Pulse_515_30000nW_0degrees_12_mV.txt
New txt format:  SMSPD_NbTiN_1_1-1_Pulse_515nm_rep10MHz_30000nW_0degrees_100uA_12mV.txt

kHz → MHz conversion (from folder path):
  10000kHz → rep10MHz
  80000kHz → rep80MHz
"""

# =====================================================================
#  使用者設定區  (User Settings)
#  在這裡修改路徑與選項，不需要用命令列參數
# =====================================================================

# 要掃描的根目錄（支援多個路徑，不用的請留空字串 ""）
ROOT_FOLDERS = [
    r"D:\Matlab analysis\SNSPD_data\20250609\4p8K\Pulse\800\80000kHz\250000nW\90degrees\20250609_234344\Pulse_800_250000nW_90degrees",
    ""
]

# 強制指定 uA 值（填入整數，例如 100）
# 設為 None 表示自動從 TDMS 檔名讀取（建議保持 None）
FORCE_UA = None          # e.g. 100

# True = 只預覽，不實際改名；確認無誤後改成 False
DRY_RUN = False

# =====================================================================
#  以下不需修改
# =====================================================================

import os
import re
import sys
import argparse
from pathlib import Path

OLD_PATTERN = re.compile(r'^(.+?degrees)_(\d+)_mV\.txt$', re.IGNORECASE)
NEW_PATTERN = re.compile(r'_\d+uA_\d+mV\.txt$', re.IGNORECASE)


def is_old_format(filename: str) -> bool:
    return bool(OLD_PATTERN.match(filename)) and not bool(NEW_PATTERN.search(filename))


def parse_old_filename(filename: str):
    m = OLD_PATTERN.match(filename)
    if m:
        return m.group(1), int(m.group(2))
    return None, None


def extract_rep_from_path(folder: Path) -> str:
    """
    Search folder path parts for a kHz token and return repXMHz string.
      10000kHz -> 'rep10MHz',  80000kHz -> 'rep80MHz'
    Returns empty string if not found.
    """
    for part in folder.parts:
        m = re.match(r'^(\d+)[kK][hH][zZ]$', part)
        if m:
            mhz = int(m.group(1)) // 1000
            return f"rep{mhz}MHz"
    return ""


def transform_prefix(prefix: str, rep_str: str) -> str:
    """
    Add 'nm' to wavelength and insert rep rate after it.
      '...Pulse_515_30000nW_0degrees' + 'rep10MHz'
      -> '...Pulse_515nm_rep10MHz_30000nW_0degrees'
    Skips transformation if 'nm_' already present in prefix.
    """
    if "nm_" in prefix:
        return prefix
    if rep_str:
        return re.sub(r'(_Pulse_)(\d+)(_)', rf'\g<1>\2nm_{rep_str}\3', prefix, count=1)
    else:
        return re.sub(r'(_Pulse_)(\d+)(_)', rf'\g<1>\2nm\3', prefix, count=1)


def build_new_filename(prefix: str, ua: int, mv: int) -> str:
    return f"{prefix}_{ua}uA_{mv}mV.txt"


def build_ua_map(tdms_folder: Path) -> dict[int, int]:
    ua_map: dict[int, int] = {}
    try:
        entries = os.listdir(tdms_folder)
    except PermissionError:
        return ua_map
    for name in entries:
        if not name.lower().endswith('.tdms'):
            continue
        mv_m = re.search(r'_(\d+)mV', name, re.IGNORECASE)
        ua_m = re.search(r'_(\d+)uA', name, re.IGNORECASE)
        if mv_m and ua_m:
            ua_map[int(mv_m.group(1))] = int(ua_m.group(1))
    return ua_map


def process_txt_folder(
    txt_folder: Path,
    ua_override: int | None,
    dry_run: bool,
    counters: dict,
) -> None:
    old_files = sorted(f for f in os.listdir(txt_folder) if is_old_format(f))
    if not old_files:
        return

    if ua_override is None:
        ua_map = build_ua_map(txt_folder.parent)
        if not ua_map:
            ua_map = build_ua_map(txt_folder.parent.parent)
        ua_src_label = "TDMS"
    else:
        ua_map = {}
        ua_src_label = f"FORCE_UA={ua_override}"

    # Extract rep rate (kHz→MHz) from folder path
    rep_str = extract_rep_from_path(txt_folder)

    print(f"\n[{txt_folder}]")
    if ua_map:
        print(f"  uA map (mV->uA): {ua_map}")
    print(f"  rep rate: {rep_str if rep_str else '(not found in path)'}")

    for filename in old_files:
        prefix, mv = parse_old_filename(filename)
        prefix = transform_prefix(prefix, rep_str)

        if ua_override is not None:
            ua = ua_override
        elif mv in ua_map:
            ua = ua_map[mv]
        else:
            print(f"  ERROR  {filename}")
            print(f"         Cannot find uA for mV={mv}  (no TDMS match; set FORCE_UA)")
            counters['errors'] += 1
            continue

        new_name = build_new_filename(prefix, ua, mv)
        old_path = txt_folder / filename
        new_path = txt_folder / new_name
        tag = "[DRY RUN] " if dry_run else ""

        if new_path.exists() and not dry_run:
            print(f"  SKIP      {filename}  (target exists)")
            counters['skipped'] += 1
            continue

        print(f"  {tag}RENAME  {filename}")
        print(f"  {tag}    ->  {new_name}  (uA from {ua_src_label})")

        if not dry_run:
            os.rename(old_path, new_path)
            counters['renamed'] += 1
        else:
            counters['would_rename'] += 1


def find_txt_folders(root: Path) -> list[Path]:
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        p = Path(dirpath)
        if any(is_old_format(f) for f in filenames):
            result.append(p)
    return result


def run(roots: list[str], ua_override: int | None, dry_run: bool) -> None:
    valid_roots = [Path(r) for r in roots if r.strip()]

    if not valid_roots:
        print("No paths specified. Please fill in ROOT_FOLDERS in the script.")
        return

    all_folders: list[Path] = []
    for root in valid_roots:
        if not root.is_dir():
            print(f"WARNING: '{root}' is not a valid directory, skipping.")
            continue
        found = find_txt_folders(root)
        print(f"  {root}  ->  {len(found)} folder(s) with old-format files")
        all_folders.extend(found)

    if not all_folders:
        print("\nNo old-format txt files found anywhere.")
        return

    print(f"\nTotal: {len(all_folders)} folder(s) to process.")
    if dry_run:
        print("DRY RUN mode — no files will be changed.\n")

    counters = {'renamed': 0, 'skipped': 0, 'errors': 0, 'would_rename': 0}
    for folder in all_folders:
        process_txt_folder(folder, ua_override=ua_override, dry_run=dry_run, counters=counters)

    print("\n" + "=" * 60)
    if dry_run:
        print(f"Dry-run complete.  Would rename: {counters['would_rename']}  "
              f"errors: {counters['errors']}")
        print("Set DRY_RUN = False to apply changes.")
    else:
        print(f"Done.  renamed={counters['renamed']}  "
              f"skipped={counters['skipped']}  errors={counters['errors']}")


def main() -> None:
    # If called with command-line arguments, use them (overrides script settings)
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description="Rename old SMSPD txt files to new format.")
        parser.add_argument("root", nargs="+", help="Root folder(s) to scan")
        parser.add_argument("--ua", type=int, default=None, metavar="VALUE")
        parser.add_argument("--dry-run", action="store_true")
        args = parser.parse_args()
        run(args.root, ua_override=args.ua, dry_run=args.dry_run)
    else:
        # Use settings defined at the top of this file
        run(ROOT_FOLDERS, ua_override=FORCE_UA, dry_run=DRY_RUN)


if __name__ == "__main__":
    main()
