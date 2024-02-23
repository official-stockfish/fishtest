from __future__ import division

import copy
import math

import scipy.optimize

"""
Probability distributions (generally having a name starting with
"pdf") are represented by a list of tuples (ai,pi), i=1,...,N.  It is
usually assumed that the ai are strictly ascending and p1>0, pN>0.
"""

"""
The results of a test are represented by a list of either length 3
or 5. If the length is 3 then it should contain the frequencies of
L,D,W. If the length is 5 then it should contain the frequencies of
the game pairs LL,LD+DL,LW+DD+WL,DW+WD,WW.
"""

nelo_divided_by_nt = 800 / math.log(10)  # 347.43558552260146


def secular(pdf):
    """
    Solves the secular equation sum_i pi*ai/(1+x*ai)=0.
    """
    epsilon = 1e-9
    v, w = pdf[0][0], pdf[-1][0]
    values = [ai for ai, pi in pdf]
    v = min(values)
    w = max(values)
    assert v * w < 0
    l = -1 / w
    u = -1 / v

    def f(x):
        return sum([pi * ai / (1 + x * ai) for ai, pi in pdf])

    x, res = scipy.optimize.brentq(
        f, l + epsilon, u - epsilon, full_output=True, disp=False
    )
    assert res.converged
    return x


def uniform(pdf):
    n = len(pdf)
    return [(ai, 1 / n) for ai, pi in pdf]


def MLE_expected(pdfhat, s):
    """
    This function computes the maximum likelood estimate for
    a discrete distribution with expectation value s,
    given an observed (i.e. empirical) distribution pdfhat.

    The theory behind this function can be found in the online
    document

    http://hardy.uhasselt.be/Fishtest/support_MLE_multinomial.pdf

    (see Proposition 1.1)."""
    pdf1 = [(ai - s, pi) for ai, pi in pdfhat]
    x = secular(pdf1)
    pdf_MLE = [(ai, pi / (1 + x * (ai - s))) for ai, pi in pdfhat]
    s_, _ = stats(pdf_MLE)  # for validation
    assert abs(s - s_) < 1e-6
    return pdf_MLE


def MLE_t_value(pdfhat, ref, s):
    """
    This function computes the maximum likelood estimate for
    a discrete distribution with t-value ((mu-ref)/sigma),
    given an observed (i.e. empirical) distribution pdfhat.

    The theory behind this function can be found in the online
    document

    https://hardy.uhasselt.be/Fishtest/normalized_elo_practical.pdf

    (see Section 4.1)."""
    N = len(pdfhat)
    pdf_MLE = uniform(pdfhat)
    for i in range(10):
        pdf_ = pdf_MLE
        mu, var = stats(pdf_MLE)
        sigma = var ** (1 / 2)
        pdf1 = [
            (ai - ref - s * sigma * (1 + ((mu - ai) / sigma) ** 2) / 2, pi)
            for ai, pi in pdfhat
        ]
        x = secular(pdf1)
        pdf_MLE = [
            (pdfhat[i][0], pdfhat[i][1] / (1 + x * pdf1[i][0])) for i in range(N)
        ]
        if max([abs(pdf_[i][1] - pdf_MLE[i][1]) for i in range(N)]) < 1e-9:
            break
    mu, var = stats(pdf_MLE)  # for validation
    assert abs(s - (mu - ref) / var**0.5) < 1e-5
    return pdf_MLE


def stats(pdf):
    epsilon = 1e-6
    for i in range(0, len(pdf)):
        assert -epsilon <= pdf[i][1] <= 1 + epsilon
    n = sum([prob for value, prob in pdf])
    assert abs(n - 1) < epsilon
    s = sum([prob * value for value, prob in pdf])
    var = sum([prob * (value - s) ** 2 for value, prob in pdf])
    return s, var


def stats_ex(pdf):
    """
    Computes expectation value, variance, skewness and excess
    kurtosis for a discrete distribution."""
    s, var = stats(pdf)
    m3 = sum([prob * (value - s) ** 3 for value, prob in pdf])
    m4 = sum([prob * (value - s) ** 4 for value, prob in pdf])
    skewness = m3 / var**1.5
    exkurt = m4 / var**2 - 3
    return s, var, skewness, exkurt


def LLRjumps(pdf, s0, s1, ref=None, statistic="expectation"):
    if statistic == "expectation":
        pdf0, pdf1 = [MLE_expected(pdf, s) for s in (s0, s1)]
    elif statistic == "t_value":
        pdf0, pdf1 = [MLE_t_value(pdf, ref, s) for s in (s0, s1)]
    else:
        assert False
    return [
        (math.log(pdf1[i][1]) - math.log(pdf0[i][1]), pdf[i][1])
        for i in range(0, len(pdf))
    ]


def LLR(pdf, s0, s1, ref=None, statistic="expectation"):
    """
    This function computes the generalized log likelihood ratio
    (divided by N) for s=s1 versus s=s0 where pdf is an empirical
    distribution and s is score of the true distribution.
    """
    return stats(LLRjumps(pdf, s0, s1, ref=ref, statistic=statistic))[0]


def LLR_alt(pdf, s0, s1):
    """
    This function computes the approximate generalized log likelihood
    ratio (divided by N) for s=s1 versus s=s0 where pdf is an empirical
    distribution and s is the expectation value of the true
    distribution. See

    http://hardy.uhasselt.be/Fishtest/support_MLE_multinomial.pdf
    """
    r0, r1 = [sum([prob * (value - s) ** 2 for value, prob in pdf]) for s in (s0, s1)]
    return 1 / 2 * math.log(r0 / r1)


def LLR_alt2(pdf, s0, s1):
    """
    This function computes the approximate generalized log likelihood
    ratio (divided by N) for s=s1 versus s=s0 where pdf is an empirical
    distribution and s is the expectation value of the true
    distribution. See

    http://hardy.uhasselt.be/Fishtest/GSPRT_approximation.pdf
    """
    s, var = stats(pdf)
    return (s1 - s0) * (2 * s - s0 - s1) / var / 2.0


def LLR_drift_variance(pdf, s0, s1, s=None):
    """
    Computes the drift and variance of the LLR for a test s=s0 against
    s=s0 when the empirical distribution is pdf, but the true value of s
    is as given by the argument s. If s is not given then it is assumed
    that pdf is the true distribution."""
    if s is not None:
        pdf = MLE_expected(pdf, s)
    jumps = LLRjumps(pdf, s0, s1)
    return stats(jumps)


def LLR_drift_variance_alt2(pdf, s0, s1, s=None):
    """
    Computes the approximated drift and variance of the LLR for a test
    s=s0 against s=s0 approximated by a Brownian motion, when the
    empirical distribution is pdf, but the true value of s is as given by
    the argument s. If s is not given the it is assumed that pdf is the
    true distribution. See

    http://hardy.uhasselt.be/Fishtest/GSPRT_approximation.pdf
    """
    s_, v_ = stats(pdf)
    # replace v_ by its MLE if requested
    s, v = (s_, v_) if s is None else (s, v_ + (s - s_) ** 2)
    mu = (s - (s0 + s1) / 2) * (s1 - s0) / v
    var = (s1 - s0) ** 2 / v
    return mu, var


def L_(x):
    return 1 / (1 + 10 ** (-x / 400))


def regularize(l):
    """
    If necessary mix in a small prior for regularization."""
    epsilon = 1e-3
    l = copy.copy(l)
    for i in range(0, len(l)):
        if l[i] == 0:
            l[i] = epsilon
    return l


def results_to_pdf(results):
    results = regularize(results)
    N = sum(results)
    l = len(results)
    return N, [(i / (l - 1), results[i] / N) for i in range(0, l)]


def LLR_logistic(elo0, elo1, results):
    """
    This function computes the generalized log-likelihood ratio for "results"
    using the statistic "expectation". elo0,elo1 are in logistic elo."""
    s0, s1 = [L_(elo) for elo in (elo0, elo1)]
    N, pdf = results_to_pdf(results)
    return N * LLR(pdf, s0, s1, statistic="expectation")


def LLR_normalized_alt(nelo0, nelo1, results):
    """
    This function computes the generalized log-likelihood ratio for "results"
    using the approximation in

    https://hardy.uhasselt.be/Fishtest/normalized_elo_practical.pdf

    (see Section 4.2).

    nelo0,nelo1 are in normalized Elo."""
    count, pdf = results_to_pdf(results)
    mu, var = stats(pdf)
    if len(results) == 5:
        sigma_pg = (2 * var) ** 0.5
        games = 2 * count
    elif len(results) == 3:
        sigma_pg = var**0.5
        games = count
    else:
        assert False
    nt0, nt1 = [nelo / nelo_divided_by_nt for nelo in (nelo0, nelo1)]
    nt = (mu - 0.5) / sigma_pg

    return (games / 2.0) * math.log(
        (1 + (nt - nt0) * (nt - nt0)) / (1 + (nt - nt1) * (nt - nt1))
    )


def LLR_normalized(nelo0, nelo1, results):
    """
    This function computes the generalized log-likelihood ratio for "results"
    using the statistic "t_value". nelo0,nelo1 are in normalized elo."""
    nt0, nt1 = [nelo / nelo_divided_by_nt for nelo in (nelo0, nelo1)]
    sqrt2 = 2**0.5
    t0, t1 = (
        (nt0, nt1)
        if len(results) == 3
        else (nt0 * sqrt2, nt1 * sqrt2) if len(results) == 5 else None
    )
    N, pdf = results_to_pdf(results)
    return N * LLR(pdf, t0, t1, ref=1 / 2, statistic="t_value")
