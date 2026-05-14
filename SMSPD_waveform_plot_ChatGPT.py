"""
波形繪圖（對應 SMSPD_waveform_plot_ChatGPT.m）

加速版：用多核心平行讀取與計算各電壓的最大波形，主程式統一繪圖。

執行方式：
    1) 不帶參數 — 使用「設定區」的 folder_path
       py -3.8 SMSPD_waveform_plot_ChatGPT.py

    2) 指定資料夾
       py -3.8 SMSPD_waveform_plot_ChatGPT.py -d "C:\\path\\to\\folder"

    3) 指定單一 .txt 檔（只畫該檔的波形，不畫 peak vs voltage）
       py -3.8 SMSPD_waveform_plot_ChatGPT.py -i "C:\\path\\to\\file_mV.txt"
"""

import os
import re
import time
import argparse
import numpy as np
import matplotlib.pyplot as plt
from multiprocessing import Pool, cpu_count


# =====================================================================
# 設定區 — 請依實驗環境修改
# =====================================================================

folder_path = r'E:\SMSPD_NbTiN_1\Laser\1-1\20250107\4p5\Pulse\450\10000kHz\5000nW\0degrees\20250107_230159\Pulse_450_5000nW_0degrees'

# 每個電壓檔最多看幾個事件
user_defined_event = 10001

# 一個事件的取樣點數
DATA_LENGTH = 1000

# 平行處理用幾個核心。-1 表示用滿全部
NUM_WORKERS = -1


# =====================================================================
# 工具函式
# =====================================================================
def extract_info(filename):
    """從檔名抽出 basename 和 mV 值"""
    match = re.search(r'(.*)_(\d+)_mV\.txt', filename)
    if not match:
        raise ValueError(f'檔名格式不符: {filename}')
    return match.group(1), int(match.group(2))


# =====================================================================
# 工作函式：讀一個 txt，回傳「最大波形」與「峰值」
# =====================================================================
def process_one_file(args):
    file_path, voltage, user_defined_event, DATA_LENGTH = args

    raw = np.loadtxt(file_path)
    signal = raw[:, 0] if raw.ndim == 2 else raw

    # 計算實際事件數（不超過使用者上限，且不超過資料長度）
    total_event = min(user_defined_event, len(signal) // DATA_LENGTH)

    # 重塑成 (DATA_LENGTH, total_event) 的 2D 陣列（column-major，跟 Matlab 一致）
    reshaped = np.reshape(
        signal[:total_event * DATA_LENGTH],
        (DATA_LENGTH, total_event),
        order='F',
    )

    # 找出哪一個事件的峰值最大
    column_max = np.max(reshaped, axis=0)
    max_idx = int(np.argmax(column_max))
    max_val = column_max[max_idx]
    max_waveform = reshaped[:, max_idx]

    return voltage, max_waveform, max_val


# =====================================================================
# 主程式
# =====================================================================
if __name__ == '__main__':
    t_start = time.time()

    # --- CLI 覆寫 ---
    parser = argparse.ArgumentParser(description='SMSPD waveform plot')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--input', metavar='FILE', help='單一 *_mV.txt 檔')
    group.add_argument('-d', '--dir',   metavar='DIR',  help='含 *_mV.txt 的資料夾')
    cli = parser.parse_args()

    if cli.input:
        folder_path = os.path.dirname(os.path.abspath(cli.input))
        all_files = [os.path.basename(cli.input)]
    elif cli.dir:
        folder_path = cli.dir
        all_files = [f for f in os.listdir(folder_path) if f.endswith('_mV.txt')]
    else:
        all_files = [f for f in os.listdir(folder_path) if f.endswith('_mV.txt')]

    if not all_files:
        raise RuntimeError('No text file is found!')

    file_with_voltage = [(f, extract_info(f)[1]) for f in all_files]
    file_with_voltage.sort(key=lambda x: x[1])
    Va = np.array([v for _, v in file_with_voltage])
    basename = extract_info(file_with_voltage[0][0])[0]
    num_va = len(Va)

    # 決定 worker 數
    n_workers = cpu_count() if NUM_WORKERS == -1 else NUM_WORKERS
    print(f'使用 {n_workers} 個核心平行處理 {num_va} 個檔案')

    # 平行處理：每個 worker 讀一個檔、回傳該電壓的最大波形
    args_list = [
        (os.path.join(folder_path, f), v, user_defined_event, DATA_LENGTH)
        for f, v in file_with_voltage
    ]
    with Pool(processes=n_workers) as pool:
        results = pool.map(process_one_file, args_list)

    # 整理結果到固定大小的陣列
    max_s1_data = np.zeros((DATA_LENGTH, num_va))
    peak_max_values = np.zeros(num_va)
    for k, (_, waveform, max_val) in enumerate(results):
        max_s1_data[:, k] = waveform
        peak_max_values[k] = max_val

    # =================================================================
    # 繪圖：所有電壓的最大波形
    # =================================================================
    print('Generating plots...')
    plt.figure(figsize=(10, 6))
    for k in range(num_va):
        plt.plot(max_s1_data[:, k], label=f'{Va[k]} mV')
    plt.title('Max s1 Data Across Voltages')
    plt.xlabel('Data Index')
    plt.ylabel('s1 Value')
    plt.grid(True)
    plt.legend(fontsize=8, loc='best')
    waveform_png = os.path.join(folder_path, f'{basename}_waveform.png')
    plt.savefig(waveform_png, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  存檔: {waveform_png}')

    # =================================================================
    # 繪圖：峰值對電壓
    # =================================================================
    plt.figure(figsize=(8, 5))
    plt.plot(Va, peak_max_values, '-o')
    plt.title('Peak Max Value vs Voltage')
    plt.xlabel('Voltage (mV)')
    plt.ylabel('Peak Max Value')
    plt.grid(True)
    peakV_png = os.path.join(folder_path, f'{basename}_peakToVoltage.png')
    plt.savefig(peakV_png, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  存檔: {peakV_png}')

    # =================================================================
    # 輸出 peak vs voltage 數值資料
    # =================================================================
    F = np.column_stack([Va, peak_max_values])
    peakV_txt = os.path.join(folder_path, f'{basename}_peakToVoltage.txt')
    np.savetxt(peakV_txt, F, fmt='%14.7e')
    print(f'  存檔: {peakV_txt}')

    print(f'Done. Elapsed: {time.time() - t_start:.2f} s')
