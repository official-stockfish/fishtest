from __future__ import division

import math,copy
import argparse

from .brownian import Brownian
from .brentq import brentq
from . import LLRcalc

class sprt:
    def __init__(self,alpha=0.05,beta=0.05,elo0=0,elo1=5):
        self.a=math.log(beta/(1-alpha))
        self.b=math.log((1-beta)/alpha)
        self.elo0=elo0
        self.elo1=elo1
        self.s0=LLRcalc.L_(elo0)
        self.s1=LLRcalc.L_(elo1)
        self.clamped=False
        self.LLR_drift_variance=LLRcalc.LLR_drift_variance_alt2

    def set_state(self,results):
        N,self.pdf=LLRcalc.results_to_pdf(results)
        mu_LLR,var_LLR=self.LLR_drift_variance(self.pdf,self.s0,self.s1,None)

        # llr estimate
        self.llr=N*mu_LLR
        self.T=N

        # now normalize llr (if llr is not legal then the implications
        # of this are unclear)
        slope=self.llr/N
        if self.llr>1.03*self.b or self.llr<1.03*self.a:
            self.clamped=True
        if self.llr<self.a:
            self.T=self.a/slope
            self.llr=self.a
        elif self.llr>self.b:
            self.T=self.b/slope
            self.llr=self.b

    def outcome_prob(self,elo):
        """
The probability of a test with the given elo with worse outcome
(faster fail, slower pass or a pass changed into a fail).
"""
        s=LLRcalc.L_(elo)
        mu_LLR,var_LLR=self.LLR_drift_variance(self.pdf,self.s0,self.s1,s)
        sigma_LLR=math.sqrt(var_LLR)
        return Brownian(a=self.a,b=self.b,mu=mu_LLR,sigma=sigma_LLR).outcome_cdf(T=self.T,y=self.llr)

    def lower_cb(self,p):
        """
Maximal elo value such that the observed outcome of the test has probability
less than p.
"""
        avg_elo=(self.elo0+self.elo1)/2
        delta=self.elo1-self.elo0
        N=30
# Various error conditions must be handled better here!
        while True:
            elo0=max(avg_elo-N*delta,-1000)
            elo1=min(avg_elo+N*delta,1000)
            sol=brentq(lambda elo:self.outcome_prob(elo)-(1-p),elo0,elo1)
            if sol['msg']=='no bracket':
                if elo0>-1000 or elo1<1000:
                    N*=2
                    continue
                else:
                    if self.outcome_prob(elo0)-(1-p)>0:
                        return elo1
                    else:
                        return elo0
            assert(sol['converged'])
            break
        return sol['x0']

    def analytics(self,p=0.05):
        ret={}
        ret['clamped']=self.clamped
        ret['a']=self.a
        ret['b']=self.b
        ret['elo']=self.lower_cb(0.5)
        ret['ci']=[self.lower_cb(p/2),self.lower_cb(1-p/2)]
        ret['LOS']=self.outcome_prob(0)
        ret['LLR']=self.llr
        return ret
