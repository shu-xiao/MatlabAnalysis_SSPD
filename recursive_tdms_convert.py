"""
遞迴搜尋資料夾中的所有 .tdms 檔案，並自動呼叫現有的轉檔腳本 rename_file_TDMS_convert_Chatgpt.py 逐資料夾轉檔。

使用方式：
    python recursive_tdms_convert.py -r "D:\path\to\root"

若不指定 -r，預設從當前工作目錄開始搜尋。
"""

import os
import sys
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed


# === 使用者設定區 ===
# 這裡是給不熟悉 CLI 的使用者直接修改的路徑。
# 只要修改 ROOT_FOLDER 為要搜尋的根目錄，然後直接雙擊或執行本檔即可。
ROOT_FOLDER = r'D:\Matlab analysis\SNSPD_data'
CONVERTER_SCRIPT = 'rename_file_TDMS_convert_Chatgpt.py'
# 若你希望用命令列指定，請保留這裡的設定為空字串：ROOT_FOLDER = ''



def find_tdms_dirs(root):
    """返回 root 下所有包含 .tdms 檔案的資料夾路徑。"""
    tdms_dirs = []
    for dirpath, dirnames, filenames in os.walk(root):
        if any(fname.lower().endswith('.tdms') for fname in filenames):
            tdms_dirs.append(dirpath)
    return sorted(tdms_dirs)


def call_convert_script(python_exe, script_path, target_dir):
    """呼叫現有 TDMS 轉換腳本處理 target_dir。"""
    cmd = [python_exe, script_path, '-d', target_dir]
    print(f'=== 轉檔資料夾: {target_dir} ===')
    print('命令:', ' '.join(f'"{p}"' if ' ' in p else p for p in cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as exc:
        print(f'[警告] 無法執行轉檔指令: {target_dir}')
        print(f'        {type(exc).__name__}: {exc}')
        return False

    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(f'[警告] 轉檔失敗: {target_dir} (returncode={result.returncode})')
        if result.stderr:
            print(result.stderr)
        return False
    if result.stderr:
        print(result.stderr)
    return True


def main():
    parser = argparse.ArgumentParser(description='遞迴批次呼叫 TDMS 轉檔腳本')
    parser.add_argument('-r', '--root', default='', help='遞迴搜尋的根資料夾，預設使用設定區 ROOT_FOLDER 或當前資料夾')
    parser.add_argument('-s', '--script', default='',
                        help='要呼叫的轉檔腳本，預設使用設定區 CONVERTER_SCRIPT')
    parser.add_argument('-j', '--jobs', default='1',
                        help='平行處理資料夾數量，預設 1。若內部轉檔器已用多核心，建議保留 1。')
    args = parser.parse_args()

    root_dir = args.root.strip() or ROOT_FOLDER or '.'
    script_name = args.script.strip() or CONVERTER_SCRIPT
    root_dir = os.path.abspath(root_dir)
    script_path = os.path.abspath(script_name)

    if not os.path.isfile(script_path):
        print(f'[錯誤] 找不到轉檔腳本: {script_path}')
        sys.exit(1)

    print(f'根目錄: {root_dir}')
    print(f'轉檔腳本: {script_path}')

    tdms_dirs = find_tdms_dirs(root_dir)
    if not tdms_dirs:
        print('找不到任何 .tdms 檔案。')
        sys.exit(0)

    print(f'找到 {len(tdms_dirs)} 個含 .tdms 的資料夾。')

    success_count = 0
    fail_count = 0
    jobs = int(args.jobs) if args.jobs and int(args.jobs) > 0 else 1

    if jobs == 1:
        for tdms_dir in tdms_dirs:
            ok = call_convert_script(sys.executable, script_path, tdms_dir)
            if ok:
                success_count += 1
            else:
                fail_count += 1
    else:
        print(f'平行執行 {jobs} 個資料夾轉檔，請確認內部轉檔器的 multiprocessing 設定不會造成 CPU 過度使用。')
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = {executor.submit(call_convert_script, sys.executable, script_path, tdms_dir): tdms_dir for tdms_dir in tdms_dirs}
            for future in as_completed(futures):
                tdms_dir = futures[future]
                try:
                    ok = future.result()
                except Exception as exc:
                    print(f'[警告] {tdms_dir} 執行時發生例外: {type(exc).__name__}: {exc}')
                    ok = False
                if ok:
                    success_count += 1
                else:
                    fail_count += 1

    print('---')
    print(f'完成：成功 {success_count} 個，失敗 {fail_count} 個。')

    if fail_count:
        sys.exit(1)


if __name__ == '__main__':
    main()
