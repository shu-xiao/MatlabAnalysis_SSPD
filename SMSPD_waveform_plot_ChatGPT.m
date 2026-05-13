tic
% 資料夾路徑
folder_path ='E:\SNSPD\SNSPD_data\SMSPD_NbTiN_2025Apr\Laser\1-10\20250503\4.68\Pulse\800\80000kHz\0nW\0degrees\20250503_015313\Pulse_800_0nW_0degrees';

% 實驗參數
% Exp_para ='20241119_BroadbandSMSPD_P1_Pulse_450_8000nW_0degrees_';
% Exp_para ='SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_';

% 電壓範圍
% Va = [500:500:5500, 5600:100:7500] / 1000; % 將電壓從 mV 轉換為 V
% Va = [5,10:20,25,30]

file_list = dir(fullfile(folder_path, '*_mV.txt'));
if (isempty(file_list))
    error('No text file is found!')
end

%%
Va = sort(extract_mV_from_list(file_list));
[basename, ~] = extract_info(file_list(1).name);
Exp_para = basename;
% 可調整的總事件數
user_defined_event = 10001; % 使用者自定義的總事件數

% 優化的預分配記憶體儲存
DATA_LENGTH = 125.;
num_va = length(Va);
%max_s1_data = zeros(1000, num_va); % 每個電壓的最大 s1 數據
max_s1_data = zeros(DATA_LENGTH, num_va); % 每個電壓的最大 s1 數據
peak_max_values = zeros(1, num_va); % 儲存每個電壓的最大 peak 值

disp('Loading Data...')

% num_va = 4;

%% Loading Data
parfor k = 1:num_va
    % 加載數據
    % file_path = fullfile(folder_path, [Exp_para, num2str(Va(k)*1000), '_mV.txt']);
    % file_path = fullfile(folder_path, [Exp_para, num2str(Va(k)), '_mV.txt']);
    file_path = fullfile(folder_path,file_list(k).name)
    if ~isfile(file_path)
        warning('File not found: %s', file_path);
        continue;
    end
    signal = load(file_path, '-ascii'); % 快速加載數據

    % 確定事件數
    total_event = min(user_defined_event, floor(length(signal) / DATA_LENGTH)); % 根據數據長度計算事件數

    % 使用矩陣重整，避免逐事件迴圈
    reshaped_signal = reshape(signal(1:total_event*DATA_LENGTH), DATA_LENGTH, total_event); % 重整為 200 行的矩陣

    % 找到每個電壓的最大事件
    [max_val, max_idx] = max(max(reshaped_signal, [], 1)); % 獲取最大值和索引
    max_s1_data(:, k) = reshaped_signal(:, max_idx); % 儲存對應事件的完整數據

    % 計算最大 peak 值
    peak_max_values(k) = max_val;
end




%% plot 
disp('Generating plots...')
% 繪製所有電壓的最大 s1 數據圖
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
%savefig('waveform.fig')

% 繪製峰值對電壓的圖
figure;
plot(Va, peak_max_values, '-o');
title('Peak Max Value vs Voltage');
xlabel('Voltage (mV)');
ylabel('Peak Max Value');
grid on;
savefig(fullfile(folder_path,[basename,'_peakToVoltage.fig']));
%savefig('peak_voltage.fig')

%% save to txt file
disp('save data into txt file...')
F = [Va, peak_max_values.'];
save(fullfile(folder_path,[basename,'_peakToVoltage.txt']),'F','-ascii')

%%% End of the code
%% function block

function [basename, mV_value] = extract_info(filename)
    % Extracts the mV value from a filename string.
    % Example: 'SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_100_mV.txt'
    % Output: 100

    % Regular expression to find the mV value before '_mV'
    pattern = '(.*)_(\d+)_mV.txt';

    % Apply regular expression
    tokens = regexp(filename, pattern, 'tokens');

    % Check if a match is found
    if ~isempty(tokens)
        basename = tokens{1}{1};
        mV_value = str2double(tokens{1}{2}); % Convert extracted string to number
    else
        error(['No mV value found in filename. filename: ', filename]);
    end
end

function mV_values = extract_mV_from_list(filenames)
    % Extracts mV values from a cell array of filenames.
    % Input: cell array of filenames
    % Output: array of extracted mV values

    mV_values = NaN(size(filenames)); % Preallocate array for mV values

    parfor i = 1:length(filenames)
        [~, mV_values(i)] = extract_info(filenames(i).name);
        %% mV_values(i) = extract_mV(filenames(i));
    end
end

function y = triple(x)
    y = 3*x;
end
toc