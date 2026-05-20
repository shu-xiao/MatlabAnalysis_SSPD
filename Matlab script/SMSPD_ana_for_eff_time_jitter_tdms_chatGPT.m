%% 資料夾路徑
tic
%import SMSPD_waveform_plot_ChatGPT.*
folder_path = 'D:\Matlab analysis\SNSPD_data\20250609\4p8K\Pulse\800\80000kHz\250000nW\0degrees\20250609_233545\Pulse_800_250000nW_0degrees';

% 實驗參數

% 電壓範圍'
file_list = dir(fullfile(folder_path, '*mV.txt'));

if (isempty(file_list))
    error('No text file is found!')
end
[basename,~, ~] = extract_info(file_list(1).name);

% sort by voltage
%Vb = sort(extract_mV_from_list(file_list));
[Vb, Ib] = extract_mV_from_list(file_list);
file_table = struct2table(file_list);
file_table = addvars(file_table,Vb, Ib,'Before',1);
file_table = sortrows(file_table,1);


%% 預分配效率數組

% threshold
STDEV_CUT = 0.05; % Threshold of STDEV 標準差閾值
V_CUT = 0.03; % Threshold of voltage amplitude 閾值
index_setting = 1; % 1: 800nm, 2: 515nm


Wavelength = ['800 nm'; '515 nm'];
datalen = [125; 250];
nPulse = [4; 1];
laserConf = table(Wavelength, datalen, nPulse);

Nevent = 10000; % 1 ~ 10000
DATA_LENGTH = laserConf.datalen(index_setting); % The number of data points of each event 每個事件的數據點數目
NUM_PEAKS = laserConf.nPulse(index_setting); % The number of signal peak in each event (usually = 1) 一個事件有幾個peak，通常是1

% 800nm, 80 MHz
CONTROL_REGION = [20:25]; % The range of control region 沒有訊號的數據點
SIGNAL_REGION = [25:32]; % The range of signal region 沒有訊號的數據點
% visible, 10 MHz
%CONTROL_REGION = [50:80]; % The range of control region 沒有訊號的數據點
%SIGNAL_REGION = 80:100; % The range of signal region 沒有訊號的數據點


%CONTROL_REGION = [1:DATA_LENGTH];  % defaul setting 預設設定
PEAK_LENGTH = ceil(DATA_LENGTH/NUM_PEAKS); % The range of first peak 第一個peak的數據點數目

eff = zeros(length(Vb), 1);
temp_waveform = NaN(DATA_LENGTH,50);
VmaxArray = zeros(Nevent, 50);
VmaxIndexArray = zeros(Nevent, 50);
amplitude_mean = zeros(length(Vb), 1);
amplitude_stdev = zeros(length(Vb), 1);
amplitude_effi = zeros(length(Vb), 3);
jitter_sys_arr = -ones(length(Vb), 1);                 % 每個檔的 jitter_sys (ns)
jitterArray = zeros(Nevent, length(file_table.Vb));    % 每事件的 toa_diff（分布用）

% setting for tab with figures
fig = uifigure('Name', 'Multi-Tab Plots', 'Position',[40 80 1400 700]);
tabgroup = uitabgroup(fig, 'Position', [20 20 1300 450]);
tabgroup2 = uitabgroup(fig, 'Position', [20 500 1300 200]);


temp_j = 1;
% for loop for different Ib, Vb files
for k = 1:length(file_table.Vb)
%for k = 6:15
    file_path = fullfile(folder_path,string(file_table(k,:).name)); 
    disp(['processing... ', num2str(k), '/',num2str(length(file_table.Vb))])
    
    d = load(file_path, '-ascii'); % Loading data
    signal = d(:, 1);
    trigger = d(:, 2);
    clear d

    if size(signal) ~= (Nevent+1)*DATA_LENGTH
        warning('k = %d. Data point does no match the size', k)
        warning('Check index_setting')
    end
    
    q = zeros(PEAK_LENGTH, 1);
    nPass = 0; nFail_pre = 0; nFail = 0;
    Vamplitude = zeros(Nevent, 1);
    deltaMax = zeros(Nevent, 1);
    %t_arrive = zeros(Nevent, 1);
    sigma = zeros(Nevent, 1);
    toaArray = zeros(Nevent, 3);   % 每個檔開頭都重置，避免上一檔的資料殘留


    Raw_sig_ave = zeros(DATA_LENGTH,1);
    temp_sig = zeros(DATA_LENGTH,1);
    fail_presel = zeros(PEAK_LENGTH, 1);
    fail_sel = zeros(PEAK_LENGTH, 1);
    sig_region = zeros(PEAK_LENGTH, 1);
    
    warning_preselction = true;
    
    % loop Events in one of files
    amplitude_cut = 0.001*[5 7.5 10];
    for i = 1:Nevent 
        
        index_peak = (1:PEAK_LENGTH) + DATA_LENGTH * (i); % index of i events
        index = (1:DATA_LENGTH) + DATA_LENGTH * (i); % index of i events
        Raw_sig_ave = Raw_sig_ave + signal(index);
        s = signal(index_peak);  % signal of 1st peak in i event, length = DATA_LENGTH
        s_raw = signal(index);   % signal of all peaks in i event, length = DATA_LENGTH

        % Calculate sigma 計算標準差
        sigma(i) = std(s(1:PEAK_LENGTH));   % the range can be changed
        [VmaxArray(i,k), VmaxIndexArray(i,k)] = max(s);

        if (warning_preselction && nFail_pre > Nevent*0.1)
            warning_preselction = false;
            warning('k = %d. Too many events fail pre-selection', k)
        end

        %if (true && k>=5 && k<=10 && i==100)
        if (true  && i==100)
            temp_waveform(:,temp_j) = s_raw;
            %outputname = [basename, '_test_waveform_',num2str(temp_j), '.txt'];
            %save(fullfile(folder_path, outputname), 's_raw', '-ascii');
            temp_j = temp_j + 1;
        end
        if (i==100)
            temp_sig = s_raw;
        end

        % pre-selection
        if true & sigma(i) <= STDEV_CUT
            q = s + q;
            s1 = s(1:PEAK_LENGTH);  % The data point of signal region
            %sbg = s(CONTROL_REGION); % control reg0ion
            %Vamplitude(i) = max(s1) - min(s1); 
            Vamplitude(i) = max(s1(SIGNAL_REGION)) - mean(s1(CONTROL_REGION)); % signal amplitude
            deltaSig = diff(s1);  % i+1 data point - i data point
            dtr = diff(trigger(index_peak));
            deltaMax(i) = max(deltaSig);  % slope index of signal
            % Jitter calculation
            toaArray(i,1) = find(dtr == max(dtr), 1);       % index of laser trigger: defined by max slope (positive)
            %index_signal = find(deltaSig == max(deltaSig), 1); % index of signal pulse: max slope index of signal
            
            
            % selection
            count = length(find(s1 > V_CUT)); % selection (Voltage cut)
            if count >= 1
                sig_region = sig_region + s1;
                count = 1;
                nPass = nPass + 1;
                % 找訊號跟Vcut的交界點
                idx_cross = find(s1(1:end-1) < V_CUT & s1(2:end) >= V_CUT, 1);
                if ~isempty(idx_cross)
                    toaArray(i,2) = idx_cross + 1;
                    toaArray(i,3) = toaArray(i,2) - toaArray(i,1); % signal - laser
                else
                    toaArray(i,2) = -99;
                    toaArray(i,3) = -99;
                end
            else
                fail_sel = fail_sel + s1;
                nFail = nFail + 1;
                toaArray(i,2) = -99;
                toaArray(i,3) = -99;
            end
            % nPass = nPass + count;

            for n = 1:length(amplitude_cut)
                if Vamplitude(i) >= amplitude_cut(n)
                    amplitude_effi(k,n) = amplitude_effi(k,n) + 1;
                end
            end
       else 
           fail_presel = fail_presel + s;
           nFail_pre = nFail_pre + 1;
       end % end of pre-selection
    end 
    % finish loop over event in one of files

    fail_presel = fail_presel/nFail_pre;
    fail_sel = fail_sel/nFail;
    sig_region = sig_region/nPass;
    Raw_sig_ave = Raw_sig_ave/Nevent;
    toa_pass = toaArray(:, 3);
    if (~isempty(toa_pass(toa_pass > 0)))
        jitter_sys = std(toa_pass(toa_pass > 0))*0.4; % unit: ns
    else
        jitter_sys = -1.;
    end
    jitter_sys_arr(k) = jitter_sys;
    jitterArray(:, k) = toaArray(:, 3);   % 存下這個檔的 jitter 分布


    % Calculate the efficiency 計算效率
    %Ef_event = length(find(sigma <= STDEV_CUT)); 
    Ef_event = nPass + nFail;
    eff(k) = nPass / Ef_event;
    amplitude_mean(k) = mean(Vamplitude);
    amplitude_stdev(k) = std(Vamplitude);
    
    % The configure of plots 顯示圖形
    tab(k)=uitab(tabgroup,'Title', sprintf('%.0f uA', file_table(k,:).Ib));
    tab(k).Scrollable = 'on';
    t = tiledlayout(tab(k), 3, 3, 'Padding', 'compact', 'TileSpacing', 'compact');

    tab2(k)=uitab(tabgroup2,'Title', sprintf('%.0f uA', file_table(k,:).Ib));
    tab2(k).Scrollable = 'on';
    t = tiledlayout(tab(k), 3, 3, 'Padding', 'compact', 'TileSpacing', 'compact');

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
    plot(tile4,Raw_sig_ave, 'g');
    ylim(tile4,[min(-0.01,min(Raw_sig_ave)*1.1), max(0.01,max(Raw_sig_ave)*1.1)]);
    title(tile4,'Raw-Data-ave');

    tile5 = nexttile(t);
    %histogram(tile5,Vmax);
    histogram(tile5,VmaxArray(:,k));
    %xlim(tile5,[-0.01, max(0.01,max(Vmax)*1.1)]);
    xlim(tile5,[-0.01, max(0.01,max(VmaxArray(:,k))*1.1)]);
    title(tile5,'Histogram of Vmax');

    %subplot(2, 2, 4);
    tile6 = nexttile(t);
    %plot(tile6,Vamplitude);
    %histogram(tile6,VmaxIndex);
    histogram(tile6,VmaxIndexArray(:,k));
    xlim(tile6,[1, PEAK_LENGTH]);
    title(tile6,'Histogram of VmaxIndex');


    tile7 = nexttile(t);
    plot(tile7,temp_sig, 'g');
    ylim(tile7,[min(-0.01,min(temp_sig)*1.1), max(0.01,max(temp_sig)*1.1)]);
    title(tile7,'100th event waveform');

    tile8 = nexttile(t);
    histogram(tile8,Vamplitude);
    title(tile8,'Amplitude');
    
    tile9 = nexttile(t);
    % 'cumcount'：y 軸為累積事件數（raw count，不 normalize / scale）
    % 舊版：histogram(tile9, toaArray(toaArray(:,3) > 0, 3));
    histogram(tile9, toaArray(toaArray(:,3) ~= -99 , 3)); 
    %ylim(tile9,[-0.05, max(0.1,max(Raw_sig_ave)*1.1)]);
    %title(tile9, sprintf('toa dist. (sys = %.3f ns)', jitter_sys));
    title(tile9, sprintf('toa dist. (sys=%.3f ns) | >0:%d  ~=0:%d  nPass:%d', jitter_sys, sum(toaArray(:,3) > 0), sum(toaArray(:,3) ~= 0), nPass));


    
    % Summary statistic table
    vars = ["File Name";"nPass";"nFail";"nFail_pre";"Effi";"Total";"Jitter (ns)"];
    passEve = [string(file_table(k,:).name);nPass;nFail;nFail_pre;eff(k);nPass+nFail+nFail_pre;jitter_sys];
    Config_name = ["STDEV-CUT";"V-CUT";"DATA-LENGTH";"PEAK-LENGTH";"CONTROAL-REGION";" ";" "];
    Config_cut = [STDEV_CUT;V_CUT;DATA_LENGTH;PEAK_LENGTH;strjoin(string(CONTROL_REGION));" ";" "];
    tdata = table(vars,passEve,Config_name,Config_cut,'VariableNames',{'Variable','Name/ # of Events','Config_name','Value'});
    %uit = uitable(tab(k),"Data",tdata,'Units', 'Normalized','Position', [0.5 0 0.4 0.2]);
    uit = uitable(tab2(k),"Data",tdata,'Position', [20 20 1200 180]); 

end 
% end of loop files

% summary effi plot
tab(k+1)=uitab(tabgroup,'Title', sprintf('Effi'));
ax = uiaxes(tab(k+1), 'Position', [40 40 1200 500]);
%plot(ax,file_table.Vb,eff)
plot(ax,file_table.Ib/1000,eff,'-o','LineWidth',2)
ylim(ax,[-0.1, 1.1]);
title(ax, 'Efficiency vs Bias Current');
%xlabel(ax, 'Bias Voltage (mV)');
xlabel(ax, 'Bias Current (mA)');
ylabel(ax, 'Efficiency');
for k=1:numel(eff)
      text(ax,file_table.Ib(k)/1000,eff(k)+0.05,sprintf('%.3f',eff(k)),'HorizontalAlignment','center');
end


% 將Efficiency保存到 txt 檔案

% Fix: 用 jitter_sys_arr（每檔的 jitter）取代 jitter_sys（只有最後一檔的值）
F = [file_table.Ib, eff, file_table.Vb, amplitude_mean, amplitude_stdev, jitter_sys_arr];
%outputname = [basename, '_',num2str(V_CUT),'_', num2str(STDEV_CUT), '_mV_efficiency.txt'];
outputname = [basename, '_',num2str(V_CUT),'_noSTDEVcut_mV_efficiency.txt'];
save(fullfile(folder_path, outputname), 'F', '-ascii');

%outputnameFig = [basename, '_',num2str(V_CUT),'_', num2str(STDEV_CUT),'.fig'];
outputnameFig = [basename, '_',num2str(V_CUT),'_noSTDEVcut.fig'];
savefig(fig,fullfile(folder_path, outputnameFig));  

outputnameVmax = [basename, '_Vmax.txt'];
save(fullfile(folder_path, outputnameVmax), 'VmaxArray', '-ascii',"-tabs");
outputnameVmax = [basename, '_VmaxIndex.txt'];
save(fullfile(folder_path, outputnameVmax), 'VmaxIndexArray', '-ascii',"-tabs");

outputnameVmax = [basename, '_darkcount.txt'];
save(fullfile(folder_path, outputnameVmax), 'amplitude_effi', '-ascii',"-tabs");

% Jitter 分布：每事件的 toa_diff（Nevent x num_files），-99 表示無效
outputnameJitter = [basename, '_jitterDist.txt'];
save(fullfile(folder_path, outputnameJitter), 'jitterArray', '-ascii',"-tabs");

%disp(['save data to ', fullfile(folder_path, outputname)]);
% save waveform
outputname2 = [basename, '_waveform_all.txt'];
%save(fullfile(folder_path, outputname2), "temp_waveform", '-ascii');

disp(['save data to ', folder_path]);
disp(['Text file name: ', outputname]);

%% function block
function [basename, mV_value, Ib] = extract_info(filename)
    % Extracts the mV value from a filename string.
    % Example: 'SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_100_mV.txt'
    % Output: mV_value, Ib. Type: double, double
    % basenmae: prefix
    % 

    % Regular expression to find the mV value before '_mV'

    % Apply regular expression
    tokens  = regexp(filename, '_(\d+)mV', 'tokens');
    uA      = regexp(filename, '_(\d+)uA', 'tokens');
    prefix  = regexp(filename, '^(.*?Pulse_)', 'tokens');
    Ib      = str2double(uA{1}{1});
    % Check if a match is found
    if ~isempty(tokens)
        basename = prefix{1}{1};
        mV_value = str2double(tokens{1}{1});
        %mV_value = str2double(tokens{1}{2}); % Convert extracted string to number
    else
        error(['No mV value found in filename. filename: ', filename]);
    end
end

function [mV_values, Ib] = extract_mV_from_list(filenames)
    % Extracts mV values from a cell array of filenames.
    % Input: cell array of filenames
    % Output: array of extracted mV values

    mV_values = NaN(length(filenames),1); % Preallocate array for mV values
    Ib = NaN(length(filenames),1); % Preallocate array for mV values

    parfor i = 1:length(filenames)
        [~, mV_values(i), Ib(i)] = extract_info(filenames(i,:).name);
        % mV_values(i) = extract_mV(filenames(i));
    end
end

toc