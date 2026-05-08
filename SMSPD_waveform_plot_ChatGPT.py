"""
波形繪圖（對應 SMSPD_waveform_plot_ChatGPT.m）

功能：
    從 folder_path 讀取所有 *_mV.txt 檔，
    對每個電壓找出最大波形，畫出：
      1. 所有電壓的最大波形圖
      2. peak vs voltage 圖
    並把結果存成 .png 與 .txt。

執行步驟：
    1. 編輯下方「設定區」的 folder_path
    2. 在命令列執行：py -3.8 SMSPD_waveform_plot_ChatGPT.py
"""

import os
import re
import time
import numpy as np
import matplotlib.pyplot as plt


# =====================================================================
# 設定區 — 請依實驗環境修改
# =====================================================================

folder_path = r'E:\SMSPD_NbTiN_1\Laser\1-1\20250107\4p5\Pulse\450\10000kHz\5000nW\0degrees\20250107_230159\Pulse_450_5000nW_0degrees'

# 使用者自訂的最大事件數（每個電壓資料檔最多看幾個事件）
user_defined_event = 10001

# 一個事件的取樣點數
DATA_LENGTH = 1000


# =====================================================================
# 工具函式
# =====================================================================

def extract_info(filename):
    """從檔名抽出 basename 和 mV 值。
    例如 'SMSPD_..._30000nW_0degrees_100_mV.txt' -> ('SMSPD_..._30000nW_0degrees', 100)
    """
    match = re.search(r'(.*)_(\d+)_mV\.txt', filename)
    if not match:
        raise ValueError(f'檔名格式不符（找不到 _<num>_mV.txt）: {filename}')
    return match.group(1), int(match.group(2))


# =====================================================================
# 主程式
# =====================================================================

t_start = time.time()

# 找出 folder_path 下所有 *_mV.txt 檔
all_files = [f for f in os.listdir(folder_path) if f.endswith('_mV.txt')]
if not all_files:
    raise RuntimeError('No text file is found!')

# 抽出每個檔案的電壓值，並依電壓排序
file_with_voltage = [(f, extract_info(f)[1]) for f in all_files]
file_with_voltage.sort(key=lambda x: x[1])  # 依電壓排序

file_list = [f for f, _ in file_with_voltage]
Va = np.array([v for _, v in file_with_voltage])
basename = extract_info(file_list[0])[0]
Exp_para = basename

num_va = len(Va)

# 預先配置陣列：每個電壓對應一個最大波形(1000點) 和一個峰值
max_s1_data = np.zeros((DATA_LENGTH, num_va))
peak_max_values = np.zeros(num_va)

print('Loading Data...')

# 對每個電壓檔做處理
for k in range(num_va):
    file_path = os.path.join(folder_path, file_list[k])
    print(f'  {k+1}/{num_va}: {file_list[k]}')

    if not os.path.isfile(file_path):
        print(f'  [警告] 找不到檔案：{file_path}')
        continue

    # 載入 ASCII 檔，這裡只需要 signal 那欄（第 1 欄）
    # 若檔案是兩欄，loadtxt 會回傳二維陣列；只取第 1 欄
    raw = np.loadtxt(file_path)
    if raw.ndim == 2:
        signal = raw[:, 0]
    else:
        signal = raw

    # 計算實際事件數：使用者上限與資料長度允許的最大值取小
    total_event = min(user_defined_event, len(signal) // DATA_LENGTH)

    # 把訊號重塑成 (DATA_LENGTH, total_event) 的 2D 陣列
    # 注意：Matlab 的 reshape 是 column-major，需指定 order='F' 對應
    reshaped_signal = np.reshape(
        signal[:total_event * DATA_LENGTH],
        (DATA_LENGTH, total_event),
        order='F',
    )

    # 找出哪一個事件擁有最大峰值
    column_max = np.max(reshaped_signal, axis=0)  # 每個事件的最大值
    max_idx = int(np.argmax(column_max))
    max_val = column_max[max_idx]

    max_s1_data[:, k] = reshaped_signal[:, max_idx]
    peak_max_values[k] = max_val


# =====================================================================
# 畫圖：所有電壓的最大波形
# =====================================================================

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


# =====================================================================
# 畫圖：峰值對電壓
# =====================================================================

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


# =====================================================================
# 輸出 peak vs voltage 的數值資料
# =====================================================================

print('Saving txt...')
F = np.column_stack([Va, peak_max_values])
peakV_txt = os.path.join(folder_path, f'{basename}_peakToVoltage.txt')
np.savetxt(peakV_txt, F, fmt='%14.7e')
print(f'  存檔: {peakV_txt}')

print(f'Done. Elapsed: {time.time() - t_start:.2f} s')
