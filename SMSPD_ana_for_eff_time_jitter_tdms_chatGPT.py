"""
效率與 time jitter 分析（對應 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.m）

功能：
    從 folder_path 讀取所有 *_mV.txt 檔，
    對每個電壓計算偵測效率（efficiency），並畫出：
      1. 訊號 s1 的波形
      2. sigma 直方圖
      3. ds1（s1 的差分）
      4. Z（事件最大-最小幅度）
    最終把 (Voltage, efficiency) 存成 .txt。

執行步驟：
    1. 編輯下方「設定區」的 folder_path
    2. 在命令列執行：py -3.8 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.py
"""

import os
import re
import time
import numpy as np
import matplotlib.pyplot as plt


# =====================================================================
# 設定區 — 請依實驗環境修改
# =====================================================================

folder_path = r'E:\SMSPD_NbTiN_1\Laser\1-1\20250107\12\Pulse\450\10000kHz\15000nW\0degrees\20250107_235851\Pulse_450_15000nW_0degrees'

# 每個電壓檔分析多少事件
Nevent = 1000

# 每個事件的取樣點數
DATA_LENGTH = 1000

# 標準差閾值（sigma threshold）：基線雜訊大於此值的事件被視為無效
stdth = 0.02

# ds1 閾值（保留與原 .m 一致，目前僅作為註解使用）
ds1th = 0.05


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
# 主程式
# =====================================================================

t_start = time.time()

# 找出所有 *_mV.txt 並依電壓排序
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

# 對每個電壓做分析
for k in range(len(Va)):
    file_path = os.path.join(folder_path, file_list[k])
    print(f'processing... {k+1}/{len(Va)}')

    # 載入 ASCII（兩欄：signal, trigger）
    d = np.loadtxt(file_path)
    signal = d[:, 0]
    trigger = d[:, 1]

    # 預先配置每個事件的統計量
    Z = np.full(Nevent, np.nan)        # 事件的最大-最小幅度
    jitter = np.full(Nevent, np.nan)   # 觸發 vs 訊號最大值的時間差
    sigma = np.zeros(Nevent)            # 事件基線雜訊
    X = 0                               # 累計偵測到光子的事件數

    # 為了在最後一個事件結束時還能畫圖，宣告 s1, ds1 預設值
    s1 = np.zeros(DATA_LENGTH)
    ds1 = np.zeros(DATA_LENGTH - 1)

    # 對每個事件處理
    for i in range(Nevent):
        # 對應 Matlab 的 r = (1:DATA_LENGTH) + DATA_LENGTH*(i)
        # i 在 Matlab 從 1 開始，這裡 Python 從 0 開始，因此用 (i+1)
        start = DATA_LENGTH * (i + 1)
        end = start + DATA_LENGTH

        # 若資料長度不足，跳過
        if end > len(signal):
            break

        s = signal[start:end]
        # 計算這個事件的標準差（雜訊水準）
        sigma[i] = np.std(s, ddof=1)  # ddof=1 對應 Matlab 的 std

        if sigma[i] <= stdth:
            s1 = s.copy()
            Z[i] = np.max(s1) - np.min(s1)
            ds1 = np.diff(s1)
            dtr = np.diff(trigger[start:end])

            # 訊號最高斜率位置 vs 觸發最高斜率位置
            nds1 = int(np.argmax(ds1))
            ntr = int(np.argmax(dtr))
            jitter[i] = ntr - nds1

            # 計算「有沒有偵測到光子」：s1 超過閾值就算 1 次
            count = int(np.sum(s1 > stdth))
            if count >= 2:
                count = 1
            X += count

    # 效率 = 偵測到光子的事件 / 有效事件
    Ef_event = int(np.sum(sigma <= stdth))
    if Ef_event > 0:
        eff[k] = X / Ef_event
    else:
        eff[k] = 0.0
        print(f'  [警告] 電壓 {Va[k]} 沒有有效事件 (sigma > {stdth})')

    # 畫圖：四連格
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
