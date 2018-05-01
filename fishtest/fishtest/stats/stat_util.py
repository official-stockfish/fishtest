from __future__ import division

import math,copy

from fishtest.stats import LLRcalc
from fishtest.stats import sprt

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
  epsilon=1e-3
  x=max(x,epsilon)
  x=min(x,1-epsilon)
  return -400*math.log10(1/x-1)

def L(x):
    return 1/(1+10**(-x/400.0))

def regularize(results):
  """
Introduce a small prior to avoid division by zero
"""
  results=copy.copy(results)
  l=len(results)
  for i in range(0,l):
    if results[i]==0:
      results[i]=1e-3
  return results

def stats(results):
# "results" is an array of length 2*n+1 with aggregated frequences
# for n games
  l=len(results)
  N=sum(results)
  games=N*(l-1)/2.0

# empirical expected score for a single game
  mu=sum([results[i]*(i/2.0) for i in range(0,l)])/games

# empirical expected variance for a single game
  mu_=(l-1)/2.0*mu
  var=sum([results[i]*(i/2.0-mu_)**2.0 for i in range(0,l)])/games

  return games,mu,var

def get_elo(results):
# "results" is an array of length 2*n+1 with aggregated frequences
# for n games

  results=regularize(results)
  games,mu,var=stats(results)
  stdev = math.sqrt(var)

# 95% confidence interval for mu
  mu_min=mu+phi_inv(0.025)*stdev/math.sqrt(games)
  mu_max=mu+phi_inv(0.975)*stdev/math.sqrt(games)

  el=elo(mu)
  elo95=(elo(mu_max)-elo(mu_min))/2.0
  los = phi((mu-0.5)/(stdev/math.sqrt(games)))

  return el,elo95,los


def bayeselo_to_proba(elo, drawelo):
  """
  elo is expressed in BayesELO (relative to the choice drawelo).
  Returns a probability, P[2], P[0], P[1] (win,loss,draw).
  """
  P = 3*[0]
  P[2] = 1.0 / (1.0 + pow(10.0, (-elo + drawelo) / 400.0))
  P[0] = 1.0 / (1.0 + pow(10.0, (elo + drawelo) / 400.0))
  P[1] = 1.0 - P[2] - P[0]
  return P

def proba_to_bayeselo(P):
  """
  Takes a probability: P[2], P[0]
  Returns elo, drawelo
  """
  assert(0 < P[2] and P[2] < 1 and 0 < P[0] and P[0] < 1)
  elo = 200 * math.log10(P[2]/P[0] * (1-P[0])/(1-P[2]))
  drawelo = 200 * math.log10((1-P[0])/P[0] * (1-P[2])/P[2])
  return elo, drawelo

def draw_elo_calc(R):
  """
  Takes trinomial frequences R[0],R[1],R[2]
  (loss,draw,win) and returns the corresponding
  drawelo value.
  """
  N=sum(R)
  P=[p/N for p in R]
  _, drawelo = proba_to_bayeselo(P)
  return drawelo

def bayeselo_to_elo(belo, drawelo):
  P = bayeselo_to_proba(belo, drawelo)
  return elo(P[2]+0.5*P[1])

def elo_to_bayeselo(elo, draw_ratio):
  assert(draw_ratio>=0)
  s=L(elo)
  P=3*[0]
  P[2]=s-draw_ratio/2.0
  P[1]=draw_ratio
  P[0]=1-P[1]-P[2]
  if P[0]<=0 or P[2]<=0:
    return float('NaN'),float('NaN')
  return proba_to_bayeselo(P)

def SPRT_elo(R, alpha=0.05, beta=0.05, p=0.05, elo0=None, elo1=None, elo_model=None):
  """
  Calculate an elo estimate from an sprt test.
  """
  assert(elo_model in ['BayesElo','logistic'])

  # Estimate drawelo out of sample
  R3=regularize([R['losses'],R['draws'],R['wins']])
  drawelo=draw_elo_calc(R3)

  # Convert the bounds to logistic elo if necessary
  if elo_model=='BayesElo':
    lelo0,lelo1=[bayeselo_to_elo(elo_, drawelo) for elo_ in (elo0,elo1)]
  else:
    lelo0,lelo1=elo0,elo1

  # Make the elo estimation object
  sp=sprt.sprt(alpha=alpha,beta=beta,elo0=lelo0,elo1=lelo1)

  # Feed the results
  if 'pentanomial' in R.keys():
    R_=R['pentanomial']
  else:
    R_=R3
  sp.set_state(R_)

  # Get the elo estimates
  a=sp.analytics(p)

  # Override the LLR approximation with the exact one
  a['LLR']=LLRcalc.LLR_logistic(lelo0,lelo1,R_)[0]
  del a['clamped']
  # Now return the estimates
  return a


def SPRT(R, elo0, alpha, elo1, beta, elo_model=None):
  """
  Sequential Probability Ratio Test
  H0: elo = elo0
  H1: elo = elo1
  alpha = max typeI error (reached on elo = elo0)
  beta = max typeII error for elo >= elo1 (reached on elo = elo1)
  R['wins'], R['losses'], R['draws'] contains the number of wins, losses and draws
  R['pentanomial'] contains the pentanomial frequencies
  elo_model can be either 'BayesElo' or 'logistic'

  Returns a dict:
  finished - bool, True means test is finished, False means continue sampling
  state - string, 'accepted', 'rejected' or ''
  llr - Log-likelihood ratio
  lower_bound/upper_bound - SPRT bounds
  """
  assert(elo_model in ['BayesElo','logistic'])

  result = {
    'finished': False,
    'state': '',
    'llr': 0.0,
    'lower_bound': math.log(beta/(1-alpha)),
    'upper_bound': math.log((1-beta)/alpha),
  }
  R3=regularize([R['losses'],R['draws'],R['wins']])
  if elo_model=='BayesElo':
    # Estimate drawelo out of sample
    drawelo=draw_elo_calc(R3)

    # Probability laws under H0 and H1
    P0 = bayeselo_to_proba(elo0, drawelo)
    P1 = bayeselo_to_proba(elo1, drawelo)

    # Conversion of bounds to logistic elo
    lelo0=elo(P0[2]+0.5*P0[1])
    lelo1=elo(P1[2]+0.5*P1[1])
  else:
    lelo0=elo0
    lelo1=elo1

  # Log-Likelihood Ratio
  if 'pentanomial' in R.keys():
    LLR_,overshoot=LLRcalc.LLR_logistic(lelo0,lelo1,R['pentanomial'])
    result['llr']=LLR_
  else:
    if elo_model=='BayesElo': # legacy code, we keep it in order not to change
                              # the LLR of prior tests
      result['llr']=sum([R3[i]*math.log(P1[i]/P0[i]) for i in range(0,len(R3))])
      overshoot=0
    else:
      LLR_,overshoot=LLRcalc.LLR_logistic(lelo0,lelo1,R3)
      result['llr']=LLR_

  # bound estimated overshoot for safety
  overshoot=min((result['upper_bound']-result['lower_bound'])/20,overshoot)

  if result['llr'] < result['lower_bound']+overshoot:
    result['finished'] = True
    result['state'] = 'rejected'
  elif result['llr'] > result['upper_bound']-overshoot:
    result['finished'] = True
    result['state'] = 'accepted'

  return result

if __name__ == "__main__":
  # unit tests
  print('SPRT tests')
  print(SPRT({'wins': 0, 'losses': 0, 'draws': 0}, 0, 0.05, 5, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 10, 'losses': 0, 'draws': 0}, 0, 0.05, 5, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 100, 'losses': 0, 'draws': 0}, 0, 0.05, 5, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 10, 'losses': 0, 'draws': 20}, 0, 0.05, 5, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 10, 'losses': 1, 'draws': 20}, 0, 0.05, 5, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 5019, 'losses': 5026, 'draws': 15699}, 0, 0.05, 5, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 1450, 'losses': 1500, 'draws': 4000}, 0, 0.05, 6, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 716, 'losses': 591, 'draws': 2163}, 0, 0.05, 6, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 13543,'losses': 13624, 'draws': 34333}, -3, 0.05, 1, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 13543,'losses': 13624, 'draws': 34333, 'pentanomial':[1187, 7410, 13475, 7378, 1164]}, -3, 0.05, 1, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 65388,'losses': 65804, 'draws': 56553}, -3, 0.05, 1, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 65388,'losses': 65804, 'draws': 56553, 'pentanomial':[10789, 19328, 33806, 19402, 10543]}, -3, 0.05, 1, 0.05, elo_model='BayesElo'))
  print(SPRT({'wins': 65388,'losses': 65804, 'draws': 56553, 'pentanomial':[10789, 19328, 33806, 19402, 10543]}, -3, 0.05, 1, 0.05, elo_model='logistic'))
  print('elo tests')
  print(SPRT_elo({'wins': 0, 'losses': 0, 'draws': 0}, elo0=0,  elo1=5, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 10, 'losses': 0, 'draws': 0}, elo0=0,  elo1=5, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 100, 'losses': 0, 'draws': 0}, elo0=0,  elo1=5, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 10, 'losses': 0, 'draws': 20}, elo0=0,  elo1=5, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 10, 'losses': 1, 'draws': 20}, elo0=0,  elo1=5, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 5019, 'losses': 5026, 'draws': 15699}, elo0=0,  elo1=5, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 1450, 'losses': 1500, 'draws': 4000}, elo0=0,  elo1=6, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 716, 'losses': 591, 'draws': 2163}, elo0=0,  elo1=6, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 13543,'losses': 13624, 'draws': 34333}, elo0=-3,  elo1=1, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 13543,'losses': 13624, 'draws': 34333, 'pentanomial':[1187, 7410, 13475, 7378, 1164]}, elo0=-3,  elo1=1, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 65388,'losses': 65804, 'draws': 56553}, elo0=-3,  elo1=1, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 65388,'losses': 65804, 'draws': 56553, 'pentanomial':[10789, 19328, 33806, 19402, 10543]}, elo0=-3,  elo1=1, elo_model='BayesElo'))
  print(SPRT_elo({'wins': 65388,'losses': 65804, 'draws': 56553, 'pentanomial':[10789, 19328, 33806, 19402, 10543]}, elo0=-3,  elo1=1, elo_model='logistic'))
