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
    - {basename}_analysis.html           ← 互動式 9 連格圖（dropdown 切 Vb）
    - {basename}_summary.html            ← Efficiency vs Bias Current 總結圖
    - {basename}_*_efficiency.txt        ← [Ib, eff, Vb, amp_mean, amp_stdev]
    - {basename}_Vmax.txt
    - {basename}_VmaxIndex.txt
    - {basename}_darkcount.txt
"""

import os
import re
import sys
import time
import argparse
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from multiprocessing import Pool, cpu_count
from scipy.optimize import curve_fit, minimize
from scipy.special import logsumexp
from scipy.stats import norm


def _fast_loadtxt(path):
    """以 pandas C engine 解析 ASCII 數值檔，比 np.loadtxt 快 5-10×"""
    return pd.read_csv(path, sep=r'\s+', header=None,
                       dtype=np.float64, engine='c').values


_TDMS_NAME_RE = re.compile(r'_\d+mV_.*\.tdms$', re.IGNORECASE)


def _is_tdms_file(name):
    """副檔名是 .tdms 但不是 .tdms_index"""
    n = name.lower()
    return n.endswith('.tdms') and not n.endswith('.tdms_index')


def _fast_load_tdms(path):
    """讀 TDMS 檔，回傳 (N, 2) ndarray，columns = [signal, trigger]，
    對齊 _fast_loadtxt 輸出格式。
    Group / Channel 名由模組頂層 TDMS_GROUP / TDMS_CH_SIGNAL / TDMS_CH_TRIGGER 控制。
    """
    from nptdms import TdmsFile
    with TdmsFile.open(path) as f:
        grp  = f[TDMS_GROUP]
        sig  = grp[TDMS_CH_SIGNAL][:]
        trig = grp[TDMS_CH_TRIGGER][:]
    return np.column_stack([sig, trig])


def _confirm_tdms(files):
    """偵測到 TDMS 檔時請使用者確認是否納入分析。
    回傳 True = 處理，False = 略過。
    非互動環境（無 stdin）自動回傳 False。
    """
    n = len(files)
    print(f'\n[提示] 偵測到 {n} 個 TDMS 檔案：')
    for f in files[:5]:
        print(f'  - {f}')
    if n > 5:
        print(f'  ... 還有 {n - 5} 個')
    try:
        resp = input('  直接讀取 TDMS 進行分析？[y/N] ').strip().lower()
    except EOFError:
        print('  （無 stdin，預設略過 TDMS）')
        return False
    return resp in ('y', 'yes')


def normalize_path(path):
    """跨平台路徑正規化。
    - WSL/Linux 下收到 Windows 絕對路徑（'D:\\foo' 或 'D:/foo'）→ 轉成 '/mnt/d/foo'
    - 其他情況保持不變
    - 空字串 / None 直接回傳
    """
    if not path:
        return path
    # 偵測 Windows 絕對路徑（單字母 + ':' + 分隔符）
    m = re.match(r'^([A-Za-z]):[\\/](.*)', path)
    if m and sys.platform.startswith('linux'):
        drive = m.group(1).lower()
        rest  = m.group(2).replace('\\', '/')
        return f'/mnt/{drive}/{rest}'
    # 不轉換的情況也順便統一斜線（純 Windows 本機跑也 OK）
    return path


def ensure_pyroot(thisroot_sh):
    """確保 PyROOT 可用。
    - 直接 import 成功 → 回傳 True
    - 失敗且在 Linux/WSL → source thisroot.sh 後 re-exec 整個 script
      （只 re-exec 一次，避免無限 loop）
    - 失敗且非 Linux 或找不到 thisroot.sh → 印警告回傳 False
    """
    try:
        import ROOT  # noqa: F401
        return True
    except ImportError:
        pass

    if os.environ.get('_ROOT_REEXEC') == '1':
        print('  [warn] PyROOT 已嘗試 source thisroot.sh 仍無法載入，跳過 .root 輸出')
        return False

    if not sys.platform.startswith('linux'):
        print('  [warn] 非 Linux/WSL 環境，無法自動 source thisroot.sh，跳過 .root 輸出')
        return False

    if not os.path.isfile(thisroot_sh):
        print(f'  [warn] 找不到 {thisroot_sh}，跳過 .root 輸出')
        return False

    # source thisroot.sh 然後 re-exec 當前 script，把 _ROOT_REEXEC 旗標傳下去防止無限 loop
    print(f'  [info] PyROOT 未載入，source {thisroot_sh} 後 re-exec...')
    quoted = ' '.join(f"'{a}'" for a in sys.argv)
    cmd = f"source '{thisroot_sh}' && exec python3 {quoted}"
    os.environ['_ROOT_REEXEC'] = '1'
    os.execvp('bash', ['bash', '-c', cmd])
    # execvp 不會 return；下面這行只是讓 linter 開心
    return False


def save_root_tree(results, output_path, sample_period_ns):
    """把所有 file 的所有 event 數據存成單一 TTree。
    一個 event = 一個 entry。Branches 涵蓋 Vb/Ib/per-event metrics/TOA。
    """
    import ROOT

    # 把每檔的事件展平、串接成大陣列
    Vb_l, Ib_l, evnum_l = [], [], []
    Vmax_l, VmaxIdx_l, Vamp_l, deltaMax_l = [], [], [], []
    toaA_l, toaC_l, validA_l, validC_l = [], [], [], []

    for r in results:
        n = int(r['actual_Nevent'])
        Vb_l.append(np.full(n, r['Vb'], dtype=np.int32))
        Ib_l.append(np.full(n, r['Ib'], dtype=np.int32))
        evnum_l.append(np.arange(1, n + 1, dtype=np.int32))
        Vmax_l.append(r['Vmax_per_event'][:n].astype(np.float64))
        VmaxIdx_l.append(r['VmaxIndex_per_event'][:n].astype(np.int32))
        Vamp_l.append(r['Vamplitude'][:n].astype(np.float64))
        deltaMax_l.append(r['deltaMax'][:n].astype(np.float64))
        toaA_l.append((r['toa_diff_A'][:n] * sample_period_ns).astype(np.float64))
        toaC_l.append((r['toa_diff_C'][:n] * sample_period_ns).astype(np.float64))
        validA_l.append(r['valid_toa_A'][:n].astype(np.int32))
        validC_l.append(r['valid_toa_C'][:n].astype(np.int32))

    data = {
        'Vb_mV':       np.concatenate(Vb_l),
        'Ib_uA':       np.concatenate(Ib_l),
        'evnum':       np.concatenate(evnum_l),
        'Vmax':        np.concatenate(Vmax_l),
        'VmaxIdx':     np.concatenate(VmaxIdx_l),
        'Vamplitude':  np.concatenate(Vamp_l),
        'deltaMax':    np.concatenate(deltaMax_l),
        'toa_A_ns':    np.concatenate(toaA_l),
        'toa_C_ns':    np.concatenate(toaC_l),
        'valid_A':     np.concatenate(validA_l),
        'valid_C':     np.concatenate(validC_l),
    }

    # 優先用 RDataFrame.FromNumpy（ROOT >= 6.24，最快）
    try:
        rdf = ROOT.RDF.FromNumpy(data)
        rdf.Snapshot('events', output_path)
        return
    except AttributeError:
        pass

    # 退而求其次：舊版用 MakeNumpyDataFrame
    try:
        rdf = ROOT.RDF.MakeNumpyDataFrame(data)
        rdf.Snapshot('events', output_path)
        return
    except AttributeError:
        pass

    # 最後 fallback：原生 TTree（較慢，per-event Python loop）
    import array as _arr
    f = ROOT.TFile(output_path, 'RECREATE')
    tree = ROOT.TTree('events', 'SMSPD event data')
    # branch buffer + ROOT type code
    bufs = {
        'Vb_mV':      (_arr.array('i', [0]),  'I'),
        'Ib_uA':      (_arr.array('i', [0]),  'I'),
        'evnum':      (_arr.array('i', [0]),  'I'),
        'Vmax':       (_arr.array('d', [0.0]), 'D'),
        'VmaxIdx':    (_arr.array('i', [0]),  'I'),
        'Vamplitude': (_arr.array('d', [0.0]), 'D'),
        'deltaMax':   (_arr.array('d', [0.0]), 'D'),
        'toa_A_ns':   (_arr.array('d', [0.0]), 'D'),
        'toa_C_ns':   (_arr.array('d', [0.0]), 'D'),
        'valid_A':    (_arr.array('i', [0]),  'I'),
        'valid_C':    (_arr.array('i', [0]),  'I'),
    }
    for name, (buf, typ) in bufs.items():
        tree.Branch(name, buf, f'{name}/{typ}')

    N_total = len(data['Vb_mV'])
    for i in range(N_total):
        for name in bufs:
            bufs[name][0][0] = data[name][i].item()
        tree.Fill()
    tree.Write()
    f.Close()


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

# 【2】雷射設定：0 = 自動從路徑偵測，1 = 800 nm 80MHz, 2 = 515 nm 10MHz
index_setting = 0

# 【3】閾值
STDEV_CUT = 0.05
V_CUT = 0.03
amplitude_cut = [0.005, 0.0075, 0.010]

# 【4】每檔分析的事件數
Nevent = 10000

# 【5】訊號分析區域（MATLAB 1-indexed 寫法，[起點, 終點] 兩端皆含）
# None = 跟著波長自動套用；也可手動填 [起點, 終點] 覆蓋。
CONTROL_REGION = None
SIGNAL_REGION  = None

# 【6】HTML 輸出設定：True=嵌入 plotly.js（檔大但離線可看），False=用 CDN
EMBED_PLOTLY_JS = True

# 【7】多核心：-1 = 使用全部 CPU 核心，或填指定數字（保守設 4）
NUM_WORKERS = -1

# 【8】輸出資料夾：空字串 = 與輸入資料夾相同；可填其他絕對路徑
#      範例：OUTPUT_DIR = r'D:\results\today'
OUTPUT_DIR = ''

# 【9】輸出格式：'all' = html + txt，'html' = 只存 html，'txt' = 只存 txt
SAVE_MODE = 'all'

# 【10】Jitter / TOA fit 設定
SAMPLE_PERIOD_NS = 0.4   # 每個 sample 對應的時間 (ns)，用於把 index 轉成 ns
INVALID_VAL      = -99   # 進入分析但 TOA 無效的標記值
TRG_THRESHOLD    = -1.25 # 固定 trigger 閾值 (V)；TOA = trigger 從上往下穿過此值的位置
                          # 適用於 baseline≈-0.8、trough≈-1.7 的負向 trigger pulse
# 註：jitter 的篩選由 V_CUT crossing 決定（valid_toa = sel_pass & has_crossing），
#     不再額外設 JITTER_THRESHOLD。

# 【10b】TDMS 直讀設定（餵 *.tdms 時使用，平時不用動）
#        若量測程式換了 group / channel 命名，改這裡即可
TDMS_GROUP      = 'ADC Readout Channels'
TDMS_CH_SIGNAL  = 'chSig'
TDMS_CH_TRIGGER = 'chTrig'

# 【11】ROOT TTree 輸出（預設關閉）
#       True：把每事件數據存成 ROOT TTree，可給 CERN ROOT 分析
#       若 PyROOT 沒抓到，自動 source THISROOT_SH 後重新執行
SAVE_ROOT  = False
THISROOT_SH = '/home/d3a2s1l/root/bin/thisroot.sh'


# ============================================================================
# ============================================================================
#                          以下為程式分析邏輯
# ============================================================================
# ============================================================================

# 雷射參數表
laserConf = {
    1: {'name': '800 nm',         'DATA_LENGTH': 125, 'NUM_PEAKS': 4,
        'CONTROL_REGION': [20, 25], 'SIGNAL_REGION': [25, 32]},
    2: {'name': '515 nm visible', 'DATA_LENGTH': 250, 'NUM_PEAKS': 1,
        'CONTROL_REGION': [50, 80], 'SIGNAL_REGION': [80, 100]},
}
_WAVELENGTH_MAP = {'800': 1, '515': 2}


def detect_index_setting(path):
    """從路徑或資料夾名稱偵測波長設定。"""
    parts = re.split(r'[\\/]+', path)
    for i, part in enumerate(parts):
        if part.lower() == 'pulse' and i + 1 < len(parts):
            candidate = parts[i + 1]
            if candidate in _WAVELENGTH_MAP:
                return _WAVELENGTH_MAP[candidate]
    for part in reversed(parts):
        if part in _WAVELENGTH_MAP:
            return _WAVELENGTH_MAP[part]
        for wl, idx in _WAVELENGTH_MAP.items():
            if re.search(rf'(?<!\d){re.escape(wl)}(?!\d)', part):
                return idx
    raise ValueError(
        f'無法從路徑自動判斷波長設定: {path}\n'
        '請手動設定 index_setting = 1 (800nm) 或 2 (515nm)。'
    )


def apply_laser_config(path):
    """依 index_setting 或路徑設定 DATA_LENGTH / region 等全域參數。"""
    global index_setting, wavelength, DATA_LENGTH, NUM_PEAKS, PEAK_LENGTH
    global ctrl_slice, sig_slice

    idx = detect_index_setting(path) if index_setting == 0 else index_setting
    if idx not in laserConf:
        raise ValueError('index_setting 請填 0（自動）、1（800nm）或 2（515nm）。')

    conf = laserConf[idx]
    wavelength  = conf['name']
    DATA_LENGTH = conf['DATA_LENGTH']
    NUM_PEAKS   = conf['NUM_PEAKS']
    PEAK_LENGTH = int(np.ceil(DATA_LENGTH / NUM_PEAKS))
    ctrl_region = CONTROL_REGION if CONTROL_REGION is not None else conf['CONTROL_REGION']
    sig_region  = SIGNAL_REGION  if SIGNAL_REGION  is not None else conf['SIGNAL_REGION']
    ctrl_slice = slice(ctrl_region[0] - 1, ctrl_region[1])
    sig_slice  = slice(sig_region[0] - 1,  sig_region[1])
    return idx, ctrl_region, sig_region


apply_laser_config(folder_path)


def extract_info(filename):
    """從檔名抽 sample_prefix（'_Pulse_' 之前的部分）, Vb (mV), Ib (uA)
    範例：'SMSPD_NbTiN_1_1-1_Pulse_515_30000nW_0degrees_100_mV.txt'
          → sample_prefix='SMSPD_NbTiN_1_1-1', Vb=100, Ib=<from uA>
    註：Pulse_<wavelength>_<power>_<angle> 改從「資料夾路徑」抽
        （因為轉檔時檔名可能忘了更新，路徑才是正確的）
    """
    # 舊 regex（連 Pulse_X_YnW_Zdegrees 一起抓）：
    # m_prefix = re.search(r'^(.*?Pulse_\d+_\d+nW_\d+degrees)', filename)
    m_mV     = re.search(r'_(\d+)mV', filename)
    m_uA     = re.search(r'_(\d+)uA', filename)
    m_sample = re.search(r'^(.+?)_Pulse_', filename)
    if not (m_mV and m_uA and m_sample):
        raise ValueError(f'檔名格式不符: {filename}')
    return m_sample.group(1), int(m_mV.group(1)), int(m_uA.group(1))


def extract_pulse_info(path):
    """從資料夾路徑抽 'Pulse_<wavelength>_<power>nW_<angle>degrees'
    範例：'.../Pulse_800_250000nW_0degrees/' → 'Pulse_800_250000nW_0degrees'
    找不到回傳空字串"""
    m = re.search(r'Pulse_(\d+)_(\d+nW)_(\d+degrees)', path)
    if m:
        return f'Pulse_{m.group(1)}_{m.group(2)}_{m.group(3)}'
    return ''


def extract_temperature(path):
    """從資料夾路徑抽溫度字串（例如 '4p8K', '300mK', '4K'）。找不到回傳空字串"""
    # 優先抓 mK，再抓 K（避免 '4p8K' 被誤抓成 'K'）
    m = re.search(r'(\d+p?\d*mK)', path)
    if m:
        return m.group(1)
    m = re.search(r'(\d+p?\d*K)(?![a-zA-Z])', path)
    return m.group(1) if m else ''


def shorten_power(s):
    """把字串中所有 '<digits>nW' 縮減單位（只在整除時轉換）：
       1000nW → 1uW、250000nW → 250uW、500000000nW → 500mW
       不整除（如 1500nW）保持原樣"""
    def repl(m):
        val = int(m.group(1))
        if val >= 1_000_000 and val % 1_000_000 == 0:
            return f'{val // 1_000_000}mW'
        if val >= 1_000 and val % 1_000 == 0:
            return f'{val // 1_000}uW'
        return m.group(0)
    return re.sub(r'(\d+)nW', repl, s)

## Gaussian fit helper functions
def _gauss1_pdf(x, mu, sigma):
    """單高斯 PDF（面積=1）"""
    return norm.pdf(x, loc=mu, scale=sigma)


def _gauss2_pdf(x, w, mu1, s1, mu2, s2):
    """雙高斯 PDF（兩個 PDF 加權混合，總面積=1）"""
    return w * norm.pdf(x, mu1, s1) + (1 - w) * norm.pdf(x, mu2, s2)


def _fit_1g_mle(data):
    """1 Gaussian MLE — 直接用 scipy.stats.norm.fit"""
    mu, sigma = norm.fit(data)
    return mu, sigma


def _fit_2g_mle(data):
    """2 Gaussian MLE — 用 scipy.optimize.minimize 最小化 -log likelihood
    params = (w, mu1, s1, mu2, s2)，w ∈ (0,1) 為第一個高斯的權重"""
    def neg_log_lik(params):
        w, mu1, s1, mu2, s2 = params
        log_pdf = logsumexp(np.vstack([
            np.log(w) + norm.logpdf(data, mu1, s1),
            np.log1p(-w) + norm.logpdf(data, mu2, s2),
        ]), axis=0)
        value = -float(np.sum(log_pdf))
        return value if np.isfinite(value) else 1e100

    mu_all = float(np.mean(data))
    s_all  = float(np.std(data, ddof=1))
    if data.size < 20 or not np.isfinite(s_all) or s_all <= 0:
        return None

    data_min = float(np.min(data))
    data_max = float(np.max(data))
    span = max(data_max - data_min, s_all, 1e-6)
    sigma_min = max(span * 1e-6, 1e-6)
    sigma_max = max(span * 10.0, s_all * 10.0, sigma_min * 10.0)
    q25, q75 = np.percentile(data, [25, 75])
    x0 = [0.5, float(q25), max(s_all * 0.7, sigma_min),
                float(q75), max(s_all * 0.7, sigma_min)]
    bounds = [
        (1e-4, 1 - 1e-4),
        (data_min - span, data_max + span),
        (sigma_min, sigma_max),
        (data_min - span, data_max + span),
        (sigma_min, sigma_max),
    ]
    result = minimize(neg_log_lik, x0, method='L-BFGS-B', bounds=bounds,
                      options={'maxiter': 5000, 'ftol': 1e-9})
    if result.success:
        return result.x
    print(f'  [warn] 2G MLE 未收斂: {result.message}')
    return None


def _log_likelihood_1g(data, mu, sigma):
    """1G log-likelihood（給 AIC/BIC 用）"""
    return float(np.sum(np.log(norm.pdf(data, mu, sigma) + 1e-300)))


def _log_likelihood_2g(data, w, mu1, s1, mu2, s2):
    """2G log-likelihood"""
    log_pdf = logsumexp(np.vstack([
        np.log(w) + norm.logpdf(data, mu1, s1),
        np.log1p(-w) + norm.logpdf(data, mu2, s2),
    ]), axis=0)
    return float(np.sum(log_pdf))


def _fit_quality(counts, expected, n_params):
    """從 observed counts 與 fit 期望值算 chi2/ndf 和 R²
    chi2 = Σ (O-E)²/E（Pearson），ndf = bins - n_params"""
    mask = expected > 1e-6
    O = counts[mask].astype(float)
    E = expected[mask]
    chi2 = float(np.sum((O - E) ** 2 / E))
    ndf  = max(len(O) - n_params, 1)
    chi2_ndf = chi2 / ndf
    # R² 用所有 bin（包含 expected≈0 的）
    ss_res = float(np.sum((counts - expected) ** 2))
    ss_tot = float(np.sum((counts - counts.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return chi2_ndf, r2


## 主分析邏輯
def analyze_one_file(args):
    filename, _folder_path = args

    _, Vb, Ib = extract_info(filename)

    fpath = os.path.join(_folder_path, filename)
    if _is_tdms_file(filename):
        d = _fast_load_tdms(fpath)
    else:
        d = _fast_loadtxt(fpath)
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

    # --- 條件平均（向量化版）---
    # 舊版用 boolean indexing 會先複製符合條件的列再 mean，資料量大時較慢：
    # sig_region_avg  = peak_mat[sel_pass].mean(axis=0) if nPass     else np.zeros(PEAK_LENGTH)
    # fail_sel_avg    = peak_mat[sel_fail].mean(axis=0) if nFail     else np.zeros(PEAK_LENGTH)
    # fail_presel_avg = sig_mat[~presel_pass].mean(axis=0) if nFail_pre else np.zeros(DATA_LENGTH)
    #
    # 新版用矩陣乘法（mask broadcast）：不複製資料，直接加權求和再除以事件數
    sig_region_avg  = sel_pass.astype(float)      @ peak_mat / max(nPass,     1)
    fail_sel_avg    = sel_fail.astype(float)      @ peak_mat / max(nFail,     1)
    fail_presel_avg = (~presel_pass).astype(float) @ sig_mat  / max(nFail_pre, 1)

    Ef_event = nPass + nFail
    eff_value = nPass / Ef_event if Ef_event > 0 else 0.0

    # --- amplitude_effi 向量化 ---
    # 舊版對每個閾值逐一做 boolean sum（Python for loop）：
    # amp_effi = [int((Vamplitude_for_stats >= cut).sum()) for cut in amplitude_cut]
    #
    # 新版一次廣播比較所有閾值，shape: (Nevent, n_cuts) → sum over axis=0
    amp_effi = (Vamplitude_for_stats[:, None] >= np.array(amplitude_cut)).sum(axis=0).tolist()

    temp_sig = sig_mat[99] if actual_Nevent >= 100 else np.zeros(DATA_LENGTH)

    # ------------------------------------------------------------------
    # TOA / Jitter — 同時計算兩種方法（jitter_fit.html dropdown 可切換）
    # ------------------------------------------------------------------
    row_idx = np.arange(actual_Nevent)   # fancy indexing 用（trigger 和 signal C 都會用到）

    # --- Trigger TOA：候選方法（目前使用方法 4）---------------------------
    # === 方法 1：最大斜率位置（舊版） ===
    # 對負向 trigger 抓錯邊（trailing edge，而非 leading edge）
    # toa_trigger = ntrg + 1
    #
    # === 方法 2：max/min 位置「中點」 ===
    # 對稱波形時 = 零交越點；但對單點 noise spike 不穩定
    # toa_trigger = (np.argmax(trg_peak_mat, axis=1).astype(float)
    #                + np.argmin(trg_peak_mat, axis=1).astype(float)) / 2.0 + 1.0
    #
    # === 方法 3：(max+min)/2 動態 threshold crossing + 線性內插 ===
    # CFD 思路；中央閾值由每個 event 的 max/min 自動算出，self-aligned
    # mid_val_trg = (trg_peak_mat.max(axis=1, keepdims=True)
    #                + trg_peak_mat.min(axis=1, keepdims=True)) / 2.0
    # trg_crossing = (trg_peak_mat[:, :-1] < mid_val_trg) & (trg_peak_mat[:, 1:] >= mid_val_trg)
    # j_trg = np.argmax(trg_crossing, axis=1)
    # p_below_trg = trg_peak_mat[row_idx, j_trg]
    # p_above_trg = trg_peak_mat[row_idx, j_trg + 1]
    # denom_trg = p_above_trg - p_below_trg
    # safe_trg  = np.abs(denom_trg) > 1e-12
    # frac_trg  = np.zeros_like(denom_trg)
    # np.divide(mid_val_trg.flatten() - p_below_trg, denom_trg,
    #           out=frac_trg, where=safe_trg)
    # toa_trigger = j_trg.astype(float) + frac_trg + 1.0
    #
    # === 方法 4：固定閾值 TRG_THRESHOLD crossing + 線性內插（目前使用）===
    # 寫死實驗已知的中點電壓（設定區【10】），不受 event-by-event max/min 波動影響：
    # 1) 閾值固定 = TRG_THRESHOLD (-1.25 V)，所有 event 共用同一 reference
    # 2) 找 trigger 從上方「往下」穿過閾值的第一個位置（= 負向脈衝的 leading edge）
    # 3) 在交越前後兩點做線性內插 → sub-sample 精度
    # 跟方法 3 比的好處：不需要每個 event 重算 max/min（更穩、更快），
    # 且不會被「max/min 個別點雜訊」影響閾值估計。
    trg_crossing = ((trg_peak_mat[:, :-1] > TRG_THRESHOLD)
                    & (trg_peak_mat[:, 1:] <= TRG_THRESHOLD))   # 上 → 下 穿越
    j_trg = np.argmax(trg_crossing, axis=1)
    p_before_trg = trg_peak_mat[row_idx, j_trg]      # 過閾值前（值 > TRG_THRESHOLD）
    p_after_trg  = trg_peak_mat[row_idx, j_trg + 1]  # 過閾值後（值 ≤ TRG_THRESHOLD）
    denom_trg = p_after_trg - p_before_trg
    safe_trg  = np.abs(denom_trg) > 1e-12
    frac_trg  = np.zeros_like(denom_trg)
    np.divide(TRG_THRESHOLD - p_before_trg, denom_trg,
              out=frac_trg, where=safe_trg)
    toa_trigger = j_trg.astype(float) + frac_trg + 1.0   # +1 = 1-indexed

    # === 方法 A：訊號最大斜率法（slope）===
    # signal TOA = 訊號上升邊緣最陡的位置；不用 V_CUT，但對雜訊較敏感
    toa_signal_A = ndeltaSig.astype(float) + 1.0
    valid_toa_A  = sel_pass.copy()                  # 此法無 crossing 概念，只看 sel_pass
    toa_diff_A   = np.zeros(actual_Nevent, dtype=float)
    toa_diff_A[presel_pass & ~valid_toa_A] = INVALID_VAL
    toa_diff_A[valid_toa_A] = toa_signal_A[valid_toa_A] - toa_trigger[valid_toa_A]

    # === 方法 C：V_CUT crossing + 線性內插（cross）===
    # sub-sample 精度，較穩定但會帶 amplitude-walk
    crossing     = (peak_mat[:, :-1] < V_CUT) & (peak_mat[:, 1:] >= V_CUT)
    has_crossing = crossing.any(axis=1)

    j_idx   = np.argmax(crossing, axis=1)
    # row_idx 在上面 trigger TOA 處已經 np.arange(actual_Nevent) 過了
    p_below = peak_mat[row_idx, j_idx]
    p_above = peak_mat[row_idx, j_idx + 1]
    denom = p_above - p_below
    safe  = np.abs(denom) > 1e-12
    frac  = np.zeros_like(denom)
    np.divide(V_CUT - p_below, denom, out=frac, where=safe)
    toa_signal_C = j_idx.astype(float) + frac + 1.0

    valid_toa_C = sel_pass & has_crossing
    toa_diff_C  = np.zeros(actual_Nevent, dtype=float)
    toa_diff_C[presel_pass & ~valid_toa_C] = INVALID_VAL
    toa_diff_C[valid_toa_C] = toa_signal_C[valid_toa_C] - toa_trigger[valid_toa_C]

    # jitter_sys (ns)：兩種方法都算；事件不足 → NaN（txt 輸出時會留空）
    def _calc_jitter(td, vt):
        v = td[vt]
        if v.size > 1:
            return float(np.std(v, ddof=1) * SAMPLE_PERIOD_NS)
        return float('nan')
    jitter_sys_C = _calc_jitter(toa_diff_C, valid_toa_C)
    jitter_sys_A = _calc_jitter(toa_diff_A, valid_toa_A)

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
        'nPass': nPass, 'nFail': nFail, 'nFail_pre': nFail_pre,
        'eff':              eff_value,
        'amplitude_mean':   Vamplitude_for_stats.mean(),
        'amplitude_stdev':  Vamplitude_for_stats.std(ddof=1),
        'amplitude_effi':   amp_effi,
        # TOA / Jitter — 兩種方法都回傳
        'toa_diff_A':   toa_diff_A,    'valid_toa_A': valid_toa_A,   # 最大斜率
        'toa_diff_C':   toa_diff_C,    'valid_toa_C': valid_toa_C,   # V_CUT 內插
        'jitter_sys_A': jitter_sys_A,
        'jitter_sys_C': jitter_sys_C,
        'jitter_sys':   jitter_sys_C,
    }


# ============================================================================
# 主程式
# ============================================================================

if __name__ == '__main__':
    t_start = time.time()

    # --- CLI 覆寫 ---
    parser = argparse.ArgumentParser(description='SMSPD analysis with interactive HTML output')
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument('-i', '--input',   metavar='FILE', help='單一 *_mV.txt 檔')
    grp.add_argument('-d', '--dir',     metavar='DIR',  help='含 *_mV.txt 的資料夾')
    parser.add_argument('-o', '--out-dir', metavar='DIR',
                        help='輸出資料夾（預設與輸入資料夾相同）')
    parser.add_argument('-s','--save', metavar='MODE', choices=['all', 'html', 'txt'],
                        help="輸出格式：'all'（預設）| 'html' | 'txt'")
    parser.add_argument('--root', action='store_true',
                        help='額外輸出 ROOT TTree (.root)，預設關閉')
    cli = parser.parse_args()

    # WSL 環境下，把 Windows 路徑（D:\..., D:/...) 轉成 /mnt/d/... 格式
    cli.input   = normalize_path(cli.input)
    cli.dir     = normalize_path(cli.dir)
    cli.out_dir = normalize_path(cli.out_dir)
    folder_path = normalize_path(folder_path)   # 設定區【1】預設值也可能是 Windows 路徑

    def _gather_files(folder):
        listing = os.listdir(folder)
        txt  = sorted(f for f in listing if f.endswith('mV.txt'))
        tdms = sorted(f for f in listing if _is_tdms_file(f) and _TDMS_NAME_RE.search(f))
        return txt, tdms

    if cli.input:
        folder_path = os.path.dirname(os.path.abspath(cli.input))
        fname = os.path.basename(cli.input)
        if _is_tdms_file(fname):
            if not _confirm_tdms([fname]):
                raise SystemExit('使用者取消 TDMS 分析。')
        all_files = [fname]
    else:
        if cli.dir:
            folder_path = cli.dir
        txt_files, tdms_files = _gather_files(folder_path)
        if tdms_files and _confirm_tdms(tdms_files):
            all_files = txt_files + tdms_files
            print(f'  納入 {len(tdms_files)} 個 TDMS + {len(txt_files)} 個 TXT')
        else:
            if tdms_files:
                print(f'  略過 {len(tdms_files)} 個 TDMS，僅分析 TXT')
            all_files = txt_files

    detected_index, ctrl_region, sig_region = apply_laser_config(folder_path)

    # CLI 優先；CLI 未指定時退回設定區的值
    output_root = cli.out_dir if cli.out_dir else (OUTPUT_DIR if OUTPUT_DIR else folder_path)
    save_mode   = cli.save    if cli.save    else SAVE_MODE
    save_root   = bool(cli.root) or bool(SAVE_ROOT)
    print(f'輸出格式: {save_mode}{" + ROOT" if save_root else ""}')

    # 要存 ROOT 就提前確認 PyROOT 可用（必要時 source thisroot.sh 後 re-exec）
    if save_root:
        save_root = ensure_pyroot(THISROOT_SH)

    if not all_files:
        raise RuntimeError('找不到任何 *mV.txt 或 *mV_*.tdms 檔案')

    # 抽出 Vb, Ib 並依 Vb 排序
    file_table = []
    for f in all_files:
        bn, Vb, Ib = extract_info(f)
        file_table.append((f, bn, Vb, Ib))
    file_table.sort(key=lambda x: x[2])

    # basename 組成（以「路徑」為準，因為轉檔時檔名可能沒更新）：
    #   <sample_prefix from filename>_<pulse info from path>_<temp from path>
    sample_prefix = file_table[0][1]               # e.g. 'SMSPD_NbTiN_1_1-1'
    pulse_info    = extract_pulse_info(folder_path) # e.g. 'Pulse_800_250000nW_0degrees'
    temp_str      = extract_temperature(folder_path)# e.g. '4p8K'

    parts = [sample_prefix]
    if pulse_info:
        parts.append(pulse_info)
    if temp_str:
        parts.append(temp_str)
    basename = '_'.join(parts)
    basename = shorten_power(basename)              # 250000nW → 250uW
    output_dir = output_root
    if os.path.basename(os.path.normpath(output_dir)) != basename:
        output_dir = os.path.join(output_dir, basename)
    os.makedirs(output_dir, exist_ok=True)

    def _print_saved(path):
        print(f'  存檔: {os.path.basename(path)}')

    num_files = len(file_table)
    print(f'雷射設定: {wavelength}, DATA_LENGTH={DATA_LENGTH}, PEAK_LENGTH={PEAK_LENGTH}, '
          f'CONTROL_REGION={ctrl_region}, SIGNAL_REGION={sig_region}')
    print(f'找到 {num_files} 個檔案，basename={basename}')
    print(f'輸出資料夾: {os.path.basename(os.path.normpath(output_dir))}')

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

    VmaxArray      = np.zeros((Nevent, num_files))
    VmaxIndexArray = np.zeros((Nevent, num_files), dtype=int)
    for k, r in enumerate(results):
        n = r['actual_Nevent']
        VmaxArray[:n, k]      = r['Vmax_per_event']
        VmaxIndexArray[:n, k] = r['VmaxIndex_per_event']

    # --------------------------------------------------------------------
    # 互動式 plotly 圖（save_mode 為 'all' 或 'html' 時才執行）
    # --------------------------------------------------------------------
    if save_mode in ('all', 'html'):
        print('Building interactive HTML...')
        t_plot = time.time()
        subplot_titles = [
            'Signal-ave (pass)', 'fail-sel-ave', 'fail-presel-ave',
            'Raw-Data-ave', 'Histogram of Vmax', 'Histogram of VmaxIndex',
            '100th event waveform', 'Histogram of Amplitude', 'Histogram of deltaMax',
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
            fig.add_trace(go.Histogram(x=r['deltaMax'],
                                        visible=vis, showlegend=False), row=3, col=3)

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

        html_path = os.path.join(output_dir, f'{basename}_analysis.html')
        fig.write_html(html_path, include_plotlyjs=EMBED_PLOTLY_JS)
        _print_saved(html_path)

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
        summary_html = os.path.join(output_dir, f'{basename}_summary.html')
        fig_sum.write_html(summary_html, include_plotlyjs=EMBED_PLOTLY_JS)
        _print_saved(summary_html)

        # --------------------------------------------------------------------
        # Jitter / TOA 分布圖 + 1G / 2G Gaussian fit
        # 兩個 TOA 方法都存：
        #   - 'C' = V_CUT crossing + 線性內插（穩定，但有 amplitude walk）
        #   - 'A' = 訊號最大斜率法（slope-based）
        # Dropdown 選 (method, Ib)；右側 stats box 同步切換
        # --------------------------------------------------------------------

        fig_jit = go.Figure()
        jit_meta = []   # 每個 (method, Ib) 的 metadata
        any_valid = False

        # 給 preset 按鈕用的 trace 分類（注入 JS 用）
        trace_types = []   # 每個 trace 的類型：'data' | '1g' | '2g_total' | '2g_c1' | '2g_c2'
        combo_map   = []   # 每個 trace 屬於哪個 combo（0-indexed）

        # 方法配置：key=回傳 dict 內的欄位名前綴, label=顯示名稱
        METHODS = [
            ('C', 'cross',  'V_CUT crossing + interp'),
            ('A', 'slope',  'Max slope (signal)'),
        ]

        # 對每個 (method, Ib) 組合：算 fit + 加 trace + 存 metadata
        combo_idx = 0   # 第幾個組合（給 vis_mask 用）
        for mkey, mname, mdesc in METHODS:
            for idx, r in enumerate(results):
                toa_valid = r[f'toa_diff_{mkey}'][r[f'valid_toa_{mkey}']]
                N = toa_valid.size
                vis = (combo_idx == 0)   # 預設只顯示第一個組合

                if N > 10:
                    any_valid = True
                    toa_ns  = toa_valid * SAMPLE_PERIOD_NS

                    mu1g, s1g = _fit_1g_mle(toa_ns)
                    popt2     = _fit_2g_mle(toa_ns)

                    counts, edges = np.histogram(toa_ns, bins='auto')
                    bin_centers   = (edges[:-1] + edges[1:]) / 2
                    bin_width     = float(edges[1] - edges[0])
                    x_fit  = np.linspace(bin_centers.min(), bin_centers.max(), 500)
                    scale  = N * bin_width

                    # 1G quality
                    exp_1g = scale * _gauss1_pdf(bin_centers, mu1g, s1g)
                    chi2_1g, r2_1g = _fit_quality(counts, exp_1g, n_params=2)
                    logL_1g = _log_likelihood_1g(toa_ns, mu1g, s1g)
                    aic_1g  = 2 * 2 - 2 * logL_1g
                    bic_1g  = 2 * np.log(N) - 2 * logL_1g
                    fwhm1g  = 2.355 * abs(s1g)

                    # 2G quality
                    if popt2 is not None:
                        w_, m1_, s1_, m2_, s2_ = popt2
                        exp_2g = scale * _gauss2_pdf(bin_centers, w_, m1_, s1_, m2_, s2_)
                        chi2_2g, r2_2g = _fit_quality(counts, exp_2g, n_params=5)
                        logL_2g = _log_likelihood_2g(toa_ns, w_, m1_, s1_, m2_, s2_)
                        aic_2g  = 2 * 5 - 2 * logL_2g
                        bic_2g  = 5 * np.log(N) - 2 * logL_2g
                        delta_aic = aic_2g - aic_1g
                        preferred = '2G' if delta_aic < 0 else '1G'

                    eff_val = r['eff']
                    title_str = (f'[{mname}] Vb={r["Vb"]}mV Ib={r["Ib"]}uA | '
                                 f'N={N} | eff={eff_val:.3f} | '
                                 f'1G σ={abs(s1g):.3f} ns χ²/ndf={chi2_1g:.2f}')
                    if popt2 is not None:
                        title_str += f' | 2G χ²/ndf={chi2_2g:.2f}'

                    stats_lines = [
                        f'<b>━━ Method: {mname} ━━</b>',
                        f'({mdesc})',
                        '',
                        '<b>━━ Event Stats ━━</b>',
                        f'N events      : {N}',
                        f'Efficiency    : {eff_val:.4f}',
                        f'nPass/nFail   : {r["nPass"]}/{r["nFail"]}',
                        f'data mean     : {float(np.mean(toa_ns)):.3f} ns',
                        f'data std      : {float(np.std(toa_ns, ddof=1)):.3f} ns',
                        '',
                        '<b>━━ 1 Gaussian ━━</b>',
                        f'μ             : {mu1g:.4f} ns',
                        f'σ             : {abs(s1g):.4f} ns',
                        f'FWHM          : {fwhm1g:.4f} ns',
                        f'χ²/ndf        : {chi2_1g:.3f}',
                        f'R²            : {r2_1g:.4f}',
                        f'log L         : {logL_1g:.1f}',
                        f'AIC           : {aic_1g:.1f}',
                        f'BIC           : {bic_1g:.1f}',
                    ]
                    if popt2 is not None:
                        stats_lines += [
                            '',
                            '<b>━━ 2 Gaussian ━━</b>',
                            f'w (peak1 wt)  : {w_:.3f}',
                            f'μ₁, σ₁        : {m1_:.3f}, {abs(s1_):.3f} ns',
                            f'μ₂, σ₂        : {m2_:.3f}, {abs(s2_):.3f} ns',
                            f'χ²/ndf        : {chi2_2g:.3f}',
                            f'R²            : {r2_2g:.4f}',
                            f'log L         : {logL_2g:.1f}',
                            f'AIC           : {aic_2g:.1f}',
                            f'BIC           : {bic_2g:.1f}',
                            '',
                            '<b>━━ Model Cmp ━━</b>',
                            f'ΔAIC (2G-1G)  : {delta_aic:+.1f}',
                            f'Preferred     : <b>{preferred}</b>',
                        ]
                    stats_text = '<br>'.join(stats_lines)
                else:
                    counts      = np.array([0])
                    bin_centers = np.array([0.0])
                    bin_width   = 1.0
                    x_fit       = np.array([0.0])
                    scale       = 1.0
                    mu1g, s1g   = 0.0, 1.0
                    popt2       = None
                    title_str   = f'[{mname}] Vb={r["Vb"]}mV Ib={r["Ib"]}uA | N={N} (too few)'
                    stats_text  = f'<b>Method: {mname}</b><br>N events: {N}<br>太少，無法 fit'

                # --- 5 traces per combination ---
                # showlegend 一律 True：legend 顯示與否由 visible 控制，避免切 dropdown 後 legend 空白
                # 命名規則：清楚標出「Data / 1 Gaussian / 2 Gaussian」三類
                # 同時記錄 trace 類型，給 preset 按鈕的 JS 用
                fig_jit.add_trace(go.Bar(
                    x=bin_centers, y=counts, width=bin_width,
                    name=f'<b>Data</b> — TOA histogram (N={N})',
                    marker_color='lightgray', marker_line_color='gray',
                    visible=vis, showlegend=True,
                ))
                trace_types.append('data'); combo_map.append(combo_idx)

                fig_jit.add_trace(go.Scatter(
                    x=x_fit, y=scale * _gauss1_pdf(x_fit, mu1g, s1g),
                    mode='lines',
                    name=f'<b>1 Gaussian fit</b> (σ={abs(s1g):.3f} ns)',
                    line=dict(color='red', width=2),
                    visible=vis, showlegend=True,
                ))
                trace_types.append('1g'); combo_map.append(combo_idx)

                if popt2 is not None:
                    w_, m1_, s1_, m2_, s2_ = popt2
                    fig_jit.add_trace(go.Scatter(
                        x=x_fit, y=scale * _gauss2_pdf(x_fit, w_, m1_, s1_, m2_, s2_),
                        mode='lines',
                        name=f'<b>2 Gaussian fit (total)</b> (w₁={w_:.2f})',
                        line=dict(color='blue', width=2),
                        visible=vis, showlegend=True,
                    ))
                    trace_types.append('2g_total'); combo_map.append(combo_idx)
                    fig_jit.add_trace(go.Scatter(
                        x=x_fit, y=scale * w_ * norm.pdf(x_fit, m1_, s1_),
                        mode='lines',
                        name=f'&nbsp;&nbsp;└ 2G component 1 (μ={m1_:.2f}, σ={abs(s1_):.3f} ns)',
                        line=dict(color='blue', width=1, dash='dash'),
                        visible=vis, showlegend=True,
                    ))
                    trace_types.append('2g_c1'); combo_map.append(combo_idx)
                    fig_jit.add_trace(go.Scatter(
                        x=x_fit, y=scale * (1-w_) * norm.pdf(x_fit, m2_, s2_),
                        mode='lines',
                        name=f'&nbsp;&nbsp;└ 2G component 2 (μ={m2_:.2f}, σ={abs(s2_):.3f} ns)',
                        line=dict(color='blue', width=1, dash='dot'),
                        visible=vis, showlegend=True,
                    ))
                    trace_types.append('2g_c2'); combo_map.append(combo_idx)
                    n_traces = 5
                else:
                    n_traces = 2

                jit_meta.append({
                    'n_traces':   n_traces,
                    'title':      title_str,
                    'stats_text': stats_text,
                    # dropdown 顯示用，前綴 [method] 方便辨識
                    'label':      f'[{mname}] Vb={r["Vb"]}mV Ib={r["Ib"]}uA eff={r["eff"]:.3f}',
                })
                combo_idx += 1

        if any_valid:
            total_traces = sum(m['n_traces'] for m in jit_meta)
            buttons = []
            offset = 0
            for m in jit_meta:
                vis_mask = [False] * total_traces
                for i in range(m['n_traces']):
                    vis_mask[offset + i] = True
                buttons.append(dict(
                    label=m['label'], method='update',
                    args=[
                        {'visible': vis_mask},
                        {'title.text': m['title'],
                         'annotations[0].text': m['stats_text']},
                    ],
                ))
                offset += m['n_traces']

            initial_stats = jit_meta[0]['stats_text']

            fig_jit.update_layout(
                title=jit_meta[0]['title'],
                xaxis=dict(title='TOA diff (ns)', domain=[0.0, 0.70]),
                yaxis_title='Counts',
                updatemenus=[dict(
                    buttons=buttons, direction='down',
                    x=0.0, y=1.12, xanchor='left', yanchor='top',
                    bgcolor='lightgray',
                )],
                # Legend：放在 plot 下方（避免跟右側 stats box 重疊）；標題說明顏色含義
                legend=dict(
                    title=dict(text='<b>Fit legend</b>  (red = 1G, blue = 2G)'),
                    orientation='h',
                    x=0.0, y=-0.18, xanchor='left', yanchor='top',
                    bgcolor='rgba(245,245,245,0.7)',
                    bordercolor='gray', borderwidth=1,
                    font=dict(size=11),
                ),
                annotations=[dict(
                    text=initial_stats,
                    xref='paper', yref='paper',
                    x=1.02, y=1.0, xanchor='left', yanchor='top',
                    showarrow=False, align='left',
                    font=dict(family='Courier New, monospace', size=11),
                    bordercolor='black', borderwidth=1, borderpad=8,
                    bgcolor='rgba(245,245,245,0.95)',
                )],
                height=720, width=1400,
                margin=dict(t=120, l=60, r=400, b=160),  # 底部多留 100 px 給 legend
                bargap=0,
            )
            jitter_html = os.path.join(output_dir, f'{basename}_jitter_fit.html')
            fig_jit.write_html(jitter_html, include_plotlyjs=EMBED_PLOTLY_JS)

            # 注入 preset 按鈕（在 dropdown 切換時，限定當前 combo 的顯示類型）
            # 用 JS 偵測「當前可見的 combo」→ 過濾該 combo 的 trace 類型
            types_js = ','.join(f"'{t}'" for t in trace_types)
            map_js   = ','.join(str(c) for c in combo_map)
            preset_html = """
<div id="preset-controls" style="position: fixed; top: 12px; right: 12px;
     padding: 8px 12px; background: #f5f5f5; border: 1px solid #888;
     border-radius: 4px; font-family: sans-serif; font-size: 12px; z-index: 1000;">
  <span style="margin-right: 6px;"><b>View (current Ib):</b></span>
  <button onclick="applyPreset('data')">Data only</button>
  <button onclick="applyPreset('data_1g')">Data + 1G</button>
  <button onclick="applyPreset('data_2g')">Data + 2G</button>
  <button onclick="applyPreset('all')">All fits</button>
</div>
<script>
(function() {
  var traceTypes = [__TYPES__];
  var comboMap   = [__MAP__];
  window.applyPreset = function(preset) {
    var div = document.querySelector('.plotly-graph-div');
    if (!div || !div.data) return;
    // 找目前可見的 combo（第一個 visible !== false 的 trace 所屬 combo）
    var currentCombo = -1;
    for (var i = 0; i < div.data.length; i++) {
      var v = div.data[i].visible;
      if (v === true || v === undefined) { currentCombo = comboMap[i]; break; }
    }
    if (currentCombo < 0) return;
    // 算出每個 trace 該不該顯示
    var newVis = div.data.map(function(t, i) {
      if (comboMap[i] !== currentCombo) return false;     // 其他 combo 全隱藏
      if (preset === 'all') return true;
      var type = traceTypes[i];
      if (preset === 'data')    return type === 'data';
      if (preset === 'data_1g') return type === 'data' || type === '1g';
      if (preset === 'data_2g') return type === 'data' || type.indexOf('2g') === 0;
      return true;
    });
    // Per-trace restyle：直接傳 array，不要再包 [v]
    Plotly.restyle(div, {visible: newVis});
  };
})();
</script>
"""
            preset_html = preset_html.replace('__TYPES__', types_js).replace('__MAP__', map_js)
            with open(jitter_html, 'r', encoding='utf-8') as fp:
                html_text = fp.read()
            html_text = html_text.replace('</body>', preset_html + '\n</body>')
            with open(jitter_html, 'w', encoding='utf-8') as fp:
                fp.write(html_text)

            _print_saved(jitter_html)
        else:
            print('  [warn] 所有 Ib 的有效 TOA 事件太少，跳過 jitter fit')

    # --------------------------------------------------------------------
    # 輸出 txt（save_mode 為 'all' 或 'txt' 時才執行）
    # --------------------------------------------------------------------
    if save_mode in ('all', 'txt'):
        jitter_C_arr = np.array([r['jitter_sys_C'] for r in results], dtype=float)
        jitter_A_arr = np.array([r['jitter_sys_A'] for r in results], dtype=float)
        out_eff = os.path.join(output_dir, f'{basename}_{V_CUT}_noSTDEVcut_mV_efficiency.txt')
        pd.DataFrame({
            'Ib_uA':         Ib_arr,
            'eff':           eff,
            'Vb_mV':         Vb_arr,
            'amp_mean_mV':   amplitude_mean,
            'amp_stdev_mV':  amplitude_stdev,
            'jitter_C_ns':   jitter_C_arr,   # V_CUT crossing + interp
            'jitter_A_ns':   jitter_A_arr,   # max slope
        }).to_csv(out_eff, sep=' ', header=True, index=False,
                  float_format='%.7e', na_rep='')   # NaN → 留空
        _print_saved(out_eff)

        def _blank_invalid_toa(values, valid):
            out = np.full(values.shape, np.nan, dtype=float)
            out[valid] = values[valid]
            return out

        toa_dir = os.path.join(output_dir, 'toa')
        os.makedirs(toa_dir, exist_ok=True)
        for r in results:
            n = r['actual_Nevent']
            toa_A_sample = _blank_invalid_toa(r['toa_diff_A'][:n], r['valid_toa_A'][:n])
            toa_C_sample = _blank_invalid_toa(r['toa_diff_C'][:n], r['valid_toa_C'][:n])
            keep = r['valid_toa_C'][:n]
            toa_out = os.path.join(toa_dir, f'Vb_{r["Vb"]}mV_Ib_{r["Ib"]}uA_toa.txt')
            pd.DataFrame({
                'event_index': np.arange(1, n + 1, dtype=int)[keep],
                'toa_max_slope_sample': toa_A_sample[keep],
                'toa_max_slope_ns': (toa_A_sample * SAMPLE_PERIOD_NS)[keep],
                'toa_vcut_interp_sample': toa_C_sample[keep],
                'toa_vcut_interp_ns': (toa_C_sample * SAMPLE_PERIOD_NS)[keep],
            }).to_csv(
                toa_out, sep=' ', header=True, index=False, float_format='%.7e',
                na_rep='')
        print(f'  存檔: toa/ ({len(results)} files)')

        pd.DataFrame(VmaxArray).to_csv(
            os.path.join(output_dir, f'{basename}_Vmax.txt'),
            sep=' ', header=False, index=False, float_format='%.7e')
        pd.DataFrame(VmaxIndexArray).to_csv(
            os.path.join(output_dir, f'{basename}_VmaxIndex.txt'),
            sep=' ', header=False, index=False)
        pd.DataFrame(amplitude_effi).to_csv(
            os.path.join(output_dir, f'{basename}_darkcount.txt'),
            sep=' ', header=False, index=False)

    # --------------------------------------------------------------------
    # ROOT TTree 輸出（save_root=True 時）
    # --------------------------------------------------------------------
    if save_root:
        root_path = os.path.join(output_dir, f'{basename}.root')
        try:
            save_root_tree(results, root_path, SAMPLE_PERIOD_NS)
            _print_saved(root_path)
        except Exception as e:
            print(f'  [warn] ROOT TTree 輸出失敗: {e}')

    print(f'Done. Total elapsed: {time.time() - t_start:.2f} s')


# 版號（規則見專案記憶；版號不連續代表期間有他人/AI 改過，先 review 再動手）
# v1.1.0 | Claude | 新增 TDMS 直讀
__version__ = '1.1.0'
