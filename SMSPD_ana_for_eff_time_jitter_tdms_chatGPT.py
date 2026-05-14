"""
效率與 time jitter 分析（對應 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.m 舊版邏輯）

加速版：用 numpy 向量化一次處理所有事件，取代逐事件的 for 迴圈。
（電壓檔之間還是序列處理，因為要逐張畫圖；速度瓶頸在每個檔內部的事件迴圈）

執行方式：
    1) 不帶參數 — 使用「設定區」的 folder_path
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.py

    2) 指定資料夾
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.py -d "C:\\path\\to\\folder"

    3) 指定單一 .txt 檔
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.py -i "C:\\path\\to\\file_mV.txt"
"""

import os
import re
import time
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def _fast_loadtxt(path):
    """以 pandas C engine 解析 ASCII 數值檔，比 np.loadtxt 快 5-10×"""
    return pd.read_csv(path, sep=r'\s+', header=None,
                       dtype=np.float64, engine='c').values


# =====================================================================
# 設定區 — 請依實驗環境修改
# =====================================================================

folder_path = r'E:\SMSPD_NbTiN_1\Laser\1-1\20250107\12\Pulse\450\10000kHz\15000nW\0degrees\20250107_235851\Pulse_450_15000nW_0degrees'

# 每個電壓檔分析多少事件
Nevent = 1000

# 每個事件的取樣點數
DATA_LENGTH = 1000

# 標準差閾值：基線雜訊大於此值的事件被視為無效
stdth = 0.02

# ds1 閾值（保留與原 .m 一致，目前僅作為輸出檔名用）
ds1th = 0.05


# =====================================================================
# 工具函式
# =====================================================================
def extract_info(filename):
    match = re.search(r'(.*)_(\d+)_mV\.txt', filename)
    if not match:
        raise ValueError(f'檔名格式不符: {filename}')
    return match.group(1), int(match.group(2))


# =====================================================================
# 主程式
# =====================================================================

t_start = time.time()

# --- CLI 覆寫 ---
parser = argparse.ArgumentParser(description='SMSPD efficiency / jitter analysis')
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
file_list = [f for f, _ in file_with_voltage]
Va = np.array([v for _, v in file_with_voltage])
basename = extract_info(file_list[0])[0]

# 預配置效率陣列
eff = np.zeros(len(Va))

# 對每個電壓檔做分析
for k in range(len(Va)):
    file_path = os.path.join(folder_path, file_list[k])
    print(f'processing... {k+1}/{len(Va)}')

    # 載入 ASCII 檔（兩欄：signal, trigger）
    d = _fast_loadtxt(file_path)
    signal = d[:, 0]
    trigger = d[:, 1]

    # =================================================================
    # 對齊原 .m 的索引邏輯：
    #   for i = 1..Nevent: r = (1:DATA_LENGTH) + DATA_LENGTH*i
    # 也就是說第一段資料從 index DATA_LENGTH 開始，總共取 Nevent 段
    # 若資料長度不足，自動縮減到實際可分析的事件數
    # =================================================================
    actual_Nevent = min(Nevent, len(signal) // DATA_LENGTH - 1)

    # 把訊號重塑成 2D：每一列是一個事件，共 actual_Nevent 列、DATA_LENGTH 行
    sig_mat = signal[DATA_LENGTH : DATA_LENGTH + actual_Nevent * DATA_LENGTH] \
              .reshape(actual_Nevent, DATA_LENGTH)
    trg_mat = trigger[DATA_LENGTH : DATA_LENGTH + actual_Nevent * DATA_LENGTH] \
              .reshape(actual_Nevent, DATA_LENGTH)

    # =================================================================
    # 一次計算所有事件的統計量（這就是「向量化」的核心）
    # axis=1 表示「對每列做運算」，所以結果是長度 = actual_Nevent 的陣列
    # =================================================================

    # 每個事件的標準差（ddof=1 對應 Matlab 的 std）
    sigma = np.std(sig_mat, axis=1, ddof=1)

    # 哪些事件雜訊夠小，算有效事件
    valid = sigma <= stdth

    # 每個事件的最大-最小幅度（無效事件填 NaN）
    Z = np.full(actual_Nevent, np.nan)
    Z[valid] = sig_mat[valid].max(axis=1) - sig_mat[valid].min(axis=1)

    # 訊號與觸發的差分（找上升沿位置用）
    ds = np.diff(sig_mat, axis=1)
    dtr = np.diff(trg_mat, axis=1)

    # 每個事件中「最大斜率」的取樣位置
    nds1 = np.argmax(ds, axis=1)
    ntr = np.argmax(dtr, axis=1)

    # time jitter = 觸發上升沿位置 - 訊號上升沿位置
    jitter = np.full(actual_Nevent, np.nan)
    jitter[valid] = ntr[valid] - nds1[valid]

    # =================================================================
    # 計算效率：count = 該事件有沒有偵測到光子
    # 原 .m 邏輯：count = 樣本數 (s > stdth)；若 >= 2 則 count = 1
    # 等價於：「事件中只要有任何一個樣本 > stdth，count = 1，否則 0」
    # =================================================================
    count = (sig_mat > stdth).any(axis=1).astype(int)

    # X = 偵測到光子的有效事件數
    X = int(count[valid].sum())
    Ef_event = int(valid.sum())

    if Ef_event > 0:
        eff[k] = X / Ef_event
    else:
        eff[k] = 0.0
        print(f'  [警告] 電壓 {Va[k]} 沒有有效事件')

    # =================================================================
    # 畫圖：找出最後一個有效事件當代表，畫四連格
    # =================================================================
    valid_indices = np.where(valid)[0]
    if len(valid_indices) > 0:
        last_valid = valid_indices[-1]
        s1 = sig_mat[last_valid]
        ds1 = ds[last_valid]
    else:
        s1 = np.zeros(DATA_LENGTH)
        ds1 = np.zeros(DATA_LENGTH - 1)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    fig.suptitle(f'Voltage = {Va[k]} mV')

    axes[0, 0].plot(s1, 'g')
    axes[0, 0].set_title('Signal s1 (last valid event)')

    axes[0, 1].hist(np.sort(sigma), bins=50)
    axes[0, 1].set_title('Histogram of Sigma')

    axes[1, 0].plot(ds1, 'g')
    axes[1, 0].set_title('ds1 = diff(s1)')

    axes[1, 1].plot(Z, '.')
    axes[1, 1].set_title('Z (max - min)')

    plt.tight_layout()
    fig_path = os.path.join(folder_path, f'{basename}_{Va[k]}mV_analysis.png')
    plt.savefig(fig_path, dpi=120, bbox_inches='tight')
    plt.close(fig)


# =====================================================================
# 輸出最終 (Voltage, efficiency) 結果
# =====================================================================
F = np.column_stack([Va, eff])
output_name = f'{basename}_{ds1th}_{stdth}_mV_efficiency.txt'
output_path = os.path.join(folder_path, output_name)
np.savetxt(output_path, F, fmt='%14.7e')
print(f'save data to {output_name}')

print(f'Done. Elapsed: {time.time() - t_start:.2f} s')
