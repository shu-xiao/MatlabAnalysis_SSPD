cd('F:\20230826_SMSPD_Polarization\P1 good') 
P = [4:7.5:184];
for k = 1:length(P)
Save_Adress = strcat('4.5K_1.2uW_',num2str(P(k)));
mkdir(strcat('4.5K_1.2uW_',num2str(P(k))))
end