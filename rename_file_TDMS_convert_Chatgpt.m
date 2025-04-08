% parpool("Processes",4)
tStart = tic;
% 資料夾路徑
folder_path = 'D:\SNSPD_data\12K_515nm_30000nW\0degrees\20250106_213747';
%folder_path = 'E:\SMSPD_NbTiN_1\Laser\1-1\20250108\12\Pulse\450\10000kHz\800nW\0degrees\20250108_011217';


% 儲存檔案地址
Save_Adress = folder_path;
% Save_Adress = 'E:\SNSPD_data'; 

% 資料夾中的所有 TDMS 檔案
file_list = dir(fullfile(folder_path, '*.tdms'));
if(isempty(file_list))
    warning('Cannot find TDMS file!');
end

% 實驗參數
% Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_450_800nW_0degrees_';
Exp_para = 'SMSPD_NbTiN_1_1-1_Pulse_515_30000nW_0degrees_';
pattern = 'Pulse_\d+_\d+nW_\d+degrees';  %% generate output dir name
%dir_name = regexp(Exp_para, pattern, 'match', 'once');
dir_name = regexp(file_list(1).name, pattern, 'match', 'once');



% 初始化一個結構數組來存儲轉換後的數據
converted_data = struct('voltage', [], 'signal', [], 'trigger', []);

%number_TDMSfiles = length(file_list);
number_TDMSfiles = 8;
% 讀取和轉換所有 TDMS 檔案
t1 = toc(tStart);
tStart = tic;
parfor i = 1:number_TDMSfiles
    % 原始檔案名稱（包含路徑）
    original_filename = fullfile(folder_path, file_list(i).name);

    % 提取電壓值
    voltage_match = regexp(file_list(i).name, '_\d+mV', 'match');
    voltage = str2double(extractBetween(voltage_match{1}, 2, strlength(voltage_match{1}) - 2));

    % 轉換 TDMS 檔案
    filename_TDMS = fullfile(folder_path, file_list(i).name);
    if exist(filename_TDMS, 'file') == 2
        % 轉換 TDMS 檔案
        A = convertTDMS(0, filename_TDMS);

        % 提取信號和觸發數據
        signal = A.Data.MeasuredData(3).Data;
        trigger = A.Data.MeasuredData(4).Data;

        % 存儲轉換後的數據
        converted_data(i).voltage = voltage;
        converted_data(i).signal = signal;
        converted_data(i).trigger = trigger;

        disp([int2str(i),'/',int2str(length(file_list)),'  檔案轉換成功: ', original_filename]);
    else
        warning('檔案 %s 不存在，跳過該檔案。', filename_TDMS);
    end
end
t2 = toc(tStart);
tStart = tic;

% 將轉換後的數據保存到 txt 檔案
if  ~exist(fullfile(Save_Adress,dir_name), 'dir')  % Check if the directory exists
    mkdir(fullfile(Save_Adress,dir_name));  % Create the directory if it does not exist
    fprintf('Directory "%s" created.\n', fullfile(Save_Adress,dir_name));
end

%%
disp(['Data is saved in ',fullfile(Save_Adress,dir_name)]);


for i = 1:number_TDMSfiles
    % 構造新檔案名稱
    filename_new = fullfile(Save_Adress,dir_name, [Exp_para, num2str(converted_data(i).voltage), '_mV.txt']);

    % 保存數據到 txt 文件
    F = [converted_data(i).signal,  converted_data(i).trigger];
    save(filename_new, 'F', '-ascii');  %% need to parallel
    disp([int2str(i),'/',int2str(length(converted_data)),' output file name: ', fullfile([Exp_para, num2str(converted_data(i).voltage), '_mV.txt'])])
end


disp('Done')
disp(['Data is saved in ',fullfile(Save_Adress,dir_name)]);
t3 = toc(tStart);

%% test code

% 
% disp('new test')
% filename_new = strings(1, 8); 
% fid = double(8);
% parfor i = 1:length(5)
%     % Generate file name
%     filename_new(i) = ['testttt',num2str(i),'.txt'];
%     % Extract data: assumed to be N×2 matrix
%     %F = [converted_data(i).signal, converted_data(i).trigger];
%     % Open file for writing
%     disp(filename_new(i));
%     fid = fopen(filename_new(i), 'w');
%     if fid == -1
%         warning('Could not open file: %s', filename_new(i));
%         continue;
%     end
% 
%     % Write each row with scientific notation and 7 decimal places
%     for j = 1:100 %size(converted_data(i).signal,1)
%         %fprintf(fid, '%f\t%f\n', converted_data(i).signal(j), converted_data(i).trigger(j));
%     end
% 
%     fclose(fid);
% 
%     % Optional: display progress
%     fprintf('%d/%d saved: %s\n', i, length(converted_data), filename_new(i));
% end
% disp('done');