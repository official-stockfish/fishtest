from __future__ import division
import math
import argparse
from brownian import Brownian
from brentq import brentq

BayesElo=0
LogisticElo=1

def scale(de):
    return (4*10**(-de/400))/(1+10**(-de/400))**2

def wdl(elo,de):
    w=1/(1+10**((-elo+de)/400))
    l=1/(1+10**((elo+de)/400))
    d=1-w-l
    return(w,d,l)

def draw_elo_calc(draw_ratio):
    return 400*(math.log(1/((1-draw_ratio)/2.0)-1)/math.log(10))

class sprt:
    def __init__(self,alpha=0.05,beta=0.05,elo0=0,elo1=5,mode=BayesElo):
        self.elo0_raw=elo0
        self.elo1_raw=elo1
        self.a=math.log(beta/(1-alpha))
        self.b=math.log((1-beta)/alpha)
        self.mode=mode

    def set_state(self,W=None,D=None,L=None):
        self.N=W+D+L
        self.dr=D/self.N
        self.de=draw_elo_calc(self.dr)
        if self.mode==LogisticElo:
            sf=scale(self.de)
            self.elo0=self.elo0_raw/sf
            self.elo1=self.elo1_raw/sf
        else:
            self.elo0=self.elo0_raw;
            self.elo1=self.elo1_raw;
        w0,d0,l0=wdl(self.elo0,self.de)
        w1,d1,l1=wdl(self.elo1,self.de)
        self.llr_win=math.log(w1/w0)
        self.llr_draw=math.log(d1/d0)
        self.llr_loss=math.log(l1/l0)
        self.llr=W*self.llr_win+D*self.llr_draw+L*self.llr_loss
        self.llr_raw=self.llr
# record if llr is outside legal range
        self.clamped=False
        if self.llr<self.a+self.llr_loss or self.llr>self.b+self.llr_win:
            self.clamped=True
# now normalize llr (if llr is not legal then the implications of this are unclear)
        slope=self.llr/self.N
        if self.llr<self.a:
            self.T=self.a/slope
            self.llr=self.a
        elif self.llr>self.b:
            self.T=self.b/slope
            self.llr=self.b
        else:
            self.T=self.N

    def outcome_prob(self,elo):
        """
The probability of a test with the given elo with worse outcome
(faster fail, slower pass or a pass changed into a fail).
"""
        w,d,l=wdl(elo,self.de)
        mu=w*self.llr_win+d*self.llr_draw+l*self.llr_loss
        mu2=w*self.llr_win**2+d*self.llr_draw**2+l*self.llr_loss**2
        sigma2=mu2-mu**2
        sigma=math.sqrt(sigma2)
        return Brownian(a=self.a,b=self.b,mu=mu,sigma=sigma).outcome_cdf(T=self.T,y=self.llr)

    def lower_cb(self,p):
        """
Maximal elo value such that the observed outcome of the test has probability
less than p.
"""
        avg_elo=self.elo0+self.elo1
        delta=self.elo1-self.elo0
        N=30
# Various error conditions must be handled better here!
        while True:
            Elo0=avg_elo-N*delta
            Elo1=avg_elo+N*delta
            sol=brentq(lambda elo:self.outcome_prob(elo)-(1-p),Elo0,Elo1)
            if sol['msg']=='no bracket':
                N*=2
                continue
            break
        return sol['x0']

    def analytics(self,p=0.05):
        ret={}
        ret['LLR']=self.llr_raw
        sf=scale(self.de)
        ret['elo0']=self.elo0*sf
        ret['elo1']=self.elo1*sf
        ret['elo']=self.lower_cb(0.5)*sf
        ret['ci']=[self.lower_cb(p/2)*sf,self.lower_cb(1-p/2)*sf]
        ret['LOS']=self.outcome_prob(0)
        ret['draw_elo']=self.de
        ret['draw_ratio']=self.dr
        ret['games']=self.N
        ret['clamped']=self.clamped
        ret['a']=self.a
        ret['b']=self.b
        return ret

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha",help="probability of a false positve",type=float,default=0.05)
    parser.add_argument("--beta" ,help="probability of a false negative",type=float,default=0.05) 
    parser.add_argument("--logistic", help="Express input in logistic elo",
                        action='store_true')
    parser.add_argument("--elo0", help="H0 (expressed in BayesElo)",type=float,default=0.0)
    parser.add_argument("--elo1", help="H1 (expressed in BayseElo)",type=float,default=5.0)
    parser.add_argument("--level",help="confidence level",type=float,default=0.95)
    parser.add_argument("-W", help="number of won games",type=int,required=True)
    parser.add_argument("-D", help="number of draw games",type=int,required=True)
    parser.add_argument("-L", help="nummer of lost games",type=int,required=True)
    args=parser.parse_args()
    W,D,L=args.W,args.D,args.L
    alpha=args.alpha
    beta=args.beta
    elo0=args.elo0
    elo1=args.elo1
    mode=LogisticElo if args.logistic else BayesElo
    p=1-args.level
    s=sprt(alpha=alpha,beta=beta,elo0=elo0,elo1=elo1,mode=mode)
    s.set_state(W,D,L)
    a=s.analytics(p)
    print "Design parameters"
    print "================="
    print "False positives             :  %4.2f%%" % (100*alpha,)
    print "False negatives             :  %4.2f%%" % (100*beta,) 
    print "[Elo0,Elo1]                 :  [%.2f,%.2f] %s"    % (elo0,elo1,"" if mode==LogisticElo else "(BayesElo)")
    print "Confidence level            :  %4.2f%%" % (100*(1-p),)
    print "Estimates"
    print "========="
    print "Elo                         :  %.2f"    % a['elo']
    print "Confidence interval         :  [%.2f,%.2f] (%4.2f%%)"  % (a['ci'][0],a['ci'][1],100*(1-p))
    print "LOS                         :  %4.2f%%" % (100*a['LOS'],)
    print "Context"
    print "======="
    print "Games                       :  %d" % (a['games'],)
    print "Draw ratio                  :  %4.2f%%"    % (100*a['draw_ratio'],)
    print "DrawElo                     :  %.2f (BayesElo)"    % a['draw_elo']
    print "LLR [u,l]                   :  %.2f %s [%.2f,%.2f]"       % (a['LLR'], '(clamped)' if a['clamped'] else '',a['a'],a['b'])
    print "[Elo0,Elo1]                 :  [%.2f,%.2f]"    % (a['elo0'],a['elo1'])
