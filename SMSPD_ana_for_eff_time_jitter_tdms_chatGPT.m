%% 資料夾路徑
tic
%import SMSPD_waveform_plot_ChatGPT.*
folder_path = 'E:\SMSPD_NbTiN_1\Laser\1-1\20250107\12\Pulse\450\10000kHz\15000nW\0degrees\20250107_235851\Pulse_450_15000nW_0degrees';

% 實驗參數
Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_';

% 電壓範圍'
file_list = dir(fullfile(folder_path, '*_mV.txt'));
if (isempty(file_list))
    error('No text file is found!')
end
[basename, ~] = extract_info(file_list(1).name);
Va = sort(extract_mV_from_list(file_list));
%Va = [5,10:20,25,30];
%Va = [30,25];

%% 預分配效率數組

Nevent = 1000; % 1 到 10000
DATA_LENGTH = 1000.;
eff = zeros(length(Va), 1);
for k = 1:length(Va)
%for k = 1:2
    % d = load([Exp_para, num2str(Va(k)), '_mV.txt']);
    file_path = fullfile(folder_path,file_list(k).name);
    disp(['processing... ', num2str(k), '/',num2str(length(Va))])
    d = load(file_path, '-ascii'); % 快速加載數據
    
    
    signal = d(:, 1);
    trigger = d(:, 2);
    clear d

    
    q = zeros(DATA_LENGTH, 1);
    X = 0;
    Z = NaN(Nevent, 1);
    jitter = NaN(Nevent, 1);
    sigma = zeros(Nevent, 1);
    stdth = 0.02; % 標準差閾值
    ds1th = 0.05; % ds1 閾值

    for i = 1:Nevent
        r = (1:DATA_LENGTH) + DATA_LENGTH * (i);
        s = signal(r);

        % 計算 sigma
        sigma(i) = std(s(1:DATA_LENGTH));

       if sigma(i) <= stdth
            q = s + q;
            s1 = s(1:DATA_LENGTH);
            sbg = s(1:DATA_LENGTH);
            Z(i) = max(s1) - min(s1);
            ds1 = diff(s1);
            dtr = diff(trigger(r));
            nds1 = find(ds1 == max(ds1), 1);
            ntr = find(dtr == max(dtr), 1);
            jitter(i) = ntr(1) - nds1(1);
            count = length(find(s1 > stdth)); 
            if count >= 2
                count = 1;
            end
            X = X + count;
        end
    end

    % 計算效率
    Ef_event = length(find(sigma <= stdth)); 
    eff(k) = X / Ef_event;
    % 顯示圖形
    figure;
    subplot(2, 2, 1);
    plot(s1, 'g');
    title('Signal');

    subplot(2, 2, 2);
    histogram(sort(sigma));
    title('Histogram of Sigma');

    subplot(2, 2, 3);
    plot(ds1, 'g');
    title('ds1');

    subplot(2, 2, 4);
    plot(Z);
    title('Z');
end
% 將結果保存到 txt 檔案
F = [Va, eff];
outputname = [basename, '_',num2str(ds1th),'_', num2str(stdth), '_mV_efficiency.txt'];
save(outputname, 'F', '-ascii');
disp(['save data to ', outputname]);


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



toc