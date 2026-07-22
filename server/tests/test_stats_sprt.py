"""Confidence-bound inversion in `fishtest.stats.sprt` (issue 2571).

The live Elo page and the raw statistics page build the SPRT object in different
Elo models (normalized vs logistic) and used to disagree on the Elo estimate and
its confidence interval: one page showed a bare 1000, the other a finite value.
These tests pin the fixed behavior: the confidence bound is model-invariant, the
well-posed values are preserved, ordering holds, and a genuinely unbounded bound
pins to the clamp.
"""

import unittest

from fishtest.stats import LLRcalc
from fishtest.stats import stat_util as su
from fishtest.stats.sprt import sprt

# Reuse the estimator's own clamp constant instead of hard-coding it.
CLAMP = sprt.CB_CLAMP


def _pent_sigma(pentanomial):
    """Per-game stdev of the pentanomial, as the stats page computes it."""
    _, pdf = LLRcalc.results_to_pdf(pentanomial)
    _, var = LLRcalc.stats(pdf)
    return (2 * var) ** 0.5


def _analytics(pentanomial, model, elo0=0.0, elo1=2.0):
    """Reproduce how each page parameterizes the SPRT object.

    The live Elo page keeps the run's native normalized bounds; the stats page
    converts the bounds to logistic Elo through the pentanomial score. Both feed
    the same pentanomial, so a correct estimator must return the same analytics.
    """
    results = LLRcalc.regularize(pentanomial)
    if model == "normalized":
        sp = sprt(alpha=0.05, beta=0.05, elo0=elo0, elo1=elo1, elo_model="normalized")
    elif model == "logistic":
        sigma = _pent_sigma(pentanomial)
        ndbnt = LLRcalc.nelo_divided_by_nt
        lelo0 = su.elo(elo0 / ndbnt * sigma + 0.5)
        lelo1 = su.elo(elo1 / ndbnt * sigma + 0.5)
        sp = sprt(alpha=0.05, beta=0.05, elo0=lelo0, elo1=lelo1, elo_model="logistic")
    else:
        raise AssertionError(model)
    sp.set_state(results)
    return sp.analytics()


# The pentanomial reported in issue 2571: a strongly passing test whose observed
# Elo lies far outside the SPRT bounds, so outcome_prob is non-monotone.
ISSUE_PENT = [1, 20, 300, 900, 779]

# A spread of well-posed passing tests.
WELL_POSED = [
    [1, 60, 500, 1200, 500],
    [1, 60, 500, 1200, 600],
    [1, 60, 500, 1200, 700],
]


class ConfidenceBoundTest(unittest.TestCase):
    def test_model_invariance_on_divergence_case(self):
        # The exact case from issue 2571 must no longer depend on the Elo model:
        # both pages report the same, finite estimate instead of 1000 vs finite.
        norm = _analytics(ISSUE_PENT, "normalized")
        logi = _analytics(ISSUE_PENT, "logistic")
        self.assertAlmostEqual(norm["elo"], logi["elo"], places=6)
        self.assertAlmostEqual(norm["ci"][0], logi["ci"][0], places=6)
        self.assertAlmostEqual(norm["ci"][1], logi["ci"][1], places=6)
        # finite: not the raw clamp
        self.assertLess(norm["elo"], CLAMP)
        self.assertLess(norm["ci"][1], CLAMP)
        # pinned reference values (both models)
        self.assertAlmostEqual(norm["elo"], 245.4729, places=3)
        self.assertAlmostEqual(norm["ci"][0], 223.6370, places=3)
        self.assertAlmostEqual(norm["ci"][1], 289.7981, places=3)

    def test_well_posed_model_invariance(self):
        for pent in WELL_POSED:
            with self.subTest(pent=pent):
                norm = _analytics(pent, "normalized")
                logi = _analytics(pent, "logistic")
                self.assertAlmostEqual(norm["elo"], logi["elo"], places=6)
                self.assertAlmostEqual(norm["ci"][0], logi["ci"][0], places=6)
                self.assertAlmostEqual(norm["ci"][1], logi["ci"][1], places=6)

    def test_well_posed_reference_values(self):
        # Regression guard: pin the estimator output on a stable well-posed case.
        a = _analytics([1, 60, 500, 1200, 600], "normalized")
        self.assertAlmostEqual(a["elo"], 188.3595, places=3)
        self.assertAlmostEqual(a["ci"][0], 170.7252, places=3)
        self.assertAlmostEqual(a["ci"][1], 214.8484, places=3)

    def test_confidence_interval_is_ordered(self):
        for pent in [ISSUE_PENT, *WELL_POSED]:
            for model in ("normalized", "logistic"):
                with self.subTest(pent=pent, model=model):
                    a = _analytics(pent, model)
                    self.assertLessEqual(a["ci"][0], a["elo"])
                    self.assertLessEqual(a["elo"], a["ci"][1])

    def test_unbounded_bound_pins_to_clamp(self):
        # An off-scale test: outcome_prob never reaches the upper-CI level inside
        # the window, so the upper bound pins to the clamp and clamped is set.
        a = _analytics([0, 0, 1, 5, 994], "normalized")
        self.assertEqual(a["ci"][1], CLAMP)
        self.assertTrue(a["clamped"])

    def test_lower_cb_matches_analytics(self):
        # The public single-target wrapper agrees with the shared-scan analytics.
        sp = sprt(alpha=0.05, beta=0.05, elo0=0.0, elo1=2.0, elo_model="normalized")
        sp.set_state(LLRcalc.regularize(ISSUE_PENT))
        a = sp.analytics()
        self.assertAlmostEqual(sp.lower_cb(0.5), a["elo"], places=6)
        self.assertAlmostEqual(sp.lower_cb(0.025), a["ci"][0], places=6)
        self.assertAlmostEqual(sp.lower_cb(0.975), a["ci"][1], places=6)


if __name__ == "__main__":
    unittest.main()
