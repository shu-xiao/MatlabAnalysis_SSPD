"""
SMSPD 效率 / time jitter / 振幅分析（互動式 HTML 版，多核心）
對應 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.m

執行方式：
    1) 不帶參數 — 使用「設定區」的 folder_path
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py

    2) 指定資料夾
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py -d "C:\\path\\to\\folder"

    3) 指定單一 .txt 檔
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py -i "C:\\path\\to\\file_mV.txt"

跑完後用瀏覽器打開產生的 .html 檔，下拉選單可切換不同 Vb。

輸出檔案：
    - {basename}_analysis.html           ← 互動式 10 連格圖（含 jitter 分布；dropdown 切 Vb）
    - {basename}_summary.html            ← Efficiency vs Bias Current 總結圖
    - {basename}_*_efficiency.txt        ← [Ib, eff, Vb, amp_mean, amp_stdev, jitter_sys_ns]
    - {basename}_Vmax.txt
    - {basename}_VmaxIndex.txt
    - {basename}_darkcount.txt
"""

import os
import re
import time
import argparse
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from multiprocessing import Pool, cpu_count


def _fast_loadtxt(path):
    """以 pandas C engine 解析 ASCII 數值檔，比 np.loadtxt 快 5-10×"""
    return pd.read_csv(path, sep=r'\s+', header=None,
                       dtype=np.float64, engine='c').values


def _run_with_progress(pool, fn, args_list, desc='Processing'):
    """把 pool.imap_unordered 包上 tqdm 進度條；沒裝 tqdm 時退回純文字計數"""
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


# ============================================================================
# ============================================================================
#                            設定區（可直接修改）
#  以下所有參數都可以調整，不需要動下方程式碼
# ============================================================================
# ============================================================================

# 【1】資料夾路徑（包含 *mV.txt 的資料夾）
folder_path = r'E:\SNSPD\SNSPD_data\SMSPD_NbTiN_2025Jun\Laser\3-11_plasmonic90\20250701\4p8K\Pulse\515\10000kHz\10000nW\90degrees\20250701_015355\Pulse_515_10000nW_90degrees'

# 【2】雷射設定：1 = 800 nm 80MHz, 2 = 515 nm 10MHz
index_setting = 2

# 【3】閾值
STDEV_CUT = 0.05
V_CUT = 0.03
amplitude_cut = [0.005, 0.0075, 0.010]

# 【3a】取樣週期（ns）— jitter_sys 計算用：std(toa_diff) * SAMPLE_PERIOD_NS
SAMPLE_PERIOD_NS = 0.4

# 【4】每檔分析的事件數
Nevent = 10000

# 【5】訊號分析區域（MATLAB 1-indexed 寫法，[起點, 終點] 兩端皆含）
# 800 nm 80 MHz 設定（取消註解以套用）
# CONTROL_REGION = [20, 25]
# SIGNAL_REGION  = [25, 32]
# Visible（515 nm）10 MHz 設定
CONTROL_REGION = [50, 80]
SIGNAL_REGION  = [80, 100]

# 【6】HTML 輸出設定：True=嵌入 plotly.js（檔大但離線可看），False=用 CDN
EMBED_PLOTLY_JS = True

# 【7】多核心：-1 = 使用全部 CPU 核心，或填指定數字（保守設 4）
NUM_WORKERS = -1


# ============================================================================
# ============================================================================
#                          以下為程式分析邏輯
# ============================================================================
# ============================================================================

# 雷射參數表
laserConf = {
    1: {'name': '800 nm',         'DATA_LENGTH': 125, 'NUM_PEAKS': 4},
    2: {'name': '515 nm visible', 'DATA_LENGTH': 250, 'NUM_PEAKS': 1},
}
wavelength  = laserConf[index_setting]['name']
DATA_LENGTH = laserConf[index_setting]['DATA_LENGTH']
NUM_PEAKS   = laserConf[index_setting]['NUM_PEAKS']
PEAK_LENGTH = int(np.ceil(DATA_LENGTH / NUM_PEAKS))

# 把 MATLAB 1-indexed 區間轉成 Python 0-indexed slice
ctrl_slice = slice(CONTROL_REGION[0] - 1, CONTROL_REGION[1])
sig_slice  = slice(SIGNAL_REGION[0] - 1,  SIGNAL_REGION[1])


def extract_info(filename):
    """從檔名抽 basename, Vb (mV), Ib (uA)"""
    m_mV     = re.search(r'_(\d+)mV', filename)
    m_uA     = re.search(r'_(\d+)uA', filename)
    m_prefix = re.search(r'^(.*?Pulse_)', filename)
    if not (m_mV and m_uA and m_prefix):
        raise ValueError(f'檔名格式不符: {filename}')
    return m_prefix.group(1), int(m_mV.group(1)), int(m_uA.group(1))

## 主分析邏輯
def analyze_one_file(args):
    filename, _folder_path = args

    _, Vb, Ib = extract_info(filename)

    d = _fast_loadtxt(os.path.join(_folder_path, filename))
    signal  = d[:, 0]
    trigger = d[:, 1]

    actual_Nevent = min(Nevent, len(signal) // DATA_LENGTH - 1)

    # Reshape 成每列一事件
    sig_mat = signal[DATA_LENGTH : DATA_LENGTH + actual_Nevent * DATA_LENGTH] \
              .reshape(actual_Nevent, DATA_LENGTH)
    trg_mat = trigger[DATA_LENGTH : DATA_LENGTH + actual_Nevent * DATA_LENGTH] \
              .reshape(actual_Nevent, DATA_LENGTH)

    # 只取第一個 peak
    peak_mat     = sig_mat[:, :PEAK_LENGTH]
    trg_peak_mat = trg_mat[:, :PEAK_LENGTH]

    Raw_sig_ave = sig_mat.mean(axis=0)
    sigma = np.std(peak_mat, axis=1, ddof=1)  ## device by N-1

    Vmax_per_event      = peak_mat.max(axis=1)
    VmaxIndex_per_event = peak_mat.argmax(axis=1) + 1  # 1-indexed

    presel_pass = sigma <= STDEV_CUT

    # Vamplitude（向量化）
    sig_reg  = peak_mat[:, sig_slice]
    ctrl_reg = peak_mat[:, ctrl_slice]
    # 計算每個事件的振幅：信號區間最大值 - 控制區間平均值（背景雜訊）
    Vamplitude = sig_reg.max(axis=1) - ctrl_reg.mean(axis=1)
    # 篩選振幅：只保留通過預篩選的事件，不合格事件設為 0.0（不參與統計計算）
    Vamplitude_for_stats = np.where(presel_pass, Vamplitude, 0.0)

    # jitter
    deltaSig  = np.diff(peak_mat, axis=1)
    deltaTrg  = np.diff(trg_peak_mat, axis=1)
    ndeltaSig = np.argmax(deltaSig, axis=1)
    ntrg      = np.argmax(deltaTrg, axis=1)
    deltaMax  = deltaSig.max(axis=1)

    # Selection
    has_signal = (peak_mat > V_CUT).any(axis=1) ## 有任一event大於閥值 (any)，救回傳True
    sel_pass   = presel_pass & has_signal
    sel_fail   = presel_pass & ~has_signal

    nPass     = int(sel_pass.sum())
    nFail     = int(sel_fail.sum())
    nFail_pre = int((~presel_pass).sum())

    # =====================================================================
    # Jitter 計算（向量化）
    #   toa_trigger = 觸發脈衝最大斜率位置（dtr 的 argmax）
    #   toa_signal  = 訊號第一次跨越 V_CUT 的位置
    #   toa_diff    = toa_signal - toa_trigger  → jitter source
    #   jitter_sys  = std(有效 toa_diff) * SAMPLE_PERIOD_NS
    # =====================================================================
    toa_trigger = ntrg + 1  # 1-indexed 對應 Matlab 的 find(...)

    # 找第一次「前一點 < V_CUT 且後一點 >= V_CUT」的位置
    crossing = (peak_mat[:, :-1] < V_CUT) & (peak_mat[:, 1:] >= V_CUT)
    has_crossing = crossing.any(axis=1)
    toa_signal = np.argmax(crossing, axis=1) + 2  # +1 for crossing-after, +1 for 1-indexed

    # 只對 sel_pass + has_crossing 的事件計算 toa_diff，其他事件設 -99（與 .m 一致）
    valid_toa = sel_pass & has_crossing
    toa_diff = np.where(valid_toa, toa_signal - toa_trigger, -99)

    # jitter_sys = std(正值 toa_diff) * SAMPLE_PERIOD_NS（單位 ns）
    positive_toa = toa_diff[toa_diff > 0]
    if positive_toa.size > 1:
        jitter_sys = float(np.std(positive_toa, ddof=1) * SAMPLE_PERIOD_NS)
    else:
        jitter_sys = -1.0

    sig_region_avg  = peak_mat[sel_pass].mean(axis=0) if nPass     else np.zeros(PEAK_LENGTH)
    fail_sel_avg    = peak_mat[sel_fail].mean(axis=0) if nFail     else np.zeros(PEAK_LENGTH)
    fail_presel_avg = sig_mat[~presel_pass].mean(axis=0) if nFail_pre else np.zeros(DATA_LENGTH)

    Ef_event = nPass + nFail
    eff_value = nPass / Ef_event if Ef_event > 0 else 0.0
    amp_effi = [int((Vamplitude_for_stats >= cut).sum()) for cut in amplitude_cut]

    temp_sig = sig_mat[99] if actual_Nevent >= 100 else np.zeros(DATA_LENGTH)

    return {
        'Vb': Vb, 'Ib': Ib, 'filename': filename,
        'actual_Nevent': actual_Nevent,
        'sig_region_avg':  sig_region_avg,
        'fail_sel_avg':    fail_sel_avg,
        'fail_presel_avg': fail_presel_avg,
        'Raw_sig_ave':     Raw_sig_ave,
        'Vmax_per_event':  Vmax_per_event,
        'VmaxIndex_per_event': VmaxIndex_per_event,
        'temp_sig':        temp_sig,
        'Vamplitude':      Vamplitude_for_stats,
        'deltaMax':        deltaMax,
        'toa_diff':        toa_diff,        # 每事件的 jitter 來源（-99 = 無效）
        'positive_toa':    positive_toa,    # 給直方圖用
        'jitter_sys':      jitter_sys,      # 該檔的系統 jitter (ns)
        'nPass': nPass, 'nFail': nFail, 'nFail_pre': nFail_pre,
        'eff':              eff_value,
        'amplitude_mean':   Vamplitude_for_stats.mean(),
        'amplitude_stdev':  Vamplitude_for_stats.std(ddof=1),
        'amplitude_effi':   amp_effi,
    }


# ============================================================================
# 主程式
# ============================================================================

if __name__ == '__main__':
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

    # 抽出 Vb, Ib 並依 Vb 排序
    file_table = []
    for f in all_files:
        bn, Vb, Ib = extract_info(f)
        file_table.append((f, bn, Vb, Ib))
    file_table.sort(key=lambda x: x[2])

    basename  = file_table[0][1]
    num_files = len(file_table)
    print(f'雷射設定: {wavelength}, DATA_LENGTH={DATA_LENGTH}, PEAK_LENGTH={PEAK_LENGTH}')
    print(f'找到 {num_files} 個檔案')

    # 多核心分析
    n_workers = min(cpu_count(), num_files) if NUM_WORKERS == -1 else NUM_WORKERS
    print(f'使用 {n_workers} 個核心做平行分析')

    args_list = [(f, folder_path) for f, _, _, _ in file_table]

    t_analyze = time.time()
    if n_workers > 1:
        with Pool(processes=n_workers) as pool:
            results = _run_with_progress(pool, analyze_one_file, args_list,
                                         desc='Analyzing files')
    else:
        results = [analyze_one_file(a) for a in args_list]

    # imap_unordered 不保證順序，所以依 Vb 排序
    results.sort(key=lambda r: r['Vb'])
    print(f'分析完成，耗時 {time.time() - t_analyze:.2f} s')

    # 從 results 組裝整體陣列
    Vb_arr          = np.array([r['Vb'] for r in results])
    Ib_arr          = np.array([r['Ib'] for r in results])
    eff             = np.array([r['eff'] for r in results])
    amplitude_mean  = np.array([r['amplitude_mean'] for r in results])
    amplitude_stdev = np.array([r['amplitude_stdev'] for r in results])
    amplitude_effi  = np.array([r['amplitude_effi'] for r in results], dtype=int)
    jitter_sys_arr  = np.array([r['jitter_sys'] for r in results])

    VmaxArray      = np.zeros((Nevent, num_files))
    VmaxIndexArray = np.zeros((Nevent, num_files), dtype=int)
    for k, r in enumerate(results):
        n = r['actual_Nevent']
        VmaxArray[:n, k]      = r['Vmax_per_event']
        VmaxIndexArray[:n, k] = r['VmaxIndex_per_event']

    # --------------------------------------------------------------------
    # 互動式 plotly 圖
    # --------------------------------------------------------------------
    print('Building interactive HTML...')
    t_plot = time.time()
    subplot_titles = [
        'Signal-ave (pass)', 'fail-sel-ave', 'fail-presel-ave',
        'Raw-Data-ave', 'Histogram of Vmax', 'Histogram of VmaxIndex',
        '100th event waveform', 'Histogram of Amplitude', 'Histogram of deltaMax',
        'Histogram of Jitter (toa_diff)', '', '',
    ]
    fig = make_subplots(rows=4, cols=3, subplot_titles=subplot_titles,
                        vertical_spacing=0.08, horizontal_spacing=0.06)

    N_TRACES_PER_VB = 10  # 第 10 個是 jitter 直方圖
    for k, r in enumerate(results):
        vis = (k == 0)
        fig.add_trace(go.Scatter(y=r['sig_region_avg'], mode='lines', line=dict(color='green'),
                                  visible=vis, showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(y=r['fail_sel_avg'], mode='lines', line=dict(color='red'),
                                  visible=vis, showlegend=False), row=1, col=2)
        fig.add_trace(go.Scatter(y=r['fail_presel_avg'], mode='lines', line=dict(color='orange'),
                                  visible=vis, showlegend=False), row=1, col=3)
        fig.add_trace(go.Scatter(y=r['Raw_sig_ave'], mode='lines', line=dict(color='blue'),
                                  visible=vis, showlegend=False), row=2, col=1)
        fig.add_trace(go.Histogram(x=r['Vmax_per_event'],
                                    visible=vis, showlegend=False), row=2, col=2)
        fig.add_trace(go.Histogram(x=r['VmaxIndex_per_event'],
                                    visible=vis, showlegend=False), row=2, col=3)
        fig.add_trace(go.Scatter(y=r['temp_sig'], mode='lines', line=dict(color='green'),
                                  visible=vis, showlegend=False), row=3, col=1)
        fig.add_trace(go.Histogram(x=r['Vamplitude'],
                                    visible=vis, showlegend=False), row=3, col=2)
        fig.add_trace(go.Histogram(x=r['deltaMax'],
                                    visible=vis, showlegend=False), row=3, col=3)
        # 第 10 格：jitter 分布（只用 positive toa_diff，即有效事件）
        fig.add_trace(go.Histogram(x=r['positive_toa'],
                                    visible=vis, showlegend=False), row=4, col=1)

    buttons = []
    for k, r in enumerate(results):
        visibility = [False] * (N_TRACES_PER_VB * num_files)
        for i in range(N_TRACES_PER_VB):
            visibility[k * N_TRACES_PER_VB + i] = True
        label = f'Vb={r["Vb"]}mV  Ib={r["Ib"]}uA  Eff={r["eff"]:.3f}  Jitter={r["jitter_sys"]:.3f}ns'
        title = (f'Vb={r["Vb"]}mV, Ib={r["Ib"]}uA &nbsp;&nbsp; '
                 f'Pass={r["nPass"]}, Fail={r["nFail"]}, FailPre={r["nFail_pre"]} '
                 f'&nbsp;&nbsp; Eff={r["eff"]:.3f} &nbsp;&nbsp; '
                 f'Jitter_sys={r["jitter_sys"]:.3f} ns')
        buttons.append(dict(label=label, method='update',
                            args=[{'visible': visibility}, {'title.text': title}]))

    r0 = results[0]
    init_title = (f'Vb={r0["Vb"]}mV, Ib={r0["Ib"]}uA &nbsp;&nbsp; '
                  f'Pass={r0["nPass"]}, Fail={r0["nFail"]}, FailPre={r0["nFail_pre"]} '
                  f'&nbsp;&nbsp; Eff={r0["eff"]:.3f} &nbsp;&nbsp; '
                  f'Jitter_sys={r0["jitter_sys"]:.3f} ns')

    fig.update_layout(
        title=dict(text=init_title, x=0.5),
        updatemenus=[dict(
            buttons=buttons, direction='down',
            x=0.0, y=1.08, xanchor='left', yanchor='top',
            bgcolor='lightgray',
        )],
        height=1150, width=1500,
        margin=dict(t=140, l=60, r=40, b=40),
    )

    html_path = os.path.join(folder_path, f'{basename}_analysis.html')
    fig.write_html(html_path, include_plotlyjs=EMBED_PLOTLY_JS)
    print(f'  存檔: {html_path}')

    # --------------------------------------------------------------------
    # Efficiency vs Ib 總結圖
    # --------------------------------------------------------------------
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
    # 輸出 txt
    #   efficiency.txt 欄位: [Ib, eff, Vb, amp_mean, amp_stdev, jitter_sys_ns]
    # --------------------------------------------------------------------
    F = np.column_stack([Ib_arr, eff, Vb_arr, amplitude_mean, amplitude_stdev, jitter_sys_arr])
    out_eff = os.path.join(folder_path, f'{basename}_{V_CUT}_noSTDEVcut_mV_efficiency.txt')
    np.savetxt(out_eff, F, fmt='%14.7e')
    print(f'  存檔: {out_eff}')

    np.savetxt(os.path.join(folder_path, f'{basename}_Vmax.txt'),
               VmaxArray, fmt='%14.7e', delimiter='\t')
    np.savetxt(os.path.join(folder_path, f'{basename}_VmaxIndex.txt'),
               VmaxIndexArray, fmt='%d', delimiter='\t')
    np.savetxt(os.path.join(folder_path, f'{basename}_darkcount.txt'),
               amplitude_effi, fmt='%d', delimiter='\t')

    print(f'Done. Total elapsed: {time.time() - t_start:.2f} s')
