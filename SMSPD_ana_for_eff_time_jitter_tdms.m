% D:\Lu lab\NbN\NbN superconductor\低溫\20230706_SMSPD\p2_2.5Mhz_4.5K_0.27uw_5photon
Exp_para = '';
Va = [500:500:6000,6100:100:8000];
eff = zeros(length(Va),1);
for k =1:length(Va)
close all
d = load(strcat(Exp_para,num2str(Va(k)),'_mV.txt'));
signal = d(:,2);
trigger = d(:,1);
clear d
event = 9998; % 1 to 10000
q = zeros(1000,1);
X = 0;
Z = NaN(event,1);
jitter = NaN(event,1);
sigma = zeros(event,1);
stdth = 0.08; %璅?榆??? 0.03 0.04
ds1th = 0.05; % 閮??? 0.1 0.2 0.15
for i = 1:event %[6200,3001] 
    r = (1:1000) + 1000*(i);
    
    s = signal(r);
%     tr = trigger(r);】
    sigma(i) = std(s(1:126));
    if sigma(i) <= stdth
        q = s + q;
        s1= s(1:1000); % 405:435 (200:263) 0P(220:240)
        sbg= s(((1:126)));
        Z(i)= (max(s1)-min(s1)) ;
%         Z(i) = trapz((s1)) - trapz((sbg));
        ds1 = diff(s1);
        dtr = diff(trigger(r));
        
        nds1 = find( ds1 == max(ds1) );
        ntr = find( dtr == max(dtr) );
        jitter(i) = ntr(1) - nds1(1);
    %     subplot(2,1,1)
    %     plot(trigger(r)) 
    subplot(2,2,1)
        plot(s1,'g')
        hold on
    subplot(2,2,3)
        plot(ds1,'g')
        hold on
%         pause(0.001)
    count = length(find(ds1 > ds1th)); % 閮????????
        if count >= 2
            count = 1;
        end
        X = X + count;
    
    else
%         Z(i) = NaN;
    end

end
subplot(2,2,[2,4])
    histogram(sort(sigma)) % 閮???榆蝯梯??
Ef_event = length(find(sigma <= stdth)); % ?????????辣敺????辣?
eff(k) = X/Ef_event; % 閮????
AA = [Va'/1000, eff]
clear signal trigger
end
save(strcat(Exp_para,num2str(Va(k)),num2str(ds1th),num2str(stdth),'_mV_+V_efficiency.txt'),'eff','-ascii')

%% Photon Distribution
ZZ = sort(Z);
subplot(1,3,1)
plot((ZZ),'.')
subplot(1,3,2)
histogram(ZZ,200)

Vmax = max(ZZ);Vmin = min(ZZ);
t = 85;
dV = (Vmax-Vmin)/t;
ph = zeros(t,1);
V = linspace(Vmin, Vmax, t);
for i = 1:t
    q1 = find(ZZ <= Vmin + i*dV);
    if i == 1
        ph(i) = length(q1);
    else
        ph(i) = length(q1) - sum(ph(1:i));
    end
end
pn = 0:300;
an = 2;
poisson = exp(-an) * an.^pn ./ factorial(pn);
max(poisson)
subplot(1,3,3)
plot(V, ph/Ef_event, '.-') % , pn, poisson, 'k*'
ph_dis = [V', ph/Ef_event];
%% Poisson Distribution
x = 2.5*26/40;
Po = zeros(51,5);
i = 1;
for an = [3,4,5,10,15,20]
pn = 0:50;
poisson = exp(-an) * an.^pn ./ factorial(pn);
max(poisson)
plot(pn, poisson, '*-') % ,
Po(:,i) = poisson;
hold on
i=i+1;
end
%% Time jitter
Tr = 4*10^-10;
maxj = max(jitter);
minj = min(jitter);
T = minj:0.01:maxj;
dT = T(2) - T(1);
j = zeros(length(T),1);
for i = 1:length(T)
    j1 = find(jitter <= minj + i*dT);
    if i == 1
        j(i) = length(j1);
    else
        j(i) = length(j1) - sum(j(1:i));
    end
end
plot(T,j)
%% dark
dark = zeros(5000,length(Va));
DC = zeros(1,length(Va));
for k = 1:length(Va)
close all
d = load(strcat(Exp_para,num2str(Va(k)),'_mV.txt'));
dark(:,k) = d(1:5000,1);
DC(k) = length(find(islocalmax(dark(:,k),'MinProminence',0.001)==1));
clear d
end