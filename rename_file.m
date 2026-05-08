% 指定要處理的資料夾
folder_path = 'E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\450\10000kHz\5000nW\0degrees\20240520_153645';

% 獲取資料夾中的所有檔案
file_list = dir(fullfile(folder_path, '*.tdms'));

% 使用迴圈遍歷每個檔案
for i = 1:length(file_list)
    % 原始檔案名稱（包含路徑）
    original_filename = fullfile(folder_path, file_list(i).name);
    
    % 找到並提取uA部分的值
    ua_part = regexp(file_list(i).name, '_\d+uA_', 'match');
    
    % 找到並提取mV部分的值
    mv_part = regexp(file_list(i).name, '_\d+mV_', 'match');
    
    % 如果找到uA和mV部分，則進行重命名
    if ~isempty(ua_part) && ~isempty(mv_part)
        % 移除uA部分
        new_filename = strrep(file_list(i).name, ua_part{1}, '_');
        
        % 移除後綴的日期時間部分
        new_filename = regexprep(new_filename, '_\d{8}_\d{6}', '');
        
        % 新檔案名稱（包含路徑）
        new_full_filename = fullfile(folder_path, new_filename);
        
        % 顯示新檔案名稱以進行檢查
        disp(['將檔案: ', original_filename, ' 重命名為: ', new_full_filename]);
        
        % 重命名檔案
        status = movefile(original_filename, new_full_filename);
        if status
            disp(['檔案已成功重命名為: ', new_full_filename]);
        else
            disp(['檔案重命名失敗: ', original_filename]);
        end
    else
        disp(['檔案格式不符合要求: ', original_filename]);
    end
end
