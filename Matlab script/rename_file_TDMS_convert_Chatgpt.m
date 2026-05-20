% =====================================================================
% rename_file_TDMS_convert_Chatgpt.m (merged)
% 採用 GitHub 進階版：從檔名自動抓取 nW/degrees/uA/mV，
%   自動產生 Exp_para 與輸出資料夾名稱。
% 保留 _local 版的兩個 folder_path 範例（在註解中），方便切換。
% =====================================================================
% parpool("Processes",4)
tStart = tic;

% 資料夾路徑（依量測設定選擇）
folder_path = 'E:\SMSPD_NbTiN_1\Laser\1-1\20250108\12\Pulse\450\10000kHz\800nW\0degrees\20250108_011217';
%folder_path = 'E:\SNSPD\SNSPD_data\SMSPD_NbTiN_2025Jun\Laser\3-11_plasmonic90\20250701\4p8K\Pulse\515\10000kHz\10000nW\90degrees\20250701_015355';
%folder_path = 'E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\515\10000kHz\2000nW\0degrees\20240520_214942';


% 儲存檔案地址
Save_Adress = folder_path;
% Save_Adress = 'E:\SNSPD_data';


% 資料夾中的所有 TDMS 檔案
file_list = dir(fullfile(folder_path, '*.tdms'));
if(isempty(file_list))
    warning('Cannot find TDMS file!');
end

% 實驗參數：自動從檔名抽 "..._Pulse_" 前綴
% 舊版手動字串（如有需要可取消註解）
% Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_450_800nW_0degrees_';
% Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_515_30000nW_0degrees_';
Exp_para = regexp(file_list(1).name, '^(.*?Pulse_)', 'tokens');
Exp_para = Exp_para{1}{1};

% 從第一個檔名抽出 "Pulse_xxx_xxxnW_xxxdegrees" 當輸出資料夾名稱
pattern = 'Pulse_\d+_\d+nW_\d+degrees';
dir_name = regexp(file_list(1).name, pattern, 'match', 'once');


% 初始化結構數組（記錄 voltage / Ib / power / polarization / signal / trigger）
converted_data = struct('voltage', [],'Ib',[], 'signal', [], 'trigger', [],'power',-1,'polarization','-1');

number_TDMSfiles = length(file_list);
% number_TDMSfiles = 8;

% 讀取並轉換所有 TDMS 檔案
t1 = toc(tStart);
tStart = tic;
parfor i = 1:number_TDMSfiles
    original_filename = fullfile(folder_path, file_list(i).name);

    % 從檔名抓取 nW / degrees / uA / mV
    nW      = regexp(file_list(i).name, '_(\d+)nW', 'tokens');
    degrees = regexp(file_list(i).name, '_(\d+)degrees', 'tokens');
    uA      = regexp(file_list(i).name, '_(\d+)uA', 'tokens');
    mV      = regexp(file_list(i).name, '_(\d+)mV', 'tokens');

    nW_val      = str2double(nW{1}{1});
    degrees_val = str2double(degrees{1}{1});
    uA_val      = str2double(uA{1}{1});
    mV_val      = str2double(mV{1}{1});

    if (i==1 && isnan(nW_val));      warning('Cannot grab parameter of laser power'); end
    if (i==1 && isnan(degrees_val)); warning('Cannot grab parameter of polarization'); end
    if (i==1 && isnan(uA_val));      warning('Cannot grab parameter of Ib'); end
    if (i==1 && isnan(mV_val));      warning('Cannot grab parameter of Vb'); end

    % 轉換 TDMS
    filename_TDMS = fullfile(folder_path, file_list(i).name);
    if exist(filename_TDMS, 'file') == 2
        A = convertTDMS(0, filename_TDMS);

        signal = A.Data.MeasuredData(3).Data;
        trigger = A.Data.MeasuredData(4).Data;

        converted_data(i).Ib            = uA_val;
        converted_data(i).power         = nW_val;
        converted_data(i).polarization  = degrees_val;
        converted_data(i).Vb            = mV_val;
        converted_data(i).signal        = signal;
        converted_data(i).trigger       = trigger;

        disp([int2str(i),'/',int2str(number_TDMSfiles),'  檔案轉換成功: ', original_filename]);
    else
        warning('檔案 %s 不存在，跳過該檔案。', filename_TDMS);
    end
end
t2 = toc(tStart);
tStart = tic;


% 建立輸出資料夾
if  ~exist(fullfile(Save_Adress,dir_name), 'dir')
    mkdir(fullfile(Save_Adress,dir_name));
    fprintf('Directory "%s" created.\n', fullfile(Save_Adress,dir_name));
end

%%
disp(['Data is saved in ',fullfile(Save_Adress,dir_name)]);

for i = 1:number_TDMSfiles
    % 構造輸出檔名（包含 power / polarization / Ib / Vb 四個欄位）
    filename_base = sprintf('%s%0.fnW_%0.fdegrees_%0.fuA_%0.fmV.txt', Exp_para, ...
        converted_data(i).power, converted_data(i).polarization, ...
        converted_data(i).Ib, converted_data(i).Vb);
    filename_new = fullfile(Save_Adress,dir_name, filename_base);

    F = [converted_data(i).signal, converted_data(i).trigger];
    save(filename_new, 'F', '-ascii');
    disp([int2str(i),'/',int2str(length(converted_data)),' output file name: ', filename_base])
end


disp('Done')
disp(['Data is saved in ',fullfile(Save_Adress,dir_name)]);
t3 = toc(tStart);
