from __future__ import division

import argparse
import math

import scipy.optimize

from fishtest.stats import LLRcalc
from fishtest.stats.brownian import Brownian


class sprt:
    # Elo axis clamp for the confidence-bound search. outcome_prob maps Elo
    # through the logistic score law, so the search runs in logistic Elo over
    # [-CB_CLAMP, CB_CLAMP] regardless of the elo_model.
    CB_CLAMP = 1000.0
    # Grid step (Elo) for the coarse scan. The descending region of outcome_prob
    # is tens to hundreds of Elo wide for real pentanomial data, so a 10 Elo grid
    # cannot skip over the leftmost crossing; brentq then refines each bracket.
    CB_STEP = 10.0

    def __init__(self, alpha=0.05, beta=0.05, elo0=0, elo1=5, elo_model="logistic"):
        assert elo_model in ("logistic", "normalized")
        self.elo_model = elo_model
        self.a = math.log(beta / (1 - alpha))
        self.b = math.log((1 - beta) / alpha)
        self.elo0 = elo0
        self.elo1 = elo1
        self.clamped = False
        self.LLR_drift_variance = LLRcalc.LLR_drift_variance_alt2

    def elo_to_score(self, elo):
        """
        "elo" is expressed in our current elo_model."""
        if self.elo_model == "normalized":
            nt = elo / LLRcalc.nelo_divided_by_nt
            return nt * self.sigma_pg + 0.5
        else:
            return LLRcalc.L_(elo)

    def lelo_to_elo(self, lelo):
        """
        For external use. "elo" is expressed in our current elo_model.
        "lelo" is logistic."""
        if self.elo_model == "logistic":
            return lelo
        score = LLRcalc.L_(lelo)
        nt = (score - 0.5) / self.sigma_pg
        return nt * LLRcalc.nelo_divided_by_nt

    def set_state(self, results):
        N, self.pdf = LLRcalc.results_to_pdf(results)
        if self.elo_model == "normalized":
            mu, var = LLRcalc.stats(self.pdf)  # code duplication with LLRcalc
            if len(results) == 5:
                self.sigma_pg = (2 * var) ** 0.5
            elif len(results) == 3:
                self.sigma_pg = var**0.5
            else:
                assert False
        self.s0, self.s1 = [self.elo_to_score(elo) for elo in (self.elo0, self.elo1)]

        mu_LLR, var_LLR = self.LLR_drift_variance(self.pdf, self.s0, self.s1, None)

        # llr estimate
        self.llr = N * mu_LLR
        self.T = N

        # now normalize llr (if llr is not legal then the implications
        # of this are unclear)
        slope = self.llr / N
        if self.llr > 1.03 * self.b or self.llr < 1.03 * self.a:
            self.clamped = True
        if self.llr < self.a:
            self.T = self.a / slope
            self.llr = self.a
        elif self.llr > self.b:
            self.T = self.b / slope
            self.llr = self.b

    def outcome_prob(self, elo):
        """
        The probability of a test with the given elo with worse outcome
        (faster fail, slower pass or a pass changed into a fail)."""
        s = LLRcalc.L_(elo)
        mu_LLR, var_LLR = self.LLR_drift_variance(self.pdf, self.s0, self.s1, s)
        sigma_LLR = math.sqrt(var_LLR)
        return Brownian(a=self.a, b=self.b, mu=mu_LLR, sigma=sigma_LLR).outcome_cdf(
            T=self.T, y=self.llr
        )

    def _confidence_bounds(self, ps):
        """
        For each probability p in `ps`, return the maximal Elo such that the
        observed outcome of the test has probability less than p, i.e. the Elo
        where outcome_prob(elo) == 1 - p. The results align with `ps`.

        The root is sought on the logistic Elo axis that outcome_prob uses
        (s = L_(elo)), over the fixed window [-CB_CLAMP, CB_CLAMP]. The search
        does not depend on the elo_model or on the units of the SPRT bounds, so
        every caller and every elo_model agrees on the result.

        outcome_prob is monotone decreasing in Elo only while the small-Elo GSPRT
        approximation holds. Once the observed Elo lies far outside [elo0, elo1]
        the approximation breaks down: outcome_prob dips to a minimum and rises
        again toward the clamp. The confidence bound is the leftmost (descending)
        crossing; the spurious rising branch is ignored. A level that is never
        reached inside the window is pinned to the clamp and sets self.clamped.
        """
        lo, hi = -self.CB_CLAMP, self.CB_CLAMP
        steps = round((hi - lo) / self.CB_STEP)
        # outcome_prob level targeted by each requested p, and the bound for it
        levels = [1 - p for p in ps]
        bounds = [None] * len(ps)
        op_prev = self.outcome_prob(lo)
        pending = []
        for index, level in enumerate(levels):
            if op_prev <= level:
                # the crossing is at or below the low clamp
                bounds[index] = lo
                self.clamped = True
            else:
                pending.append(index)
        x_prev = lo
        for step in range(1, steps + 1):
            if not pending:
                break
            x = lo + (hi - lo) * step / steps
            op = self.outcome_prob(x)
            still_pending = []
            for index in pending:
                level = levels[index]
                # leftmost descending crossing of `level` in (x_prev, x]
                if op_prev >= level > op:
                    bounds[index] = scipy.optimize.brentq(
                        lambda elo, level=level: self.outcome_prob(elo) - level,
                        x_prev,
                        x,
                        disp=False,
                    )
                else:
                    still_pending.append(index)
            pending = still_pending
            x_prev, op_prev = x, op
        for index in pending:
            # never reached inside the window: the bound is unbounded above
            bounds[index] = hi
            self.clamped = True
        return bounds

    def lower_cb(self, p):
        """
        Maximal Elo value such that the observed outcome of the test has
        probability less than p."""
        (bound,) = self._confidence_bounds([p])
        return bound

    def analytics(self, p=0.05):
        elo, ci_lower, ci_upper = self._confidence_bounds([0.5, p / 2, 1 - p / 2])
        ret = {}
        ret["clamped"] = self.clamped
        ret["a"] = self.a
        ret["b"] = self.b
        ret["elo"] = elo
        ret["ci"] = [ci_lower, ci_upper]
        ret["LOS"] = self.outcome_prob(0)
        ret["LLR"] = self.llr
        return ret


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--alpha", help="probability of a false positive", type=float, default=0.05
    )
    parser.add_argument(
        "--beta", help="probability of a false negative", type=float, default=0.05
    )
    parser.add_argument(
        "--elo0", help="H0 (expressed in LogisticElo)", type=float, default=0.0
    )
    parser.add_argument(
        "--elo1", help="H1 (expressed in LogisticElo)", type=float, default=5.0
    )
    parser.add_argument("--level", help="confidence level", type=float, default=0.95)
    parser.add_argument(
        "--elo-model",
        help="logistic or normalized",
        choices=["logistic", "normalized"],
        default="logistic",
    )
    parser.add_argument(
        "--results",
        help="trinomial of pentanomial frequencies, low to high",
        nargs="*",
        type=int,
        required=True,
    )
    args = parser.parse_args()
    results = args.results
    if len(results) != 3 and len(results) != 5:
        parser.error("argument --results: expected 3 or 5 arguments")
    alpha = args.alpha
    beta = args.beta
    elo0 = args.elo0
    elo1 = args.elo1
    elo_model = args.elo_model
    p = 1 - args.level
    s = sprt(alpha=alpha, beta=beta, elo0=elo0, elo1=elo1, elo_model=elo_model)
    s.set_state(results)
    a = s.analytics(p)
    print("Design parameters")
    print("=================")
    print("False positives             :  {:4.2%}".format(alpha))
    print("False negatives             :  {:4.2%}".format(beta))
    print("[Elo0,Elo1]                 :  [{:.2f},{:.2f}]".format(elo0, elo1))
    print("Confidence level            :  {:4.2%}".format(1 - p))
    print("Elo model                   :  {}".format(elo_model))
    print("Estimates")
    print("=========")
    print("Elo                         :  {:.2f}".format(a["elo"]))
    print(
        "Confidence interval         :  [{:.2f},{:.2f}] ({:4.2%})".format(
            a["ci"][0], a["ci"][1], 1 - p
        )
    )
    print("LOS                         :  {:4.2%}".format(a["LOS"]))
    print("Context")
    print("=======")
    print(
        "LLR [u,l]                   :  {:.2f} {} [{:.2f},{:.2f}]".format(
            a["LLR"], "(clamped)" if a["clamped"] else "", a["a"], a["b"]
        )
    )
