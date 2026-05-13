% =====================================================================
% SMSPD_waveform_plot_ChatGPT.m (merged)
% 整合 GitHub 版（DATA_LENGTH=125）與本地版（DATA_LENGTH=1000）
% 主要差異只在 folder_path 與 DATA_LENGTH，邏輯完全相同
% =====================================================================
tic

% 資料夾路徑（依量測設定二選一）
folder_path ='E:\SMSPD_NbTiN_1\Laser\1-1\20250107\4p5\Pulse\450\10000kHz\5000nW\0degrees\20250107_230159\Pulse_450_5000nW_0degrees';
%folder_path ='E:\SNSPD\SNSPD_data\SMSPD_NbTiN_2025Apr\Laser\1-10\20250503\4.68\Pulse\800\80000kHz\0nW\0degrees\20250503_015313\Pulse_800_0nW_0degrees';

% 一個事件的取樣點數（依量測設定調整）
DATA_LENGTH = 1000.;
% DATA_LENGTH = 125.;   % 另一種常用設定（800nm Pulse 系列）

% 可調整的總事件數
user_defined_event = 10001;

% 實驗參數（舊版手動字串範例，僅參考用）
% Exp_para ='20241119_BroadbandSMSPD_P1_Pulse_450_8000nW_0degrees_';
% Exp_para ='SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_';

file_list = dir(fullfile(folder_path, '*_mV.txt'));
if (isempty(file_list))
    error('No text file is found!')
end

%%
Va = sort(extract_mV_from_list(file_list));
[basename, ~] = extract_info(file_list(1).name);
Exp_para = basename;

% 預分配
num_va = length(Va);
max_s1_data = zeros(DATA_LENGTH, num_va);   % 每個電壓的最大 s1 數據
peak_max_values = zeros(1, num_va);          % 每個電壓的最大 peak 值

disp('Loading Data...')

%% Loading Data
parfor k = 1:num_va
    % 加載數據
    file_path = fullfile(folder_path,file_list(k).name);
    if ~isfile(file_path)
        warning('File not found: %s', file_path);
        continue;
    end
    signal = load(file_path, '-ascii');  % 快速加載數據

    % 確定事件數
    total_event = min(user_defined_event, floor(length(signal) / DATA_LENGTH));

    % 矩陣重整，避免逐事件迴圈
    reshaped_signal = reshape(signal(1:total_event*DATA_LENGTH), DATA_LENGTH, total_event);

    % 找到每個電壓的最大事件
    [max_val, max_idx] = max(max(reshaped_signal, [], 1));
    max_s1_data(:, k) = reshaped_signal(:, max_idx);

    peak_max_values(k) = max_val;
end


%% plot
disp('Generating plots...')

% 所有電壓的最大 s1 數據
figure;
for k = 1:num_va
    plot(max_s1_data(:, k), 'DisplayName', ['Voltage ', num2str(Va(k)), ' mV']);
    hold on;
end
title('Max s1 Data Across Voltages');
xlabel('Data Index');
ylabel('s1 Value');
legend;
grid on;
savefig(fullfile(folder_path,[basename,'_waveform.fig']));

% 峰值對電壓
figure;
plot(Va, peak_max_values, '-o');
title('Peak Max Value vs Voltage');
xlabel('Voltage (mV)');
ylabel('Peak Max Value');
grid on;
savefig(fullfile(folder_path,[basename,'_peakToVoltage.fig']));


%% save to txt file
disp('save data into txt file...')
F = [Va, peak_max_values.'];
save(fullfile(folder_path,[basename,'_peakToVoltage.txt']),'F','-ascii')


%% function block

function [basename, mV_value] = extract_info(filename)
    pattern = '(.*)_(\d+)_mV.txt';
    tokens = regexp(filename, pattern, 'tokens');
    if ~isempty(tokens)
        basename = tokens{1}{1};
        mV_value = str2double(tokens{1}{2});
    else
        error(['No mV value found in filename. filename: ', filename]);
    end
end

function mV_values = extract_mV_from_list(filenames)
    mV_values = NaN(size(filenames));
    parfor i = 1:length(filenames)
        [~, mV_values(i)] = extract_info(filenames(i).name);
    end
end

function y = triple(x)
    y = 3*x;
end

toc
