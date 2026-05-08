S = load('C:\Users\Peaksea\OneDrive\桌面\台大實驗室\Matlab analysis\IPcurve.txt');
Tc = 12;
T = 4.5;
w = 4000*10^-9;
d = 15*10^-9;
D = 0.7*10^-4; %0.7
tauD = (w^2/(16*D));
E0 = 4 * 16*10^46 * (1.38*10^-23 * Tc)^2; %25.5*(10^9)^3

a = tauD / ((E0*w^2*d)*10^9);
1/a
E0*w^2*d/(1.6*10^-19);
%a = 1/400; %1/400

p1 = S(:,1) *a;
p2 = S(:,2) *a;
p3 = S(:,3) *a;

I1 = S(:,4);
I2 = S(:,5);
I3 = S(:,6);
N = 800;
G = [0.2 2 14];
X = zeros(size(G,2)*2,N);

plot(p1, I1,'bo', p2, I2, 'go', p3, I3, 'ro')
hold on


for g = G
    

    dT = linspace(0, 0.3*Tc, N);
    Te = T + dT;

    P = E_e(Te,Tc) + E_ph(Te,Tc,g) - (E_e(T,Tc) + E_ph(T,Tc,g));
    I = I_det(Te, Tc)/I_det(T, Tc);
    plot(P, I)
    xlim([0, 1])
    ylim([0.2, 1.1])
    ES = zeros(1,size(Te,2));
    hold on

    for i = 1:size(Te,2)
        ES(i) = E_s(Te(i),Tc);
    end
    q = find(G==g);
    X(2*q-1:2*q,:) = [P; I];
    
end
X = X';
%%
g=1;
 Tc = 10;
 T= Tc/2;
Te = 0.5*Tc;
P = E_e(Te,Tc) + E_ph(Te,Tc,g) - (E_e(T,Tc) + E_ph(T,Tc,g))
    I = I_det(Te, Tc)
%%
[Te' P' I' ];
plot(Te/Tc, P)

%%
Tc = 10;
dT = linspace(0, 0.999, 100)*Tc;
Te = dT;
for T = 0:1:Tc

%     T = 4.599; %6.395
    g = 1;
    I = I_det(T, Tc)/0.6495; 
    P = E_e(Te,Tc) + E_ph(Te,Tc,g) - (E_e(T,Tc) + E_ph(T,Tc,g));
    plot((Te)/Tc, P, '*-')
    hold on
end
%%
Tc = 10;
dT = linspace(0, 1, 100)*Tc;
T = 4.599;
Te = dT;

g = 1;
P = (pi^2)/12 *(Te/Tc).^2  ; %+ E_ph(Te,Tc,g)
PP =  E_s(Te,Tc) ;
plot((Te)/Tc, P, (Te)/Tc, PP,(Te)/Tc, P-PP, '*-')

%%
function Eph = E_ph(T,Tc,g)

 Eph = 1/g *(pi^4)/15 *(T/Tc).^4;

end

function Ee = E_e(T,Tc)

 Ee = (pi^2)/12 *(T/Tc).^2 - E_s(T,Tc);

end

function Es = E_s(T,Tc)
    g = 1.76;
    if T <= Tc
        Es = ( g/2 * tanh(1.74*sqrt(Tc./T-1)) ).^2 ...
           .* ( 1 - 0.053 * (g * tanh(1.74*sqrt((Tc./T)-1))).^2 ...
              - 0.1 * tanh(1.74*sqrt(Tc./T-1)).^4 ...
              - 0.236 * exp(-12*(1 - tanh(1.74*sqrt(Tc./T-1))).^0.7) );
    else
        Es = 0;
    end
end

function f = I_det(T, Tc)

%   f = (1-(T/Tc).^2).^(3/2) ...
%       ./ ( (1-(T/Tc).^2) .* (1-(T/Tc).^4).^(0.5) ) ;
     f = (1-(T/Tc).^2).^(3/2);
end
