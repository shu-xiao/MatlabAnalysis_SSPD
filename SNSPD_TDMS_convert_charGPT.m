% TDMS轉換toolbox地址 不動
TCT_Adress = 'C:\Users\Peaksea\OneDrive\桌面\台大實驗室\Matlab analysis\github_repo (2)';

% TDMS檔地址
TDMS_Adress = 'E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\450\10000kHz\5000nW\0degrees\20240520_153645';
% 存檔地址
Save_Adress = 'E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\450\10000kHz\5000nW\0degrees\20240520_153645';

% 實驗參數
Exp_para = 'BroadbandSMSPD_20240519_P1_Pulse_450_5000nW_0degrees_';

% 改變當前工作目錄
cd(Save_Adress);
% 添加TDMS轉換工具的路徑
addpath(TCT_Adress);

% 定義電壓範圍
Vol = [500:500:6000, 6100:100:8500];
num_files = length(Vol);

% 預分配記憶體空間
dT = zeros(num_files, 1);

% 迴圈處理每個電壓值
for ii = 1:num_files
    voltage = Vol(ii);
    filename_TDMS = fullfile(TDMS_Adress, [Exp_para, num2str(voltage), 'mV.tdms']);
    filename_new = fullfile(Save_Adress, [Exp_para, num2str(voltage), '_mV.txt']);
    
    % 檢查檔案是否存在
    if exist(filename_TDMS, 'file') == 2
        % 轉換TDMS檔案
        A = convertTDMS(0, filename_TDMS);
        
        % 提取信號和觸發數據
        signal = A.Data.MeasuredData(3).Data;  
        trigger = A.Data.MeasuredData(4).Data;  
        
        % 保存數據到txt文件
        F = [signal, trigger];
        save(filename_new, 'F', '-ascii');
        
        % 計算dT並保存
        dT(ii) = str2double(A.Data.Root.Property(15).Value) / str2double(A.Data.Root.Property(9).Value) * 1e-9; % 奈秒  
        
        % 刪除臨時mat文件
        delete(fullfile(Save_Adress, [Exp_para, num2str(voltage), 'mV.mat']));
    else
        warning('檔案 %s 不存在，跳過該檔案。', filename_TDMS);
    end
end

% 儲存 dT 結果到文件
save(fullfile(Save_Adress, 'dT_results.mat'), 'dT');
