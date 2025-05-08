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

% sort by voltage
%Va = sort(extract_mV_from_list(file_list));
Va = extract_mV_from_list(file_list);
file_table = struct2table(file_list);
file_table = addvars(file_table,Va,'Before',1);
file_table = sortrows(file_table,1);

%Va = [5,10:20,25,30];
%Va = [30,25];

%% 預分配效率數組
% threshold
STDEV_CUT = 0.03; % 標準差閾值
V_CUT = 0.02; % voltage amplitude 閾值

Nevent = 10000; % 1 到 10000
DATA_LENGTH = 125.; % 每個事件的數據點數目
NUM_PEAKS = 4; % 一個事件有幾個peak，通常是1

CONTROL_REGION = [1 15]; % 沒有訊號的數據點
%CONTROL_REGION = [1 DATA_LENGTH];  % 預設設定
PEAK_LENGTH = ceil(DATA_LENGTH/NUM_PEAKS); % 第一個peak的數據點數目

eff = zeros(length(Va), 1);

% setting for tab with figures
fig = uifigure('Name', 'Multi-Tab Plots', 'Position',[40 80 1400 700]);
tabgroup = uitabgroup(fig, 'Position', [20 20 1300 650]);

% for loop for different Ib, Vb files
%for k = 1:length(file_table.Va)
for k = 6:12
    % d = load([Exp_para, num2str(Va(k)), '_mV.txt']);
    % file_path = fullfile(folder_path,file_list(k).name);
    file_path = fullfile(folder_path,string(file_table.name(k)));
    disp(['processing... ', num2str(k), '/',num2str(length(file_table.Va))])
    
    d = load(file_path, '-ascii'); % 快速加載數據
    signal = d(:, 1);
    trigger = d(:, 2);
    clear d

    if size(signal) ~= (Nevent+1)*DATA_LENGTH
        warning('k = %d. Data point does no match the size', k)
    end
    
    q = zeros(PEAK_LENGTH, 1);
    nPass = 0; nFail_pre = 0; nFail = 0;
    Vamplitude = zeros(Nevent, 1);
    jitter = NaN(Nevent, 1);
    sigma = zeros(Nevent, 1);

    Raw_sig = zeros(DATA_LENGTH,1);
    fail_presel = zeros(PEAK_LENGTH, 1);
    fail_sel = zeros(PEAK_LENGTH, 1);
    sig_region = zeros(PEAK_LENGTH, 1);
    
    % loop Events
    for i = 1:10000 %Nevent 
        
        index_peak = (1:PEAK_LENGTH) + DATA_LENGTH * (i); % index of i events
        index = (1:DATA_LENGTH) + DATA_LENGTH * (i); % index of i events
        Raw_sig = Raw_sig + signal(index);
        s = signal(index_peak);  % signal in i event, length = DATA_LENGTH

        % 計算 sigma
        sigma(i) = std(s(1:PEAK_LENGTH));   % the range can be changed

       % pre-selection
       if sigma(i) <= STDEV_CUT
            q = s + q;
            s1 = s(1:PEAK_LENGTH);  % signal region
            %sbg = s(CONTROL_REGION); % control region
            %Vamplitude(i) = max(s1) - min(s1); 
            Vamplitude(i) = max(s1) - min(s1(CONTROL_REGION)); % signal amplitude
            deltaSig = diff(s1);  % i+1 data point - i data point
            dtr = diff(trigger(index_peak));
            ndeltaSig = find(deltaSig == max(deltaSig), 1);
            ntr = find(dtr == max(dtr), 1);
            jitter(i) = ntr(1) - ndeltaSig(1);
            % selection
            count = length(find(s1 > V_CUT)); 
            if count >= 2
                sig_region = sig_region + s1;
                count = 1;
                nPass = nPass + 1;
            else
                fail_sel = fail_sel + s1;
                nFail = nFail + 1;
            end
            % nPass = nPass + count;
       else
           fail_presel = fail_presel + s;
           nFail_pre = nFail_pre + 1;
       end
    end 
    % finish loop over event
    fail_presel = fail_presel/nFail_pre;
    fail_sel = fail_sel/nFail;
    sig_region = sig_region/nPass;
    Raw_sig = Raw_sig/Nevent;


    % 計算效率
    Ef_event = length(find(sigma <= STDEV_CUT)); 
    eff(k) = nPass / Ef_event;
    % 顯示圖形
    %figure;
    tab(k)=uitab(tabgroup,'Title', sprintf('Tab_%i', k));
    t = tiledlayout(tab(k), 3, 3, 'Padding', 'compact', 'TileSpacing', 'compact');
    %tab_axes = axes('parent',tab(k));
    %hold(tab_axes,'on')
    
    %subplot(2, 2, 1);
    tile1 = nexttile(t, 1);
    plot(tile1,sig_region, 'g');
    title(tile1,'Signal-ave');

    tile2 = nexttile(t);
    plot(tile2,fail_sel, 'g');
    title(tile2,'fail-sel-ave');

    tile3 = nexttile(t);
    plot(tile3,fail_presel, 'g');
    title(tile3,'fail-presel-ave');

    tile4 = nexttile(t);
    plot(tile4,Raw_sig, 'g');
    title(tile4,'Raw-signal');

    %subplot(2, 2, 2);
    tile5 = nexttile(t);
    histogram(tile5,sort(sigma));
    title(tile5,'Histogram of Sigma');

    %subplot(2, 2, 3);
    tile6 = nexttile(t);
    plot(tile6,deltaSig, 'g');
    title(tile6,'deltaSig');

    %subplot(2, 2, 4);
    tile7 = nexttile(t);
    plot(tile7,Vamplitude);
    title(tile7,'Vamplitude-passPreSel');
    
    % Summary table
    vars = ["File Name";"nPass";"nFail";"nFail_pre";"Total"];
    passEve = [string(file_table.name(k));nPass;nFail;nFail_pre;nPass+nFail+nFail_pre];
    Config_name = ["STDEV-CUT";"V-CUT";"DATA-LENGTH";"PEAK-LENGTH";"CONTROAL-REGION"];
    Config_cut = [STDEV_CUT;V_CUT;DATA_LENGTH;PEAK_LENGTH;strjoin(string(CONTROL_REGION))];
    tdata = table(vars,passEve,Config_name,Config_cut,'VariableNames',{'Variable','Name/ # of Events','Config_name','Value'});
    uit = uitable(tab(k),"Data",tdata,'Units', 'Normalized','Position', [0.5 0.0 0.4 0.2]);

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