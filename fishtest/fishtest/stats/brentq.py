#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# file pyroots/brent.py
#
#############################################################################
# Copyright (c) 2013 by Panagiotis Mavrogiorgos
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name(s) of the copyright holders nor the names of its
#   contributors may be used to endorse or promote products derived from this
#   software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AS IS AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL THE COPYRIGHT HOLDERS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#############################################################################
#
# @license: http://opensource.org/licenses/BSD-3-Clause
# @authors: see AUTHORS.txt


"""
Brent's algorithm for root finding.
"""

from __future__ import division
import sys

EPS = sys.float_info.epsilon

def nearly_equal(a, b, epsilon):
    if a == b:
        return True                         # shortcut. Handles infinities etc
    diff = abs(a - b)
    max_ab = max(abs(a), abs(b), 1)
    if max_ab >= diff or max_ab > 1:
        return diff <= epsilon              # absolute error
    else:
        return diff < epsilon * max_ab      # relative  error

class result(dict):
    def __init__(self, x0, fx0, iterations, func_evaluations, converged, msg=""):
        self['x0'] = x0
        self['fx0'] = fx0
        self['iterations'] = iterations
        self['func_calls'] = func_evaluations
        self['converged'] = converged
        self['msg'] = msg
        
def _extrapolate(fcur, fpre, fblk, dpre, dblk):
    return -fcur * (fblk * dblk - fpre * dpre) / (dblk * dpre * (fblk - fpre))

def brentq(f, xa, xb, xtol=EPS, epsilon=1e-6, max_iter=500):    
    # initialize counters
    i = 0
    fcalls = 0

    # rename variables in order to be consistent with scipy's code.
    xpre, xcur = xa, xb
    xblk, fblk, spre, scur = 0, 0, 0, 0

    #check that the bracket's interval is sufficiently big.
    if nearly_equal(xa, xb, xtol):
        return result(None, None, i, fcalls, False, "small bracket")

    # check lower bound
    fpre = f(xpre)             # First function call
    fcalls += 1
    if nearly_equal(0,fpre,epsilon):
        return result(xpre, fpre, i, fcalls, True, "lower bracket")

    # check upper bound
    fcur = f(xcur)             # Second function call
    fcalls += 1
    # self._debug(i, fcalls, xpre, xcur, fpre, fcur)
    if nearly_equal(0,fcur,epsilon):
        return result(xcur, fcur, i, fcalls, True, "upper bracket")

    # check if the root is bracketed.
    if fpre * fcur > 0.0:
        return result(None, None, i, fcalls, False, "no bracket")

    # start iterations
    for i in range(max_iter):
        if (fpre*fcur < 0):
            xblk = xpre
            fblk = fpre
            spre = scur = xcur - xpre

        if (abs(fblk) < abs(fcur)):
            xpre = xcur
            xcur = xblk
            xblk = xpre
            fpre = fcur
            fcur = fblk
            fblk = fpre

        # check bracket
        sbis = (xblk - xcur) / 2;
        if abs(sbis) < xtol:
            return result(xcur, fcur, i + 1, fcalls, False, "small bracket")

        # calculate short step
        if abs(spre) > xtol and abs(fcur) < abs(fpre):
            if xpre == xblk:
                # interpolate
                stry = -fcur * (xcur - xpre) / (fcur - fpre)
            else:
                # extrapolate
                dpre = (fpre - fcur) / (xpre - xcur)
                dblk = (fblk - fcur) / (xblk - xcur)
                stry = _extrapolate(fcur, fpre, fblk, dpre, dblk)

            # check short step
            if (2 * abs(stry) < min(abs(spre), 3 * abs(sbis) - xtol)):
                # good short step
                spre = scur
                scur = stry
            else:
                # bisect
                spre = sbis
                scur = sbis
        else:
            # bisect
            spre = sbis
            scur = sbis

        xpre = xcur;
        fpre = fcur;
        if (abs(scur) > xtol):
            xcur += scur
        else:
            xcur += xtol if (sbis > 0) else -xtol

        fcur = f(xcur)     # function evaluation
        fcalls += 1
        # self._debug(i + 1, fcalls, xpre, xcur, fpre, fcur)
        if nearly_equal(0,fcur,epsilon):
            return result(xcur, fcur, i, fcalls, True, "convergence")

    return result(xcur, fcur, i + 1, fcalls, False, "iterations")

if __name__=='__main__':
    import math
    f=lambda x:math.cos(x)-x
    print(brentq(f,0,math.pi/2))


    
