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

%% Test code 4
fig = uifigure('Name', 'Tab Example');

% Create tab group
tg = uitabgroup(fig);

% Create tabs
tab1 = uitab(tg, 'Title', 'Controls');
tab2 = uitab(tg, 'Title', 'Plot');
tab3 = uitab(tg, 'Title', 'Table');
ax = uiaxes(tab2, 'Position', [20 20 400 250]);
x = linspace(0, 2*pi, 100);
y = sin(x);
plot(ax, x, y);
title(ax, 'Sine Wave');

% --- Tab 3: Add a table ---
%% Test code 5
% Example data setup
num_plots = 4;  % Change this to however many plots you need
x = linspace(0, 2*pi, 100);

% Create the UI figure and tab group
fig = uifigure('Name', 'Multi-Tab Plots', 'Position', [100 100 800 600]);
tg = uitabgroup(fig, 'Position', [50 50 700 500]);

% Loop to create tabs and plots
for i = 1:num_plots
    % Create a new tab
    tab = uitab(tg, 'Title', ['Plot ' num2str(i)],'Units','normalized');
    tab.Scrollable = 'on';

    
    % Create axes in the tab
    ax = uiaxes(tab, 'Position', [50 50 700 500]);
    
    % Generate example plot
    y = sin(x + i);  % Varying sine wave
    plot(ax, x, y);
    title(ax, ['Sine Wave #' num2str(i)]);
end
savefig(fig,'C:\Users\user\Downloads\testout.fig')
%% testt
fig = uifigure;
vars = ["dd";"nPass";"nFail";"nFail_pre";"Total"];
gg = ["ee";3;5;2;7];
tdata = table(vars,gg,'VariableNames',{'Date',' '});
uit = uitable(fig,"Data",tdata);

%%
fig = uifigure('Name', 'Multi-Tab Plots', 'Position', [40 80 1400 700]);
tabgroup = uitabgroup(fig, 'Position', [20 20 1300 650]);
k=1;
tab(k)=uitab(tabgroup,'Title', sprintf('Tab_%i', k));
vars = ["File Name";"nPass";"nFail";"nFail_pre";"Total"];
    passEve = ["ee";3;4;5;6];
    tdata = table(vars,passEve,'VariableNames',{'Variable',' # of Events'});
    uit = uitable(tab(k),"Data",tdata,'Units', 'Normalized','Position', [0.5 0.0 0.4 0.2]);
savefig(fig,'gggggg.fig');