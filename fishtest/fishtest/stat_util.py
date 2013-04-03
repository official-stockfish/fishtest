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

def bayeselo_to_proba(elo, drawelo):
	"""
	elo is expressed in BayesELO (relative to the choice drawelo).
	Returns a probability, P['win'], P['loss'], P['draw']
	"""
	P = {'win': 0.0, 'loss': 0.0, 'draw': 0.0}
	P['win'] = 1.0 / (1.0 + pow(10.0, (-elo + drawelo) / 400.0))
	P['loss'] = 1.0 / (1.0 + pow(10.0, (elo + drawelo) / 400.0))
	P['draw'] = 1.0 - P['win'] - P['loss']
	return P

def SPRT(R, elo0, alpha, elo1, beta, drawelo):
	"""
	Sequential Probability Ratio Test
	H0: elo = elo0
	H1: elo = elo1
	alpha = max typeI error (reached on elo = elo0)
	beta = max typeII error for elo >= elo1 (reached on elo = elo1)
	R['wins'], R['losses'], R['draws'] contains the number of wins, losses and draws

	Returns a tuple
	True, 'H0': stop and accept H0
	True: 'H1': stop and accept H1
	False, '': continue sampling
	"""
	# Probability laws under H0 and H1
	P0 = bayeselo_to_proba(elo0, drawelo)
	P1 = bayeselo_to_proba(elo1, drawelo)

	# Log-Likelyhood Ratio
	LLR = R['wins']*math.log(P1['win']/P0['win']) + R['losses']*math.log(P1['loss']/P0['loss']) + R['draws']*math.log(P1['draw']/P0['draw'])

	# See if the LLR has crossed the bounds
	lower_bound = math.log(beta/(1-alpha))
	upper_bound = math.log((1-beta)/alpha)

	if LLR < lower_bound:
		return True, 'H0'
	elif upper_bound:
		return True, 'H1'
	else:
		return False, ''
