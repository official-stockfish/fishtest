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
