import math

def erf(x):
  #Python 2.7 defines math.erf(), but we need to cater for older versions.
  a = 8*(math.pi-3)/(3*math.pi*(4-math.pi))
  x2 = x*x
  y = -x2 * (4/math.pi + a*x2) / (1 + a*x2)
  return math.copysign(math.sqrt(1 - math.exp(y)), x)

def erf_inv(x):
  # Above erf formula inverted analytically
  a = 8*(math.pi-3)/(3*math.pi*(4-math.pi))
  y = math.log(1-x*x)
  z = 2/(math.pi*a) + y/2
  return math.copysign(math.sqrt(math.sqrt(z*z - y/a) - z), x)

def phi(q):
  # Cumlative distribution function for the standard Gaussian law: quantile -> probability
  return 0.5*(1+erf(q/math.sqrt(2)))

def phi_inv(p):
  # Quantile function for the standard Gaussian law: probability -> quantile
  assert(0 <= p and p <= 1)
  return math.sqrt(2)*erf_inv(2*p-1)

def elo(x):
  assert(0 < x and x < 1)
  return -400*math.log10(1/x-1)

def get_elo(WLD):

  # win/loss/draw ratio
  N = sum(WLD)
  w = float(WLD[0])/N
  l = float(WLD[1])/N
  d = float(WLD[2])/N

  # mu is the empirical mean of the variables (Xi), assumed i.i.d.
  mu = w + d/2

  # stdev is the empirical standard deviation of the random variable (X1+...+X_N)/N
  stdev = math.sqrt(w*(1-mu)**2 + l*(0-mu)**2 + d*(0.5-mu)**2) / math.sqrt(N)

  # 95% confidence interval for mu
  mu_min = mu + phi_inv(0.025) * stdev
  mu_max = mu + phi_inv(0.975) * stdev

  el = elo(mu)
  elo95 = (elo(mu_max) - elo(mu_min)) / 2
  los = phi((mu-0.5) / stdev)

  return el, elo95, los
