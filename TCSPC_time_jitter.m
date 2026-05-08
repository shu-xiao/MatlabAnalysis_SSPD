A = load('C:\Users\Peaksea\OneDrive\桌面\APLS\TCSPC\JW SMSPD\NP3uW.txt');
F = zeros(size(A,2),1);
xx = (1:size(A,1));
x = 1:2:size(A,1);
for i = 1:size(A,2)
yy = A(:,i);
y = spline(xx,yy,x);
F(i) = fwhm(x,y)*4;
end