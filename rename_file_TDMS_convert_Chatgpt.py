"""
TDMS -> txt 自動轉換器（對應 rename_file_TDMS_convert_Chatgpt.m）

加速版：用多核心同時處理多個 TDMS 檔案。

執行方式：
    1) 不帶參數 — 使用「設定區」的 folder_path
       python rename_file_TDMS_convert_Chatgpt.py

    2) 指定資料夾
       python rename_file_TDMS_convert_Chatgpt.py -d "C:\\path\\to\\folder"

    3) 指定單一檔案
       python rename_file_TDMS_convert_Chatgpt.py -i "C:\\path\\to\\file.tdms"
"""

import os
import re
import argparse
import numpy as np
from multiprocessing import Pool, cpu_count
from nptdms import TdmsFile


# =====================================================================
# 進度條工具
# =====================================================================
def _run_with_progress(pool, fn, args_list, desc='Processing'):
    """把 pool.imap_unordered 包上 tqdm 進度條；沒裝 tqdm 時自動退回純文字計數"""
    try:
        from tqdm import tqdm
        return list(tqdm(pool.imap_unordered(fn, args_list),
                         total=len(args_list), desc=desc, unit='file'))
    except ImportError:
        results = []
        n = len(args_list)
        for i, r in enumerate(pool.imap_unordered(fn, args_list), 1):
            print(f'\r  {desc}: {i}/{n}', end='', flush=True)
            results.append(r)
        print()
        return results


# =====================================================================
# 設定區 — 請依實驗環境修改
# =====================================================================

# TDMS 檔所在的資料夾
folder_path = r'E:\SMSPD_NbTiN_1\Laser\1-1\20250108\12\Pulse\450\10000kHz\800nW\0degrees\20250108_011217'

# 輸出資料夾（一般和 folder_path 相同）
Save_Adress = folder_path

# 實驗參數字串（會出現在輸出檔名前面）
Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_450_800nW_0degrees_'

# 平行處理用幾個核心。-1 表示用滿全部 CPU 核心；想保守一點可以設成 4
NUM_WORKERS = -1


# =====================================================================
# 工作函式：每個核心會分別呼叫這個函式來處理一個 TDMS 檔
# =====================================================================
def convert_one_file(args):
    filename, folder_path, output_dir, Exp_para = args
    full_path = os.path.join(folder_path, filename)

    # 從檔名抓電壓 (例如 _100mV)
    voltage_match = re.search(r'_(\d+)mV', filename)
    if not voltage_match:
        return f'[跳過] 檔名找不到電壓: {filename}'
    voltage = int(voltage_match.group(1))

    # 讀 TDMS、取出 signal 與 trigger
    tdms = TdmsFile.read(full_path)
    group = tdms['ADC Readout Channels']
    signal = group['chSig'][:]
    trigger = group['chTrig'][:]

    # 寫成兩欄 ASCII txt
    out_filename = f'{Exp_para}{voltage}_mV.txt'
    out_path = os.path.join(output_dir, out_filename)
    F = np.column_stack([signal, trigger])
    np.savetxt(out_path, F, fmt='%14.7e')

    return f'OK: {out_filename}'


# =====================================================================
# 主程式
# Windows 上使用 multiprocessing 必須包在 if __name__ == '__main__': 裡面，
# 否則 worker 啟動時會無限重複跑這段程式
# =====================================================================
if __name__ == '__main__':
    # --- CLI 覆寫 ---
    parser = argparse.ArgumentParser(description='TDMS -> txt converter')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--input', metavar='FILE', help='單一 .tdms 檔')
    group.add_argument('-d', '--dir',   metavar='DIR',  help='含 .tdms 檔的資料夾')
    cli = parser.parse_args()

    if cli.input:
        folder_path = os.path.dirname(os.path.abspath(cli.input))
        Save_Adress = folder_path
        file_list = [os.path.basename(cli.input)]
    elif cli.dir:
        folder_path = cli.dir
        Save_Adress = folder_path
        file_list = [f for f in os.listdir(folder_path) if f.lower().endswith('.tdms')]
        file_list.sort()
    else:
        file_list = [f for f in os.listdir(folder_path) if f.lower().endswith('.tdms')]
        file_list.sort()

    print(f'找到 {len(file_list)} 個 .tdms 檔')

    # 從 Exp_para 抓出 "Pulse_xxx_xxxnW_xxxdegrees" 當輸出子資料夾名稱
    match = re.search(r'Pulse_\d+_\d+nW_\d+degrees', Exp_para)
    dir_name = match.group(0) if match else 'output'

    # 建立輸出資料夾（worker 開始之前一定要先建好）
    output_dir = os.path.join(Save_Adress, dir_name)
    os.makedirs(output_dir, exist_ok=True)
    print(f'資料將輸出到: {output_dir}')

    # 決定 worker 數量
    n_workers = cpu_count() if NUM_WORKERS == -1 else NUM_WORKERS
    print(f'使用 {n_workers} 個核心平行處理')

    # 把每個 worker 需要的參數打包成一串 tuple
    args_list = [(f, folder_path, output_dir, Exp_para) for f in file_list]

    # 把工作丟給 pool（_run_with_progress 會印進度條）
    with Pool(processes=n_workers) as pool:
        _run_with_progress(pool, convert_one_file, args_list, desc='Converting TDMS')

    print('Done')
