% TDMS轉換toolbox地址 不動
TCT_Adress = 'C:\Users\Peaksea\OneDrive\桌面\台大實驗室\Matlab analysis\github_repo (2)';

% TDMS檔地址
TDMS_Adress ='E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\450\10000kHz\2000nW\0degrees\20240520_152049';
% 存檔地址
Save_Adress ='E:\Peaksea\paper\broadbandSMSPD\BroadbandSMSPD_20240519\Laser\P1\20240520\4.5\Pulse\450\10000kHz\2000nW\0degrees\20240520_152049';

% 實驗參數
Exp_para = 'BroadbandSMSPD_20240519_P1_Pulse_450_2000nW_0degrees_'; 

cd(Save_Adress)
addpath(TCT_Adress)

%Vi = 0; dV = 200; Vf = 2400; % 輸入電壓範圍
Vol = [500:500:6000,6100:100:8500];
dT = zeros(length(Vi:dV:Vf),1);
%%
for ii = 1:length(Vol)
    i = Vol(ii);
    filename = strcat(TDMS_Adress, '\', Exp_para ,num2str(i), 'mV.tdms');
    %filename = strcat('test.tdms');
    A = convertTDMS(0,filename);
    signal = A.Data.MeasuredData(3).Data;  
    trigger= A.Data.MeasuredData(4).Data;  
    F = [signal, trigger];
    save(strcat(Exp_para,num2str(i),'_mV.txt'),'F','-ascii')
    dT(ii) = str2double(cell2mat(A.Data.Root.Property(15).Value)) / ...
    str2double(cell2mat(A.Data.Root.Property(9).Value))*10^-9; % 奈秒  
    delete(strcat(Exp_para, num2str(i), 'mV.mat'));
    clear F signal trigger
end



