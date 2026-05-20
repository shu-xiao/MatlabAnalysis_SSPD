"""
SMSPD 效率 / time jitter / 振幅分析（互動式 HTML 版，多核心）
對應 SMSPD_ana_for_eff_time_jitter_tdms_chatGPT.m

執行方式：
    1) 不帶參數 — 使用「設定區」的 folder_path / OUTPUT_FOLDER
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py

    2) 指定資料夾（輸出預設存回同資料夾）
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py -d "C:\\path\\to\\folder"

    3) 指定單一 .txt 檔
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py -i "C:\\path\\to\\file_mV.txt"

    4) 指定輸出資料夾（與 -d 或 -i 搭配使用）
       python SMSPD_ana_for_eff_time_jitter_tdms_chatGPT_v2.py -d "C:\\data" -o "C:\\output"

CLI 選項：
    -d / --dir      含 *mV.txt 的資料夾（覆蓋設定區 folder_path）
    -i / --input    單一 *mV.txt 檔（覆蓋設定區 folder_path）
    -o / --output   輸出資料夾（覆蓋設定區 OUTPUT_FOLDER；預設同輸入資料夾）
    -f / --format   輸出格式: html / txt / both（覆蓋設定區 OUTPUT_FORMAT）

跑完後用瀏覽器打開產生的 .html 檔，下拉選單可切換不同 Vb。

輸出檔案：
    - {basename}_analysis.html           ← 互動式 9 連格圖（含 jitter 分布；dropdown 切 Vb）
    - {basename}_summary.html            ← Efficiency vs Bias Current 總結圖
    - {basename}_*_efficiency.txt        ← [Ib, eff, Vb, amp_mean, amp_stdev, jitter_sys_ns]
    - {basename}_Vmax.txt
    - {basename}_VmaxIndex.txt
    - {basename}_darkcount.txt
    - {basename}_jitterDist.txt          ← 每事件 toa_diff（Nevent × num_files）
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

# 【2】雷射設定：
#        0 = 自動從路徑/檔名偵測（建議）
#        1 = 800 nm 80MHz
#        2 = 515 nm 10MHz
index_setting = 0

# 【3】閾值
STDEV_CUT = 0.05
V_CUT = 0.03
amplitude_cut = [0.005, 0.0075, 0.010]

# 【3a】取樣週期（ns）— jitter_sys 計算用：std(toa_diff) * SAMPLE_PERIOD_NS
SAMPLE_PERIOD_NS = 0.4  ## unit: ns

# 【4】每檔分析的事件數
Nevent = 10000

# 【5】訊號分析區域（None = 跟著 index_setting 自動套用預設值）
#      手動指定時填入 [起點, 終點]（MATLAB 1-indexed，兩端皆含）
CONTROL_REGION = None   # 手動範例：[20, 25]（800nm）或 [50, 80]（515nm）
SIGNAL_REGION  = None   # 手動範例：[25, 32]（800nm）或 [80, 100]（515nm）

# 【6】輸出資料夾：None = 與輸入資料夾相同
OUTPUT_FOLDER = None   # 範例: r"D:\output"

# 【6b】輸出格式：'html'=只存 HTML, 'txt'=只存 txt, 'both'=兩者都存
OUTPUT_FORMAT = 'both'

# 【6a】HTML 輸出設定：True=嵌入 plotly.js（檔大但離線可看），False=用 CDN
EMBED_PLOTLY_JS = True

# 【7】多核心：-1 = 使用全部 CPU 核心，或填指定數字（保守設 4）
NUM_WORKERS = -1

# 【8】無效事件的填值（對應 MATLAB toaArray 的 -99）
INVALID_VAL = -99  ## 不需要動


# ============================================================================
# ============================================================================
#                          以下為程式分析邏輯
# ============================================================================
# ============================================================================

# 雷射參數表
laserConf = {
        1: {'name': 'IR: 800 nm 80MHz', 'DATA_LENGTH': 125, 'NUM_PEAKS': 4,
        'CONTROL_REGION': [20, 25], 'SIGNAL_REGION': [25, 32]},
        2: {'name': 'RGB: 515 nm 10MHz', 'DATA_LENGTH': 250, 'NUM_PEAKS': 1,
        'CONTROL_REGION': [50, 80], 'SIGNAL_REGION': [80, 100]},
}
# 支援的波長關鍵字（可擴充）
# 800 -> Ti-Sapphire
# 515 -> Prima(RGB laser)
_WAVELENGTH_MAP = {'800': 1, '515': 2}


def detect_index_setting(path: str) -> int:
    """
    從路徑或資料夾名稱自動偵測波長設定。
    優先搜尋路徑各層（\\Pulse\\800\\ 或 \\Pulse\\515\\），
    找不到再搜尋最底層資料夾名稱（basename）。
    找不到時拋出錯誤，請手動設定 index_setting。
    """
    import os
    parts = path.replace('/', '\\').split('\\')

    # 1) 優先：路徑各層中找緊接在 'Pulse' 後面的波長資料夾
    for i, part in enumerate(parts):
        if part.lower() == 'pulse' and i + 1 < len(parts):
            candidate = parts[i + 1]
            if candidate in _WAVELENGTH_MAP:
                return _WAVELENGTH_MAP[candidate]

    # 2) 次要：整條路徑中任何層含有波長數字的資料夾名稱
    for part in reversed(parts):          # 從最底層往上找，basename 優先
        if part in _WAVELENGTH_MAP:
            return _WAVELENGTH_MAP[part]

    # 3) 再次：資料夾名稱含 _800_ 或 _515_ 這類片段（basename 優先）
    for part in reversed(parts):
        for wl, idx in _WAVELENGTH_MAP.items():
            if re.search(rf'(?<!\d){re.escape(wl)}(?!\d)', part):
                return idx

    raise ValueError(
        f'無法從路徑自動判斷波長設定: {path}\n'
        '請手動設定 index_setting = 1 (800nm) 或 2 (515nm)。'
    )


def apply_laser_config(path: str):
    """
    index_setting / folder_path 確定後呼叫。
    設定全域變數 wavelength, DATA_LENGTH, NUM_PEAKS, PEAK_LENGTH,
    CONTROL_REGION, SIGNAL_REGION, ctrl_slice, sig_slice。
    """
    global index_setting, wavelength, DATA_LENGTH, NUM_PEAKS, PEAK_LENGTH
    global CONTROL_REGION, SIGNAL_REGION, ctrl_slice, sig_slice

    if index_setting not in (0, 1, 2):
        raise SystemExit(
            f'[錯誤] index_setting = {index_setting} 不合法，'
            '請填 0（自動）、1（800nm）或 2（515nm）。'
        )

    if index_setting == 0:
        index_setting = detect_index_setting(path)
        print(f'[自動偵測] index_setting = {index_setting} ({laserConf[index_setting]["name"]})')
    else:
        print(f'[手動設定] index_setting = {index_setting} ({laserConf[index_setting]["name"]})')

    conf        = laserConf[index_setting]
    wavelength  = conf['name']
    DATA_LENGTH = conf['DATA_LENGTH']
    NUM_PEAKS   = conf['NUM_PEAKS']
    PEAK_LENGTH = int(np.ceil(DATA_LENGTH / NUM_PEAKS))

    # CONTROL / SIGNAL REGION：手動優先，None 則用 laserConf 預設
    if CONTROL_REGION is None:
        CONTROL_REGION = conf['CONTROL_REGION']
    if SIGNAL_REGION is None:
        SIGNAL_REGION = conf['SIGNAL_REGION']
    print(f'  CONTROL_REGION={CONTROL_REGION}, SIGNAL_REGION={SIGNAL_REGION}')

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
    filename, _folder_path, cfg = args
    try:
        DATA_LENGTH      = cfg['DATA_LENGTH']
        PEAK_LENGTH      = cfg['PEAK_LENGTH']
        Nevent           = cfg['Nevent']
        STDEV_CUT        = cfg['STDEV_CUT']
        V_CUT            = cfg['V_CUT']
        amplitude_cut    = cfg['amplitude_cut']
        SAMPLE_PERIOD_NS = cfg['SAMPLE_PERIOD_NS']
        INVALID_VAL      = cfg['INVALID_VAL']
        ctrl_slice       = cfg['ctrl_slice']
        sig_slice        = cfg['sig_slice']

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
        Vamplitude = sig_reg.max(axis=1) - ctrl_reg.mean(axis=1)
        Vamplitude_for_stats = np.where(presel_pass, Vamplitude, 0.0)

        # jitter
        deltaSig  = np.diff(peak_mat, axis=1)
        deltaTrg  = np.diff(trg_peak_mat, axis=1)
        ndeltaSig = np.argmax(deltaSig, axis=1)
        ntrg      = np.argmax(deltaTrg, axis=1)
        deltaMax  = deltaSig.max(axis=1)

        # Selection
        has_signal = (peak_mat > V_CUT).any(axis=1)
        sel_pass   = presel_pass & has_signal
        sel_fail   = presel_pass & ~has_signal

        nPass     = int(sel_pass.sum())
        nFail     = int(sel_fail.sum())
        nFail_pre = int((~presel_pass).sum())

        # =====================================================================
        # Jitter 計算（向量化）
        #   toa_trigger = 觸發脈衝最大斜率位置
        #   toa_signal  = 訊號第一次跨越 V_CUT 的位置
        #   toa_diff    = toa_signal - toa_trigger
        #   jitter_sys  = std(valid toa_diff) * SAMPLE_PERIOD_NS
        # =====================================================================
        toa_trigger = ntrg + 1  # 1-indexed 對應 Matlab 的 find(...)

        crossing = (peak_mat[:, :-1] < V_CUT) & (peak_mat[:, 1:] >= V_CUT)
        has_crossing = crossing.any(axis=1)
        toa_signal = np.argmax(crossing, axis=1) + 2  # +1 crossing-after, +1 1-indexed

        # toa_diff：對應 MATLAB toaArray(:,3)
        #   pre-sel fail        → 0
        #   sel fail / 無過零點 → INVALID_VAL (-99)
        #   sel pass + 過零點   → 實際差值
        valid_toa = sel_pass & has_crossing
        toa_diff = np.zeros(actual_Nevent, dtype=float)
        toa_diff[presel_pass & ~valid_toa] = INVALID_VAL
        toa_diff[valid_toa] = toa_signal[valid_toa] - toa_trigger[valid_toa]

        # 用 valid_toa mask（保留 signal 早於 trigger 的合法事件，避免 >0 誤殺）
        valid_toa_values = toa_diff[valid_toa]
        if valid_toa_values.size > 1:
            jitter_sys = float(np.std(valid_toa_values, ddof=1) * SAMPLE_PERIOD_NS)
        else:
            jitter_sys = -1.0

        # 直方圖用：排除 INVALID_VAL，保留 0（pre-sel fail）和實際差值
        toa_hist = toa_diff[toa_diff != INVALID_VAL]
        count_gt0 = int((toa_diff > 0).sum())
        count_ne0 = int((toa_diff != 0).sum())

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
            'toa_diff':        toa_diff,        # -99=無效, 0=pre-sel fail
            'toa_hist':        toa_hist,        # 直方圖用（已排除 -99）
            'count_gt0':       count_gt0,
            'count_ne0':       count_ne0,
            'jitter_sys':      jitter_sys,
            'nPass': nPass, 'nFail': nFail, 'nFail_pre': nFail_pre,
            'eff':              eff_value,
            'amplitude_mean':   Vamplitude_for_stats.mean(),
            'amplitude_stdev':  Vamplitude_for_stats.std(ddof=1),
            'amplitude_effi':   amp_effi,
        }
    except Exception as e:
        import traceback
        return {'error': f'{type(e).__name__}: {e}',
                'filename': filename,
                'traceback': traceback.format_exc()}


# ============================================================================
# 主程式
# ============================================================================

if __name__ == '__main__':
    t_start = time.time()

    # --- CLI ---（設定區常數作為預設值，CLI 可覆寫）
    parser = argparse.ArgumentParser(
        description='SMSPD efficiency / jitter analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--input',  metavar='FILE', help='單一 *mV.txt 檔')
    group.add_argument('-d', '--dir',    metavar='DIR',  help='含 *mV.txt 的資料夾')
    parser.add_argument('-o', '--output', metavar='DIR',
                        help='輸出資料夾（預設：同輸入資料夾）')
    parser.add_argument('-f', '--format', metavar='FMT',
                        choices=['html', 'txt', 'both'],
                        help='輸出格式: html / txt / both')

    # 分析參數
    parser.add_argument('--laser', type=int, choices=[0, 1, 2], default=index_setting,
                        help='0=auto, 1=800nm 80MHz, 2=515nm 10MHz (default: %(default)s)')
    parser.add_argument('--stdev-cut', type=float, default=STDEV_CUT,
                        help='presel sigma 上限 (default: %(default)s)')
    parser.add_argument('--v-cut', type=float, default=V_CUT,
                        help='signal threshold (default: %(default)s)')
    parser.add_argument('--nevent', type=int, default=Nevent,
                        help='每檔最大事件數 (default: %(default)s)')
    parser.add_argument('--control-region', type=int, nargs=2, default=None,
                        metavar=('START', 'END'),
                        help='控制區間 1-indexed (default: 跟著 laser 設定)')
    parser.add_argument('--signal-region', type=int, nargs=2, default=None,
                        metavar=('START', 'END'),
                        help='訊號區間 1-indexed (default: 跟著 laser 設定)')
    parser.add_argument('--sample-period-ns', type=float, default=SAMPLE_PERIOD_NS,
                        help='取樣週期 ns (default: %(default)s)')
    parser.add_argument('--amplitude-cut', type=float, nargs='+', default=amplitude_cut,
                        help='amplitude 計數閾值 (default: %(default)s)')
    parser.add_argument('--workers', type=int, default=NUM_WORKERS,
                        help='平行處理核心數，-1=全部 (default: %(default)s)')
    parser.add_argument('--no-embed-js', dest='embed_plotly_js',
                        action='store_false', default=EMBED_PLOTLY_JS,
                        help='HTML 用 CDN 載入 plotly.js 而非嵌入')

    cli = parser.parse_args()

    if cli.input:
        folder_path = os.path.dirname(os.path.abspath(cli.input))
        all_files = [os.path.basename(cli.input)]
    elif cli.dir:
        folder_path = cli.dir
        all_files = [f for f in os.listdir(folder_path) if f.endswith('mV.txt')]
    else:
        all_files = [f for f in os.listdir(folder_path) if f.endswith('mV.txt')]

    # CLI 覆寫輸出資料夾 / 格式
    if cli.output:
        OUTPUT_FOLDER = cli.output
    if cli.format:
        OUTPUT_FORMAT = cli.format

    # CLI 覆寫分析參數（覆寫 module-level 全域，apply_laser_config 才會看到）
    index_setting = cli.laser
    STDEV_CUT     = cli.stdev_cut
    V_CUT         = cli.v_cut
    Nevent        = cli.nevent
    SAMPLE_PERIOD_NS = cli.sample_period_ns
    amplitude_cut    = cli.amplitude_cut
    EMBED_PLOTLY_JS  = cli.embed_plotly_js
    if cli.control_region is not None:
        CONTROL_REGION = cli.control_region
    if cli.signal_region is not None:
        SIGNAL_REGION = cli.signal_region

    # ── 在 folder_path 確定後才做波長偵測 ──
    apply_laser_config(folder_path)

    # 決定最終輸出資料夾
    output_folder = OUTPUT_FOLDER if OUTPUT_FOLDER else folder_path
    os.makedirs(output_folder, exist_ok=True)

    if not all_files:
        raise RuntimeError('No text file is found!')

    # 抽出 Vb, Ib 並依 Vb 排序
    file_table = []
    for f in all_files:
        bn, Vb, Ib = extract_info(f)
        file_table.append((f, bn, Vb, Ib))
    file_table.sort(key=lambda x: x[2])

    # cfg 傳給 worker（避免依賴 module-level 全域，相容 Windows spawn）
    cfg = {
        'DATA_LENGTH':      DATA_LENGTH,
        'PEAK_LENGTH':      PEAK_LENGTH,
        'Nevent':           Nevent,
        'STDEV_CUT':        STDEV_CUT,
        'V_CUT':            V_CUT,
        'amplitude_cut':    amplitude_cut,
        'SAMPLE_PERIOD_NS': SAMPLE_PERIOD_NS,
        'INVALID_VAL':      INVALID_VAL,
        'ctrl_slice':       ctrl_slice,
        'sig_slice':        sig_slice,
    }

    # 輸出檔名前綴：用資料夾名（含波長/光強/角度）
    basename  = os.path.basename(folder_path.rstrip('/\\'))
    num_files = len(file_table)
    print(f'雷射設定: {wavelength}, DATA_LENGTH={DATA_LENGTH}, PEAK_LENGTH={PEAK_LENGTH}')
    print(f'STDEV_CUT={STDEV_CUT}, V_CUT={V_CUT}, Nevent={Nevent}, '
          f'sample_period={SAMPLE_PERIOD_NS}ns')
    print(f'找到 {num_files} 個檔案')

    # 多核心：cap 到檔案數（避免 workers > files 浪費）
    raw_workers = cpu_count() if cli.workers == -1 else cli.workers
    n_workers   = max(1, min(raw_workers, num_files))
    print(f'使用 {n_workers} 個核心做平行分析')

    args_list = [(f, folder_path, cfg) for f, _, _, _ in file_table]

    t_analyze = time.time()
    if n_workers > 1:
        with Pool(processes=n_workers) as pool:
            results = _run_with_progress(pool, analyze_one_file, args_list,
                                         desc='Analyzing files')
    else:
        results = [analyze_one_file(a) for a in args_list]

    # 過濾失敗的檔案（worker 已包 try/except）
    errors  = [r for r in results if 'error' in r]
    results = [r for r in results if 'error' not in r]
    if errors:
        print(f'  [警告] {len(errors)} 個檔案分析失敗：')
        for e in errors:
            print(f'    - {e["filename"]}: {e["error"]}')
    if not results:
        raise RuntimeError('所有檔案都分析失敗')

    # imap_unordered 不保證順序，所以依 Vb 排序
    results.sort(key=lambda r: r['Vb'])
    num_valid = len(results)
    print(f'分析完成 ({num_valid}/{num_files})，耗時 {time.time() - t_analyze:.2f} s')

    # 從 results 組裝整體陣列
    Vb_arr          = np.array([r['Vb'] for r in results])
    Ib_arr          = np.array([r['Ib'] for r in results])
    eff             = np.array([r['eff'] for r in results])
    amplitude_mean  = np.array([r['amplitude_mean'] for r in results])
    amplitude_stdev = np.array([r['amplitude_stdev'] for r in results])
    amplitude_effi  = np.array([r['amplitude_effi'] for r in results], dtype=int)
    jitter_sys_arr  = np.array([r['jitter_sys'] for r in results])

    VmaxArray      = np.zeros((Nevent, num_valid))
    VmaxIndexArray = np.zeros((Nevent, num_valid), dtype=int)
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
        '100th event waveform', 'Histogram of Amplitude', 'Jitter distribution',
    ]
    fig = make_subplots(rows=3, cols=3, subplot_titles=subplot_titles,
                        vertical_spacing=0.10, horizontal_spacing=0.06)

    N_TRACES_PER_VB = 9
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
        # tile 9：jitter 分布（對應 MATLAB：toaArray(~= -99, 3)，含 0 排除 -99）
        fig.add_trace(go.Histogram(x=r['toa_hist'],
                                    visible=vis, showlegend=False), row=3, col=3)

    buttons = []
    for k, r in enumerate(results):
        visibility = [False] * (N_TRACES_PER_VB * num_valid)
        for i in range(N_TRACES_PER_VB):
            visibility[k * N_TRACES_PER_VB + i] = True
        # dropdown label：精簡，避免被截斷
        label = f'{r["Vb"]}mV {r["Ib"]}uA | Eff={r["eff"]:.3f} J={r["jitter_sys"]:.3f}ns'
        # 圖標題：完整資訊
        title = (f'<b>{basename}</b> &nbsp;&nbsp; '
                 f'Vb={r["Vb"]}mV, Ib={r["Ib"]}uA &nbsp;&nbsp; '
                 f'Pass={r["nPass"]}, Fail={r["nFail"]}, FailPre={r["nFail_pre"]} &nbsp;&nbsp; '
                 f'Eff={r["eff"]:.3f} &nbsp;&nbsp; '
                 f'Jitter={r["jitter_sys"]:.3f} ns &nbsp;&nbsp; '
                 f'>0:{r["count_gt0"]} ~=0:{r["count_ne0"]}')
        buttons.append(dict(label=label, method='update',
                            args=[{'visible': visibility}, {'title.text': title}]))

    r0 = results[0]
    init_title = (f'<b>{basename}</b> &nbsp;&nbsp; '
                  f'Vb={r0["Vb"]}mV, Ib={r0["Ib"]}uA &nbsp;&nbsp; '
                  f'Pass={r0["nPass"]}, Fail={r0["nFail"]}, FailPre={r0["nFail_pre"]} &nbsp;&nbsp; '
                  f'Eff={r0["eff"]:.3f} &nbsp;&nbsp; '
                  f'Jitter={r0["jitter_sys"]:.3f} ns &nbsp;&nbsp; '
                  f'>0:{r0["count_gt0"]} &nbsp; ~=0:{r0["count_ne0"]} &nbsp; nPass:{r0["nPass"]}')

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

    save_html = OUTPUT_FORMAT in ('html', 'both')
    save_txt  = OUTPUT_FORMAT in ('txt',  'both')

    # --------------------------------------------------------------------
    # HTML 輸出
    # --------------------------------------------------------------------
    if save_html:
        html_path = os.path.join(output_folder, f'{basename}_analysis.html')
        fig.write_html(html_path, include_plotlyjs=EMBED_PLOTLY_JS)
        print(f'  存檔: {html_path}')

        # Efficiency vs Ib 總結圖
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
        summary_html = os.path.join(output_folder, f'{basename}_summary.html')
        fig_sum.write_html(summary_html, include_plotlyjs=EMBED_PLOTLY_JS)
        print(f'  存檔: {summary_html}')

    # --------------------------------------------------------------------
    # txt 輸出
    #   efficiency.txt 欄位: [Ib, eff, Vb, amp_mean, amp_stdev, jitter_sys_ns]
    # --------------------------------------------------------------------
    if save_txt:
        F = np.column_stack([Ib_arr, eff, Vb_arr, amplitude_mean, amplitude_stdev, jitter_sys_arr])
        out_eff = os.path.join(output_folder, f'{basename}_{V_CUT}_noSTDEVcut_mV_efficiency.txt')
        np.savetxt(out_eff, F, fmt='%14.7e')
        print(f'  存檔: {out_eff}')

    if save_txt:
        np.savetxt(os.path.join(output_folder, f'{basename}_Vmax.txt'),
                   VmaxArray, fmt='%14.7e', delimiter='\t')
        np.savetxt(os.path.join(output_folder, f'{basename}_VmaxIndex.txt'),
                   VmaxIndexArray, fmt='%d', delimiter='\t')
        np.savetxt(os.path.join(output_folder, f'{basename}_darkcount.txt'),
                   amplitude_effi, fmt='%d', delimiter='\t')

        # jitterDist.txt：每事件的 toa_diff（Nevent × num_valid），INVALID_VAL = 無效
        jitterArray = np.full((Nevent, num_valid), float(INVALID_VAL))
        for k, r in enumerate(results):
            n = r['actual_Nevent']
            jitterArray[:n, k] = r['toa_diff']
        np.savetxt(os.path.join(output_folder, f'{basename}_jitterDist.txt'),
                   jitterArray, fmt='%g', delimiter='\t')
        print(f'  存檔: {basename}_jitterDist.txt')

    # 印出輸出資料夾路徑（Windows + WSL 兩種格式）
    abs_out = os.path.abspath(output_folder)
    print(f'\n輸出資料夾:')
    import re as _re
    if len(abs_out) >= 2 and abs_out[1] == ':':
        # 在 Windows 執行：abs_out = D:\foo\bar
        win_out = abs_out
        drive   = abs_out[0].lower()
        wsl_out = '/mnt/' + drive + abs_out[2:].replace('\\', '/')
    else:
        # 在 WSL/Linux 執行：abs_out = /mnt/d/foo/bar
        wsl_out = abs_out
        m = _re.match(r'^/mnt/([a-z])(/.*)?$', abs_out)
        if m:
            win_out = m.group(1).upper() + ':' + (m.group(2) or '').replace('/', '\\')
        else:
            win_out = '(無法轉換)'
    print(f'  [Windows] {win_out}')
    print(f'  [WSL]     {wsl_out}')

    print(f'\nDone. Total elapsed: {time.time() - t_start:.2f} s')
