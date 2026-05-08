"""
Python port of SNSPD_TDMS_convert_charGPT.m
Logic mirrors the Matlab script exactly.
"""

import os
import warnings
import numpy as np
from scipy.io import savemat
from nptdms import TdmsFile

# === 設定區（對應 Matlab 開頭的路徑與參數）===
TDMS_Adress = r'E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\450\10000kHz\5000nW\0degrees\20240520_153645'
Save_Adress = r'E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\450\10000kHz\5000nW\0degrees\20240520_153645'
Exp_para    = 'BroadbandSMSPD_20240519_P1_Pulse_450_5000nW_0degrees_'

# 電壓範圍：對應 Matlab 的 Vol = [500:500:6000, 6100:100:8500]
Vol = np.concatenate([np.arange(500, 6001, 500), np.arange(6100, 8501, 100)])
num_files = len(Vol)

# 預分配 dT
dT = np.zeros(num_files)

# 切換到儲存目錄（對應 cd(Save_Adress)）
os.chdir(Save_Adress)

for ii, voltage in enumerate(Vol):
    filename_TDMS = os.path.join(TDMS_Adress, f"{Exp_para}{voltage}mV.tdms")
    filename_new  = os.path.join(Save_Adress, f"{Exp_para}{voltage}_mV.txt")

    # 檢查檔案是否存在（對應 exist(filename_TDMS, 'file') == 2）
    if not os.path.isfile(filename_TDMS):
        warnings.warn(f"檔案 {filename_TDMS} 不存在，跳過該檔案。")
        continue

    # 讀取 TDMS（對應 convertTDMS）
    tdms = TdmsFile.read(filename_TDMS)

    # 提取信號與觸發（對應 MeasuredData(3) = signal, MeasuredData(4) = trigger）
    group   = tdms['ADC Readout Channels']
    signal  = group['chSig'][:]
    trigger = group['chTrig'][:]

    # 存成 ASCII txt（對應 save(filename_new, 'F', '-ascii')）
    # Matlab 預設 -ascii 格式為 %14.7e (8 位有效數字，科學記號，空白分隔)
    F = np.column_stack([signal, trigger])
    np.savetxt(filename_new, F, fmt='%14.7e', delimiter='   ')

    # 計算 dT（對應 Property(15) / Property(9) * 1e-9）
    # Property(15) = 'record length', Property(9) = 'actual sample rate'
    record_length = float(tdms.properties['record length'])
    sample_rate   = float(tdms.properties['actual sample rate'])
    dT[ii] = record_length / sample_rate * 1e-9  # 奈秒

# 儲存 dT 結果（對應 save('dT_results.mat', 'dT')）
savemat(os.path.join(Save_Adress, 'dT_results.mat'), {'dT': dT})

print('Done')
