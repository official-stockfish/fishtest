from __future__ import division
from scipy.optimize import brentq
import math,copy

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

def get_elo(results):
# "results" is an array of length 2*n+1 with aggregated frequences
# for n games
  l=len(results)

# avoid division by zero
  results=regularize(results)
  N=sum(results)
  games=N*(l-1)/2.0

# empirical expected score for a single game
  mu=sum([results[i]*(i/2.0) for i in range(0,l)])/games

# empirical expected variance for a single game
  mu_=(l-1)/2.0*mu
  var=sum([results[i]*(i/2.0-mu_)**2.0 for i in range(0,l)])/games

# matching standard deviation
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
  Returns a probability, P['win'], P['loss'], P['draw']
  """
  P = {}
  P['win'] = 1.0 / (1.0 + pow(10.0, (-elo + drawelo) / 400.0))
  P['loss'] = 1.0 / (1.0 + pow(10.0, (elo + drawelo) / 400.0))
  P['draw'] = 1.0 - P['win'] - P['loss']
  return P

def proba_to_bayeselo(P):
  """
  Takes a probability: P['win'], P['loss']
  Returns elo, drawelo
  """
  assert(0 < P['win'] and P['win'] < 1 and 0 < P['loss'] and P['loss'] < 1)
  elo = 200 * math.log10(P['win']/P['loss'] * (1-P['loss'])/(1-P['win']))
  drawelo = 200 * math.log10((1-P['loss'])/P['loss'] * (1-P['win'])/P['win'])
  return elo, drawelo

def SPRT(R, elo0, alpha, elo1, beta, drawelo):
  """
  Sequential Probability Ratio Test
  H0: elo = elo0
  H1: elo = elo1
  alpha = max typeI error (reached on elo = elo0)
  beta = max typeII error for elo >= elo1 (reached on elo = elo1)
  R['wins'], R['losses'], R['draws'] contains the number of wins, losses and draws
  R['pentanomial'] contains the pentanomial frequencies

  The drawelo parameter is a historical artifact and is not used.

  Returns a dict:
  finished - bool, True means test is finished, False means continue sampling
  state - string, 'accepted', 'rejected' or ''
  llr - Log-likelihood ratio
  lower_bound/upper_bound - SPRT bounds
  """

  result = {
    'finished': False,
    'state': '',
    'llr': 0.0,
    'lower_bound': math.log(beta/(1-alpha)),
    'upper_bound': math.log((1-beta)/alpha),
  }

  # Estimate drawelo out of sample
  if (R['wins'] > 0 and R['losses'] > 0 and R['draws'] > 0):
    N = R['wins'] + R['losses'] + R['draws']
    P = {'win': float(R['wins'])/N, 'loss': float(R['losses'])/N, 'draw': float(R['draws'])/N}
    elo, drawelo = proba_to_bayeselo(P)
  else:
    return result

  # Probability laws under H0 and H1
  P0 = bayeselo_to_proba(elo0, drawelo)
  P1 = bayeselo_to_proba(elo1, drawelo)

  # Conversion of bounds to logistic elo for use with the pentanomial model
  scale_factor = (4*10**(-drawelo/400.0))/(1+10**(-drawelo/400.0))**2
  lelo0=scale_factor*elo0
  lelo1=scale_factor*elo1

  # Log-Likelihood Ratio
  if 'pentanomial' in R.keys():
    LLR_,overshoot=LLR_logistic(lelo0,lelo1,R['pentanomial'])
    overshoot=min((result['upper_bound']-result['lower_bound'])/20,overshoot)
    result['llr']=LLR_
  else:
    result['llr'] = R['wins']*math.log(P1['win']/P0['win']) + R['losses']*math.log(P1['loss']/P0['loss']) + R['draws']*math.log(P1['draw']/P0['draw'])
    overshoot=0

  if result['llr'] < result['lower_bound']+overshoot:
    result['finished'] = True
    result['state'] = 'rejected'
  elif result['llr'] > result['upper_bound']-overshoot:
    result['finished'] = True
    result['state'] = 'accepted'

  return result

def MLE(pdf,s):
    """
This function computes the maximum likelood estimate for
a discrete distribution with expectation value s,
given an observed (i.e. empirical) distribution pdf.

pdf is a list of tuples (ai,pi), i=1,...,N. It is assumed that 
that the ai are strictly ascending, a1<s<aN and p1>0, pN>0.

The theory behind this function can be found in the online 
document

http://hardy.uhasselt.be/Toga/computeLLR.pdf

(see Proposition 1.1).

"""
    epsilon=1e-9
    v,w=pdf[0][0],pdf[-1][0]
    l,u=-1/(w-s),1/(s-v)
    f=lambda x:sum([p*(a-s)/(1+x*(a-s)) for a,p in pdf])
    x,res=brentq(f,l+epsilon,u-epsilon,full_output=True)
    assert(res.converged)
    pdf_MLE=[(a,p/(1+x*(a-s))) for a,p in pdf]
    s_,var=stats(pdf_MLE) # for validation
    assert(abs(s-s_)<1e-6)
    return pdf_MLE

def LL(pdf1,pdf2):
    return sum([pdf1[i][1]*math.log(pdf2[i][1]) for i in range(0,len(pdf1))])

def LLR(pdf,s0,s1):
    """
This function computes the generalized log likelihood ratio (divided by N)
for s=s1 versus s=s0 where pdf is an empirical distribution and
s is the expectation value of the true distribution.
pdf is a list of pairs (value,probability).
"""
    return LL(pdf,MLE(pdf,s1))-LL(pdf,MLE(pdf,s0))

def stats(pdf):
    epsilon=1e-6
    for i in range(0,len(pdf)):
      assert(-epsilon<=pdf[i][1]<=1+epsilon)
    n=sum([prob for value,prob in pdf])
    assert(abs(n-1)<epsilon)
    s=sum([prob*value for value,prob in pdf])
    var=sum([prob*(value-s)**2 for value,prob in pdf])
    return s,var

def results_to_pdf(results):
  results=regularize(results)
  N=sum(results)
  l=len(results)
  return N,[(i/(l-1),results[i]/N) for i in range(0,l)]

def LLR_logistic(elo0,elo1,results):
    """
This function computes the generalized log-likelihood ratio for "results"
which should be a list of either length 3 or 5. If the length
is 3 then it should contain the frequencies of L,D,W. If the length
is 5 then it should contain the frequencies of the game pairs
LL,LD+DL,LW+DD+WL,DW+WD,WW.
elo0,elo1 are in logistic elo.
"""
    s0,s1=[L(elo) for elo in (elo0,elo1)]
    N,pdf=results_to_pdf(results)
    s,var=stats(pdf)
    # The well-known universal constant 0.583 is for normal increments.
    # For the trinomial distribution it should be 0.5.
    # For the pentanomial distribution there is also a formula.
    # In practice this appears to make no difference.
    overshoot=0.583*(s1-s0)/math.sqrt(var)
    return N*LLR(pdf,s0,s1),overshoot

if __name__ == "__main__":
  # unit tests
  print SPRT({'wins': 10, 'losses': 0, 'draws': 20}, 0, 0.05, 5, 0.05, 200)
  print SPRT({'wins': 10, 'losses': 1, 'draws': 20}, 0, 0.05, 5, 0.05, 200)
  print SPRT({'wins': 5019, 'losses': 5026, 'draws': 15699}, 0, 0.05, 5, 0.05, 200)
  print SPRT({'wins': 1450, 'losses': 1500, 'draws': 4000}, 0, 0.05, 6, 0.05, 200)
  print SPRT({'wins': 716, 'losses': 591, 'draws': 2163}, 0, 0.05, 6, 0.05, 200)
  print SPRT({'wins': 13543,'losses': 13624, 'draws': 34333}, -3, 0.05, 1, 0.05, 200)
  print SPRT({'wins': 13543,'losses': 13624, 'draws': 34333, 'pentanomial':[1187, 7410, 13475, 7378, 1164]}, -3, 0.05, 1, 0.05, 200)
  print SPRT({'wins': 65388,'losses': 65804, 'draws': 56553}, -3, 0.05, 1, 0.05, 200)
  print SPRT({'wins': 65388,'losses': 65804, 'draws': 56553, 'pentanomial':[10789, 19328, 33806, 19402, 10543]}, -3, 0.05, 1, 0.05, 200)
