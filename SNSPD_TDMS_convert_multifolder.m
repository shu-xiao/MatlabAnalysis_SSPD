P = [0:5:180];
for k = 1:length(P)
% TDMS轉換toolbox地址 不動
TCT_Adress = 'C:\Users\Peaksea\OneDrive\桌面\台大實驗室\Matlab analysis\github_repo (2)';

% TDMS檔地址
TDMS_Adress = strcat('E:\SMSPD1_polarization_TPS2024\20240119\SMSPD_No.2\Polarization_P2(3-12)\4.5K\1uW\',num2str(P(k)),'deg');
% 存檔地址
Save_Adress = strcat('E:\SMSPD1_polarization_TPS2024\20240119\SMSPD_No.2\Polarization_P2(3-12)\4.5K\1uW\',num2str(P(k)),'deg');

% 實驗參數
Exp_para = ''; 
disp(P(k))
cd(Save_Adress)
addpath(TCT_Adress)

Vi = 0; dV = 200; Vf = 2400; % 輸入電壓範圍
Vol = [0:500:5000,5100:100:5500,6000:500:6500];
dT = zeros(length(Vi:dV:Vf),1);

for ii = 1:length(Vol)
    i = Vol(ii);
    filename = strcat(TDMS_Adress, '\', Exp_para, num2str(i), 'mV.tdms');
    % filename = strcat('test.tdms');
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

end



