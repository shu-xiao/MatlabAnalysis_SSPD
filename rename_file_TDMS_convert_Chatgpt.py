"""
TDMS -> txt 自動轉換器（對應 rename_file_TDMS_convert_Chatgpt.m）

功能：
    自動掃描 folder_path 內所有 .tdms 檔，把每個檔案的訊號(signal)與觸發(trigger)
    存成兩欄 ASCII 文字檔，輸出到子資料夾。

執行步驟：
    1. 編輯下方「設定區」的路徑
    2. 在命令列執行：py -3.8 rename_file_TDMS_convert_Chatgpt.py
"""

import os
import re
import warnings
import numpy as np
from nptdms import TdmsFile


# =====================================================================
# 設定區 — 請依實驗環境修改
# =====================================================================

# TDMS 檔所在的資料夾
folder_path = r'E:\SMSPD_NbTiN_1\Laser\1-1\20250108\12\Pulse\450\10000kHz\800nW\0degrees\20250108_011217'

# 輸出資料夾（一般和 folder_path 相同）
Save_Adress = folder_path

# 實驗參數字串（會出現在輸出檔名前面）
Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_450_800nW_0degrees_'


# =====================================================================
# 主程式
# =====================================================================

# 從 Exp_para 抓出 "Pulse_xxx_xxxnW_xxxdegrees" 當輸出子資料夾名稱
match = re.search(r'Pulse_\d+_\d+nW_\d+degrees', Exp_para)
dir_name = match.group(0) if match else 'output'

# 列出資料夾內所有 .tdms 檔
file_list = [f for f in os.listdir(folder_path) if f.lower().endswith('.tdms')]
file_list.sort()
print(f'找到 {len(file_list)} 個 .tdms 檔')

# 用一個 list 儲存每個檔案的轉換結果
converted_data = []  # 每筆 = {'voltage': int, 'signal': array, 'trigger': array}

# 逐檔讀取 TDMS
for i, filename in enumerate(file_list, start=1):
    full_path = os.path.join(folder_path, filename)

    # 從檔名中找到 _XXXmV，抓出電壓值
    voltage_match = re.search(r'_(\d+)mV', filename)
    if not voltage_match:
        warnings.warn(f'檔名中找不到電壓 (_XXXmV)，跳過: {filename}')
        continue
    voltage = int(voltage_match.group(1))

    # 讀取 TDMS
    if not os.path.isfile(full_path):
        warnings.warn(f'檔案不存在，跳過: {full_path}')
        continue

    tdms = TdmsFile.read(full_path)
    group = tdms['ADC Readout Channels']
    signal = group['chSig'][:]
    trigger = group['chTrig'][:]

    converted_data.append({
        'voltage': voltage,
        'signal': signal,
        'trigger': trigger,
    })

    print(f'{i}/{len(file_list)}  讀取成功: {filename}')

# 建立輸出子資料夾（若不存在）
output_dir = os.path.join(Save_Adress, dir_name)
if not os.path.isdir(output_dir):
    os.makedirs(output_dir)
    print(f'建立輸出資料夾: {output_dir}')

print(f'資料將輸出到: {output_dir}')

# 寫出每個 voltage 對應的 .txt
for i, data in enumerate(converted_data, start=1):
    out_filename = f'{Exp_para}{data["voltage"]}_mV.txt'
    out_path = os.path.join(output_dir, out_filename)

    # 兩欄：signal, trigger（與 .m 版本一致）
    F = np.column_stack([data['signal'], data['trigger']])

    # ASCII 格式，模擬 Matlab save -ascii 的 %14.7e
    np.savetxt(out_path, F, fmt='%14.7e')

    print(f'{i}/{len(converted_data)} 輸出: {out_filename}')

print('Done')
