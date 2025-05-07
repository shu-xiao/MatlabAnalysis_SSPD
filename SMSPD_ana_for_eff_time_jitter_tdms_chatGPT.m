%% 資料夾路徑
tic
%import SMSPD_waveform_plot_ChatGPT.*
folder_path = 'E:\SNSPD\SNSPD_data\SMSPD_NbTiN_2025Apr\Laser\1-10\20250503\4.68\Pulse\800\80000kHz\300000nW\0degrees\20250503_013751\Pulse_800_300000nW_0degrees';

% 實驗參數
% Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_';

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
% threshold
STDEV_CUT = 0.02; % 標準差閾值
V_CUT = 0.05; % voltage amplitude 閾值
Nevent = 10000; % 1 到 10000
DATA_LENGTH = 125.;

eff = zeros(length(Va), 1);

% setting for tab with figures
fig = uifigure('Name', 'Multi-Tab Plots', 'Position', [100 100 800 600]);
tabgroup = uitabgroup(fig, 'Position', [50 50 700 500]);

% for loop for different Ib, Vb files
%for k = 1:length(Va)  
for k = 1:2
    % d = load([Exp_para, num2str(Va(k)), '_mV.txt']);
    file_path = fullfile(folder_path,file_list(k).name);
    disp(['processing... ', num2str(k), '/',num2str(length(Va))])
    
    d = load(file_path, '-ascii'); % 快速加載數據
    signal = d(:, 1);
    trigger = d(:, 2);
    clear d

    
    q = zeros(DATA_LENGTH, 1);
    nPass = 0;
    Vamplitude = NaN(Nevent, 1);
    jitter = NaN(Nevent, 1);
    sigma = zeros(Nevent, 1);


    for i = 1:Nevent
        r = (1:DATA_LENGTH) + DATA_LENGTH * (i); % index of i events
        s = signal(r);  % signal in i event

        % 計算 sigma
        sigma(i) = std(s(1:DATA_LENGTH));   % the range can be changed

       if sigma(i) <= STDEV_CUT
            q = s + q;
            s1 = s(1:DATA_LENGTH);  % signal region
            sbg = s(1:DATA_LENGTH); % control region
            Vamplitude(i) = max(s1) - min(s1);  % signal amplitude
            deltaSig = diff(s1);  % i+1 data point - i data point
            dtr = diff(trigger(r));
            ndeltaSig = find(deltaSig == max(deltaSig), 1);
            ntr = find(dtr == max(dtr), 1);
            jitter(i) = ntr(1) - ndeltaSig(1);
            count = length(find(s1 > V_CUT)); 
            if count >= 2
                count = 1;
                nPass = nPass + 1;
            end
            % nPass = nPass + count;
        end
    end

    % 計算效率
    Ef_event = length(find(sigma <= STDEV_CUT)); 
    eff(k) = nPass / Ef_event;
    % 顯示圖形
    %figure;
    tab(k)=uitab(tabgroup,'Title', sprintf('Tab_%i', k));
    t = tiledlayout(tab(k), 2, 2, 'Padding', 'compact', 'TileSpacing', 'compact');
    %tab_axes = axes('parent',tab(k));
    %hold(tab_axes,'on')
    
    %subplot(2, 2, 1);
    tile1 = nexttile(t, 1);
    plot(tile1,s1, 'g');
    title(tile1,'Signal');

    %subplot(2, 2, 2);
    tile2 = nexttile(t, 2);
    histogram(tile2,sort(sigma));
    title(tile2,'Histogram of Sigma');

    %subplot(2, 2, 3);
    tile3 = nexttile(t, 3);
    plot(tile3,deltaSig, 'g');
    title(tile3,'deltaSig');

    %subplot(2, 2, 4);
    tile4 = nexttile(t, 4);
    plot(tile4,Vamplitude);
    title(tile4,'Vamplitude');
end

% 將結果保存到 txt 檔案
F = [Va, eff];
outputname = [basename, '_',num2str(V_CUT),'_', num2str(STDEV_CUT), '_mV_efficiency.txt'];

save(fullfile(folder_path, outputname), 'F', '-ascii');
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