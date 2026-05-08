%% test file
import SMSPD_waveform_plot_ChatGPT.*
disp('gg')
%%
path = 'E:\SMSPD_NbTiN_1\Laser\1-1\20250107\12\Pulse\450\10000kHz\30000nW\0degrees\20250107_232827\Pulse_450_30000nW_0degrees';
file_list = dir(fullfile(path, '*.txt'));

% disp(file_list(1).name);
disp(extract_info('SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_100_mV'));
Va = sort(extract_info(file_list));

%% 
function [basename, mV_value] = extract_info(filename)
    % Extracts the mV value from a filename string.
    % Example: 'SMSPD_NbTiN_1_1-1_Pulse_450_30000nW_0degrees_100_mV.txt'
    % Output: 100

    % Regular expression to find the mV value before '_mV'
    pattern = '(.*)_(\d+)_mV';

    % Apply regular expression
    tokens = regexp(filename, pattern, 'tokens');

    % Check if a match is found
    if ~isempty(tokens)
        basename = tokens{1}{1};
        mV_value = str2double(tokens{1}{2}); % Convert extracted string to number
    else
        error('No mV value found in filename.');
    end
end

function mV_values = extract_mV_from_list(filenames)
    % Extracts mV values from a cell array of filenames.
    % Input: cell array of filenames
    % Output: array of extracted mV values

    mV_values = NaN(size(filenames)); % Preallocate array for mV values

    for i = 1:length(filenames)
        [~,mV_values(i)] = extract_info(filenames(i).name);
        %% mV_values(i) = extract_mV(filenames(i));
    end
end


%% block one
disp('1');
%% block two
disp('2');