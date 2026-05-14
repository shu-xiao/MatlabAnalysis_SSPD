"""
SMSPD 效率 / time jitter / 振幅分析（互動式 HTML 版）
對應 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.m

執行方式：
    1) 不帶參數 — 使用「設定區」的 folder_path
       py -3.8 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py

    2) 指定資料夾
       py -3.8 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py -d "C:\\path\\to\\folder"

    3) 指定單一 .txt 檔
       py -3.8 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py -i "C:\\path\\to\\file_mV.txt"

跑完後用瀏覽器打開產生的 .html 檔，下拉選單可切換不同 Vb。

輸出檔案：
    - {basename}_analysis.html           ← 互動式 9 連格圖（dropdown 切 Vb）
    - {basename}_summary.html            ← Efficiency vs Bias Current 總結圖
    - {basename}_*_efficiency.txt        ← [Ib, eff, Vb, amp_mean, amp_stdev]
    - {basename}_Vmax.txt                ← 每個事件的 Vmax (Nevent × num_files)
    - {basename}_VmaxIndex.txt           ← 每個事件 Vmax 出現的位置
    - {basename}_darkcount.txt           ← 各振幅切點對應的事件數
"""

import os
import re
import time
import argparse
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================================
# ============================================================================
#                            設定區（可直接修改）
#  以下所有參數都可以調整，不需要動下方程式碼
# ============================================================================
# ============================================================================

# --------------------------------------------------------------------
# 【1】資料夾路徑
#      包含 *_mV.txt 檔案的資料夾
# --------------------------------------------------------------------
folder_path = r'E:\SNSPD\SNSPD_data\SMSPD_NbTiN_2025Jun\Laser\3-11_plasmonic90\20250701\4p8K\Pulse\515\10000kHz\10000nW\90degrees\20250701_015355\Pulse_515_10000nW_90degrees'


# --------------------------------------------------------------------
# 【2】雷射設定
#      1 = 800 nm Pulse 80 MHz（每事件 4 個 peak，每段 125 點）
#      2 = 515 nm Pulse 10 MHz（每事件 1 個 peak，每段 250 點）
# --------------------------------------------------------------------
index_setting = 2


# --------------------------------------------------------------------
# 【3】偵測閾值
# --------------------------------------------------------------------
# Pre-selection：事件基線雜訊 sigma > 此值就視為無效
STDEV_CUT = 0.05

# Selection：事件中至少有一個樣本 > 此值才算偵測到光子
V_CUT = 0.03

# 振幅切點（單位 Volt）：計算「振幅 >= 此值的事件數」
# 用於分析不同光子數的偵測率
amplitude_cut = [0.005, 0.0075, 0.010]


# --------------------------------------------------------------------
# 【4】每個檔案要分析的事件數
# --------------------------------------------------------------------
Nevent = 10000


# --------------------------------------------------------------------
# 【5】訊號分析區域（採用 MATLAB 1-indexed 寫法，與 .m 檔一致）
#      [起點, 終點]，兩端皆包含
#
#      CONTROL_REGION：沒有訊號的「背景」區段，用來算基準（mean）
#      SIGNAL_REGION ：訊號 peak 出現的區段，用來算 amplitude（max）
# --------------------------------------------------------------------

# 800 nm, 80 MHz 設定（取消註解以套用）
# CONTROL_REGION = [20, 25]
# SIGNAL_REGION  = [25, 32]

# Visible（515 nm), 10 MHz 設定
CONTROL_REGION = [50, 80]
SIGNAL_REGION  = [80, 100]


# --------------------------------------------------------------------
# 【6】HTML 輸出設定
# --------------------------------------------------------------------
# 是否把 plotly.js 嵌入 html
#   True  = 嵌入（檔案較大但離線可看）
#   False = 用 CDN（檔案小但要網路才能看）
EMBED_PLOTLY_JS = True


# ============================================================================
# ============================================================================
#                          以下為程式邏輯（不用動）
# ============================================================================
# ============================================================================

# 雷射參數表（依 index_setting 自動選用）
laserConf = {
    1: {'name': '800 nm',        'DATA_LENGTH': 125, 'NUM_PEAKS': 4},
    2: {'name': '515 nm visible', 'DATA_LENGTH': 250, 'NUM_PEAKS': 1},
}

wavelength  = laserConf[index_setting]['name']
DATA_LENGTH = laserConf[index_setting]['DATA_LENGTH']
NUM_PEAKS   = laserConf[index_setting]['NUM_PEAKS']
PEAK_LENGTH = int(np.ceil(DATA_LENGTH / NUM_PEAKS))

# 把 MATLAB 1-indexed [a, b] 轉成 Python 0-indexed [a-1:b]
def matlab_range_to_slice(r):
    return slice(r[0] - 1, r[1])

ctrl_slice = matlab_range_to_slice(CONTROL_REGION)
sig_slice  = matlab_range_to_slice(SIGNAL_REGION)


# --------------------------------------------------------------------
# 工具函式：從檔名抽 basename, Vb (mV), Ib (uA)
# --------------------------------------------------------------------
def extract_info(filename):
    m_mV     = re.search(r'_(\d+)mV', filename)
    m_uA     = re.search(r'_(\d+)uA', filename)
    m_prefix = re.search(r'^(.*?Pulse_)', filename)
    if not (m_mV and m_uA and m_prefix):
        raise ValueError(f'檔名格式不符: {filename}')
    return m_prefix.group(1), int(m_mV.group(1)), int(m_uA.group(1))


# --------------------------------------------------------------------
# Step 1: 找檔案、抽 Vb / Ib、依 Vb 排序
# --------------------------------------------------------------------
t_start = time.time()

# --- CLI 覆寫 ---
parser = argparse.ArgumentParser(description='SMSPD analysis with interactive HTML output')
group = parser.add_mutually_exclusive_group()
group.add_argument('-i', '--input', metavar='FILE', help='單一 *_mV.txt 檔')
group.add_argument('-d', '--dir',   metavar='DIR',  help='含 *_mV.txt 的資料夾')
cli = parser.parse_args()

if cli.input:
    folder_path = os.path.dirname(os.path.abspath(cli.input))
    all_files = [os.path.basename(cli.input)]
elif cli.dir:
    folder_path = cli.dir
    all_files = [f for f in os.listdir(folder_path) if f.endswith('mV.txt')]
else:
    all_files = [f for f in os.listdir(folder_path) if f.endswith('mV.txt')]

if not all_files:
    raise RuntimeError('No text file is found!')

file_table = []  # list of (filename, basename, Vb, Ib)
for f in all_files:
    bn, Vb, Ib = extract_info(f)
    file_table.append((f, bn, Vb, Ib))
file_table.sort(key=lambda x: x[2])  # 依 Vb 排序

basename  = file_table[0][1]
num_files = len(file_table)
print(f'雷射設定: {wavelength}, DATA_LENGTH={DATA_LENGTH}, PEAK_LENGTH={PEAK_LENGTH}')
print(f'找到 {num_files} 個檔案')


# --------------------------------------------------------------------
# Step 2: 預先配置儲存陣列
# --------------------------------------------------------------------
eff             = np.zeros(num_files)
amplitude_mean  = np.zeros(num_files)
amplitude_stdev = np.zeros(num_files)
amplitude_effi  = np.zeros((num_files, len(amplitude_cut)), dtype=int)
VmaxArray       = np.zeros((Nevent, num_files))
VmaxIndexArray  = np.zeros((Nevent, num_files), dtype=int)

results = []  # 每個 Vb 的繪圖資料


# --------------------------------------------------------------------
# Step 3: 逐檔分析（向量化內層 Nevent 迴圈）
# --------------------------------------------------------------------
for k, (filename, _, Vb, Ib) in enumerate(file_table):
    print(f'processing... {k+1}/{num_files}: Vb={Vb}mV, Ib={Ib}uA')

    d = np.loadtxt(os.path.join(folder_path, filename))
    signal  = d[:, 0]
    trigger = d[:, 1]

    # 對齊 .m 索引：i=1..Nevent，每個事件取 signal[i*DATA_LENGTH : (i+1)*DATA_LENGTH]
    # 實際從 index DATA_LENGTH 開始（跳過第 0 段）
    actual_Nevent = min(Nevent, len(signal) // DATA_LENGTH - 1)

    # 把訊號重塑成 2D：每列是一個事件
    sig_mat = signal[DATA_LENGTH : DATA_LENGTH + actual_Nevent * DATA_LENGTH] \
              .reshape(actual_Nevent, DATA_LENGTH)
    trg_mat = trigger[DATA_LENGTH : DATA_LENGTH + actual_Nevent * DATA_LENGTH] \
              .reshape(actual_Nevent, DATA_LENGTH)

    # 只取每事件的第一個 peak（PEAK_LENGTH 個點）
    peak_mat     = sig_mat[:, :PEAK_LENGTH]
    trg_peak_mat = trg_mat[:, :PEAK_LENGTH]

    # 全體事件的原始訊號平均
    Raw_sig_ave = sig_mat.mean(axis=0)

    # 每個事件的標準差（用 ddof=1 對應 Matlab 的 std）
    sigma = np.std(peak_mat, axis=1, ddof=1)

    # 每個事件第一個 peak 的最大值與其位置
    Vmax_per_event       = peak_mat.max(axis=1)
    VmaxIndex_per_event  = peak_mat.argmax(axis=1) + 1  # +1 對應 MATLAB 1-indexed

    VmaxArray[:actual_Nevent, k]      = Vmax_per_event
    VmaxIndexArray[:actual_Nevent, k] = VmaxIndex_per_event

    # Pre-selection: sigma <= STDEV_CUT
    presel_pass = sigma <= STDEV_CUT

    # 計算 Vamplitude（對全體事件向量化）
    sig_reg = peak_mat[:, sig_slice]
    ctrl_reg = peak_mat[:, ctrl_slice]
    Vamplitude = sig_reg.max(axis=1) - ctrl_reg.mean(axis=1)

    # 對 .m 行為一致：失敗的 pre-selection 事件其 Vamplitude 視為 0
    Vamplitude_for_stats = np.where(presel_pass, Vamplitude, 0.0)

    # jitter：訊號最大斜率位置 vs 觸發最大斜率位置
    deltaSig  = np.diff(peak_mat, axis=1)
    deltaTrg  = np.diff(trg_peak_mat, axis=1)
    ndeltaSig = np.argmax(deltaSig, axis=1)
    ntrg      = np.argmax(deltaTrg, axis=1)
    deltaMax  = deltaSig.max(axis=1)
    jitter    = ntrg - ndeltaSig  # 失敗事件這裡仍計算，但不會用於輸出

    # Selection：在 pre-pass 中，有任何樣本 > V_CUT 算偵測到
    has_signal = (peak_mat > V_CUT).any(axis=1)
    sel_pass   = presel_pass & has_signal
    sel_fail   = presel_pass & ~has_signal

    nPass     = int(sel_pass.sum())
    nFail     = int(sel_fail.sum())
    nFail_pre = int((~presel_pass).sum())

    # 平均波形
    sig_region_avg  = peak_mat[sel_pass].mean(axis=0) if nPass     else np.zeros(PEAK_LENGTH)
    fail_sel_avg    = peak_mat[sel_fail].mean(axis=0) if nFail     else np.zeros(PEAK_LENGTH)
    fail_presel_avg = sig_mat[~presel_pass].mean(axis=0) if nFail_pre else np.zeros(DATA_LENGTH)

    # 效率
    Ef_event = nPass + nFail
    eff[k] = nPass / Ef_event if Ef_event > 0 else 0.0
    amplitude_mean[k]  = Vamplitude_for_stats.mean()
    amplitude_stdev[k] = Vamplitude_for_stats.std(ddof=1)

    # 振幅切點對應的事件數
    for n, cut in enumerate(amplitude_cut):
        amplitude_effi[k, n] = int((Vamplitude_for_stats >= cut).sum())

    # 第 100 個事件的完整波形（給互動圖看）
    temp_sig = sig_mat[99] if actual_Nevent >= 100 else np.zeros(DATA_LENGTH)

    results.append({
        'Vb': Vb, 'Ib': Ib, 'filename': filename,
        'sig_region_avg':  sig_region_avg,
        'fail_sel_avg':    fail_sel_avg,
        'fail_presel_avg': fail_presel_avg,
        'Raw_sig_ave':     Raw_sig_ave,
        'Vmax_per_event':  Vmax_per_event,
        'VmaxIndex_per_event': VmaxIndex_per_event,
        'temp_sig':        temp_sig,
        'Vamplitude':      Vamplitude_for_stats,
        'deltaMax':        deltaMax,
        'nPass': nPass, 'nFail': nFail, 'nFail_pre': nFail_pre,
        'eff':   eff[k],
    })


# --------------------------------------------------------------------
# Step 4: 建構互動式 plotly 圖（dropdown 切 Vb）
# --------------------------------------------------------------------
print('Building interactive HTML...')

subplot_titles = [
    'Signal-ave (pass)', 'fail-sel-ave', 'fail-presel-ave',
    'Raw-Data-ave', 'Histogram of Vmax', 'Histogram of VmaxIndex',
    '100th event waveform', 'Histogram of Amplitude', 'Histogram of deltaMax',
]

fig = make_subplots(rows=3, cols=3, subplot_titles=subplot_titles,
                    vertical_spacing=0.10, horizontal_spacing=0.06)

# 為每個 Vb 加 9 個 traces，第 0 個 Vb 預設可見，其他不可見
N_TRACES_PER_VB = 9

for k, r in enumerate(results):
    vis = (k == 0)
    # 1
    fig.add_trace(go.Scatter(y=r['sig_region_avg'], mode='lines', line=dict(color='green'),
                              visible=vis, showlegend=False, name='sig_region'), row=1, col=1)
    # 2
    fig.add_trace(go.Scatter(y=r['fail_sel_avg'], mode='lines', line=dict(color='red'),
                              visible=vis, showlegend=False, name='fail_sel'), row=1, col=2)
    # 3
    fig.add_trace(go.Scatter(y=r['fail_presel_avg'], mode='lines', line=dict(color='orange'),
                              visible=vis, showlegend=False, name='fail_presel'), row=1, col=3)
    # 4
    fig.add_trace(go.Scatter(y=r['Raw_sig_ave'], mode='lines', line=dict(color='blue'),
                              visible=vis, showlegend=False, name='Raw'), row=2, col=1)
    # 5
    fig.add_trace(go.Histogram(x=r['Vmax_per_event'],
                                visible=vis, showlegend=False, name='Vmax'), row=2, col=2)
    # 6
    fig.add_trace(go.Histogram(x=r['VmaxIndex_per_event'],
                                visible=vis, showlegend=False, name='VmaxIndex'), row=2, col=3)
    # 7
    fig.add_trace(go.Scatter(y=r['temp_sig'], mode='lines', line=dict(color='green'),
                              visible=vis, showlegend=False, name='100th event'), row=3, col=1)
    # 8
    fig.add_trace(go.Histogram(x=r['Vamplitude'],
                                visible=vis, showlegend=False, name='Vamplitude'), row=3, col=2)
    # 9
    fig.add_trace(go.Histogram(x=r['deltaMax'],
                                visible=vis, showlegend=False, name='deltaMax'), row=3, col=3)

# 構造 dropdown buttons
buttons = []
for k, r in enumerate(results):
    visibility = [False] * (N_TRACES_PER_VB * num_files)
    for i in range(N_TRACES_PER_VB):
        visibility[k * N_TRACES_PER_VB + i] = True
    label = f'Vb={r["Vb"]}mV  Ib={r["Ib"]}uA  Eff={r["eff"]:.3f}'
    title = (f'Vb={r["Vb"]}mV, Ib={r["Ib"]}uA &nbsp;&nbsp; '
             f'Pass={r["nPass"]}, Fail={r["nFail"]}, FailPre={r["nFail_pre"]} '
             f'&nbsp;&nbsp; Eff={r["eff"]:.3f}')
    buttons.append(dict(label=label, method='update',
                        args=[{'visible': visibility}, {'title.text': title}]))

# 初始標題（對應第 0 個 Vb）
r0 = results[0]
init_title = (f'Vb={r0["Vb"]}mV, Ib={r0["Ib"]}uA &nbsp;&nbsp; '
              f'Pass={r0["nPass"]}, Fail={r0["nFail"]}, FailPre={r0["nFail_pre"]} '
              f'&nbsp;&nbsp; Eff={r0["eff"]:.3f}')

fig.update_layout(
    title=dict(text=init_title, x=0.5),
    updatemenus=[dict(
        buttons=buttons, direction='down',
        x=0.0, y=1.10, xanchor='left', yanchor='top',
        bgcolor='lightgray',
    )],
    height=900, width=1500,
    margin=dict(t=120, l=60, r=40, b=40),
)

# 寫成 HTML
html_path = os.path.join(folder_path, f'{basename}_analysis.html')
fig.write_html(html_path, include_plotlyjs=EMBED_PLOTLY_JS)
print(f'  存檔: {html_path}')


# --------------------------------------------------------------------
# Step 5: Efficiency vs Bias Current 總結圖
# --------------------------------------------------------------------
Ib_arr = np.array([r['Ib'] for r in results])
Vb_arr = np.array([r['Vb'] for r in results])

fig_sum = go.Figure()
fig_sum.add_trace(go.Scatter(
    x=Ib_arr / 1000.0, y=eff,
    mode='lines+markers+text',
    text=[f'{e:.3f}' for e in eff],
    textposition='top center',
))
fig_sum.update_layout(
    title='Efficiency vs Bias Current',
    xaxis_title='Bias Current (mA)',
    yaxis_title='Efficiency',
    yaxis=dict(range=[-0.1, 1.1]),
    height=500, width=900,
)
summary_html = os.path.join(folder_path, f'{basename}_summary.html')
fig_sum.write_html(summary_html, include_plotlyjs=EMBED_PLOTLY_JS)
print(f'  存檔: {summary_html}')


# --------------------------------------------------------------------
# Step 6: 輸出 txt 檔
# --------------------------------------------------------------------
F = np.column_stack([Ib_arr, eff, Vb_arr, amplitude_mean, amplitude_stdev])
out_eff = os.path.join(folder_path, f'{basename}_{V_CUT}_noSTDEVcut_mV_efficiency.txt')
np.savetxt(out_eff, F, fmt='%14.7e')
print(f'  存檔: {out_eff}')

np.savetxt(os.path.join(folder_path, f'{basename}_Vmax.txt'),
           VmaxArray, fmt='%14.7e', delimiter='\t')
np.savetxt(os.path.join(folder_path, f'{basename}_VmaxIndex.txt'),
           VmaxIndexArray, fmt='%d', delimiter='\t')
np.savetxt(os.path.join(folder_path, f'{basename}_darkcount.txt'),
           amplitude_effi, fmt='%d', delimiter='\t')

print(f'Done. Elapsed: {time.time() - t_start:.2f} s')
