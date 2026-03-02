"use strict";

// Live Elo gauge rendering for htmx-updated data on /tests/live_elo/{id}.
// Baseline dynamic follows upstream/master: every gauge uses two draws
// (start value then target value). Additional behavior:
// - open page: animate all gauges from middle,
// - any tab/page activation: replay gauges from middle (all statuses),
// - if |delta LLR| > 0.05: animate all gauges from middle,
// - if SPRT state is accepted/rejected: animate all gauges from middle,
// - otherwise: animate from previous value to new value.

(async () => {
  await Promise.all([
    DOMContentLoaded(),
    google.charts.load("current", { packages: ["gauge"] }),
  ]);

  const losChart = new google.visualization.Gauge(
    document.getElementById("LOS_chart_div"),
  );
  const llrChart = new google.visualization.Gauge(
    document.getElementById("LLR_chart_div"),
  );
  const eloChart = new google.visualization.Gauge(
    document.getElementById("ELO_chart_div"),
  );

  const LLR_FALLBACK_A = -2.94;
  const LLR_FALLBACK_B = 2.94;
  const LLR_MIDDLE_TRIGGER_DELTA = 0.05;
  const ELO_INITIAL_BOUND = 1;
  const ELO_MIN_BOUND = 0.25;
  const ELO_MINOR_TICKS = 4;
  const ELO_MAJOR_TICK_COUNT = 5;
  const ANIMATION_START_DELAY_MS = 110;
  const ANIMATION_DURATION_MS = 950;

  let animationToken = 0;
  let animationTimers = [];

  let hasDrawnOnce = false;
  let lastSample = {
    llr: 0,
    a: LLR_FALLBACK_A,
    b: LLR_FALLBACK_B,
    los: 50,
    elo: 0,
    ciLower: 0,
    ciUpper: 0,
    sprtState: "",
  };

  function finiteOr(value, fallback) {
    return Number.isFinite(value) ? value : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function rounded(value, decimals) {
    const factor = 10 ** decimals;
    return Math.round(value * factor) / factor;
  }

  function parseSprtState(raw) {
    return (raw || "").trim().toLowerCase();
  }

  function isTerminalSprtState(state) {
    return state === "accepted" || state === "rejected";
  }

  function parseGaugeData(el) {
    if (!el) {
      return null;
    }

    const d = el.dataset;
    let a = finiteOr(parseFloat(d.a), LLR_FALLBACK_A);
    let b = finiteOr(parseFloat(d.b), LLR_FALLBACK_B);
    if (a >= b) {
      a = LLR_FALLBACK_A;
      b = LLR_FALLBACK_B;
    }

    let ciLower = finiteOr(parseFloat(d.ciLower), lastSample.ciLower);
    let ciUpper = finiteOr(parseFloat(d.ciUpper), lastSample.ciUpper);
    if (ciLower > ciUpper) {
      [ciLower, ciUpper] = [ciUpper, ciLower];
    }

    return {
      llr: rounded(finiteOr(parseFloat(d.llr), lastSample.llr), 2),
      a: rounded(a, 2),
      b: rounded(b, 2),
      los: rounded(
        clamp(finiteOr(parseFloat(d.los), lastSample.los), 0, 100),
        1,
      ),
      elo: rounded(finiteOr(parseFloat(d.elo), lastSample.elo), 2),
      ciLower: rounded(ciLower, 2),
      ciUpper: rounded(ciUpper, 2),
      sprtState: parseSprtState(d.sprtState),
    };
  }

  function selectPowerOfTwoBound(requiredAbs, minBound) {
    const clampedRequired = Math.max(requiredAbs, minBound);
    const exponent = Math.ceil(Math.log2(clampedRequired));
    return 2 ** exponent;
  }

  function buildEloScale(sample, isInitialDraw) {
    // Keep the gauge symmetric around zero and pick the smallest
    // power-of-two bound that contains CI endpoints and the arrow value.
    const requiredAbs = Math.max(
      Math.abs(sample.elo),
      Math.abs(sample.ciLower),
      Math.abs(sample.ciUpper),
    );
    const minBound = isInitialDraw ? ELO_INITIAL_BOUND : ELO_MIN_BOUND;
    const bound = selectPowerOfTwoBound(requiredAbs, minBound);
    return {
      min: -bound,
      max: bound,
      center: 0,
      minorTicks: ELO_MINOR_TICKS,
    };
  }

  function eloMajorTicks(scale) {
    // Keep a stable major tick count; label only the two ends.
    const ticks = new Array(ELO_MAJOR_TICK_COUNT).fill("");
    ticks[0] = String(scale.min);
    ticks[ELO_MAJOR_TICK_COUNT - 1] = String(scale.max);
    return ticks;
  }

  function gaugeData(label, value) {
    return google.visualization.arrayToDataTable([
      ["Label", "Value"],
      [label, value],
    ]);
  }

  function animateGaugeTo(chart, data, options, targetValue, token) {
    const duration = ANIMATION_DURATION_MS;
    const animatedOptions = {
      ...options,
      animation: {
        duration,
        easing: "out",
      },
    };

    chart.draw(data, animatedOptions);

    const timer = setTimeout(() => {
      if (token !== animationToken) {
        return;
      }
      data.setValue(0, 1, targetValue);
      chart.draw(data, animatedOptions);
    }, ANIMATION_START_DELAY_MS);
    animationTimers.push(timer);
  }

  function resetAnimationCycle() {
    animationToken += 1;
    for (const timer of animationTimers) {
      clearTimeout(timer);
    }
    animationTimers = [];
  }

  function shouldAnimateFromMiddle(sample) {
    if (sample.forceMiddleAnimation) {
      return true;
    }

    if (!hasDrawnOnce) {
      return true;
    }

    if (Math.abs(sample.llr - lastSample.llr) > LLR_MIDDLE_TRIGGER_DELTA) {
      return true;
    }

    return isTerminalSprtState(sample.sprtState);
  }

  function drawGauges(sample) {
    resetAnimationCycle();
    const token = animationToken;

    const fromMiddle = shouldAnimateFromMiddle(sample);
    const isFirstDraw = !hasDrawnOnce;

    const losStart = fromMiddle ? 50 : lastSample.los;
    const losOpts = {
      width: 500,
      height: 150,
      greenFrom: 95,
      greenTo: 100,
      yellowFrom: 5,
      yellowTo: 95,
      redFrom: 0,
      redTo: 5,
      minorTicks: 5,
    };
    const losData = gaugeData("LOS", losStart);
    animateGaugeTo(losChart, losData, losOpts, sample.los, token);

    const llrMiddle = (sample.a + sample.b) / 2;
    const llrStart = fromMiddle ? llrMiddle : lastSample.llr;
    const llrOpts = {
      width: 500,
      height: 150,
      greenFrom: sample.b,
      greenTo: sample.b * 1.04,
      redFrom: sample.a * 1.04,
      redTo: sample.a,
      yellowFrom: sample.a,
      yellowTo: sample.b,
      max: sample.b,
      min: sample.a,
      minorTicks: 3,
    };
    const llrData = gaugeData("LLR", llrStart);
    animateGaugeTo(llrChart, llrData, llrOpts, sample.llr, token);

    const eloScale = buildEloScale(sample, isFirstDraw);
    const eloStart = fromMiddle ? eloScale.center : lastSample.elo;
    const eloOpts = {
      width: 500,
      height: 150,
      min: eloScale.min,
      max: eloScale.max,
      minorTicks: eloScale.minorTicks,
      majorTicks: eloMajorTicks(eloScale),
    };
    // Keep upstream/master color semantics with dynamic scale.
    if (sample.ciLower < 0 && sample.ciUpper > 0) {
      eloOpts.redFrom = sample.ciLower;
      eloOpts.redTo = 0;
      eloOpts.yellowFrom = 0;
      eloOpts.yellowTo = 0;
      eloOpts.greenFrom = 0;
      eloOpts.greenTo = sample.ciUpper;
    } else if (sample.ciLower >= 0) {
      eloOpts.redFrom = sample.ciLower;
      eloOpts.redTo = sample.ciLower;
      eloOpts.yellowFrom = sample.ciLower;
      eloOpts.yellowTo = sample.ciLower;
      eloOpts.greenFrom = sample.ciLower;
      eloOpts.greenTo = sample.ciUpper;
    } else if (sample.ciUpper <= 0) {
      eloOpts.redFrom = sample.ciLower;
      eloOpts.redTo = sample.ciUpper;
      eloOpts.yellowFrom = sample.ciUpper;
      eloOpts.yellowTo = sample.ciUpper;
      eloOpts.greenFrom = sample.ciUpper;
      eloOpts.greenTo = sample.ciUpper;
    }
    const eloData = gaugeData("Elo", eloStart);
    animateGaugeTo(eloChart, eloData, eloOpts, sample.elo, token);

    hasDrawnOnce = true;
    lastSample = sample;
  }

  // Coalesce fast consecutive swaps into one draw cycle.
  let pendingSwap = false;
  let latestGaugeData = null;

  function scheduleGaugeUpdate(el) {
    latestGaugeData = el;
    if (pendingSwap) {
      return;
    }
    pendingSwap = true;
    requestAnimationFrame(() => {
      pendingSwap = false;
      const sample = parseGaugeData(latestGaugeData);
      if (sample) {
        drawGauges(sample);
        consumeActivationReplay();
      }
    });
  }

  // Initial draw from server-rendered data attributes.
  scheduleGaugeUpdate(document.getElementById("gauge-data"));

  function replayCurrentSampleFromMiddle() {
    if (!hasDrawnOnce || document.visibilityState !== "visible") {
      return false;
    }
    drawGauges({
      ...lastSample,
      forceMiddleAnimation: true,
    });
    return true;
  }

  let replayOnNextActivation = document.visibilityState !== "visible";

  function consumeActivationReplay() {
    if (!replayOnNextActivation || document.visibilityState !== "visible") {
      return;
    }
    if (replayCurrentSampleFromMiddle()) {
      replayOnNextActivation = false;
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      replayOnNextActivation = true;
      return;
    }

    consumeActivationReplay();
  });

  window.addEventListener("focus", () => {
    consumeActivationReplay();
  });

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      replayOnNextActivation = true;
      consumeActivationReplay();
    }
  });

  // Update on each htmx OOB swap (innerHTML of #live-elo-data).
  document.body.addEventListener("htmx:oobAfterSwap", (e) => {
    if (e?.detail?.target?.id === "live-elo-data") {
      scheduleGaugeUpdate(document.getElementById("gauge-data"));
    }
  });
})();
