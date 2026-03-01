"use strict";

// Google Charts gauge rendering for the live ELO page.
// Data is delivered via htmx OOB swap on #live-elo-data with data-* attrs.
// Gauges are initialized on page load from the server-rendered data attributes,
// then updated on each htmx:afterSwap event.

(async () => {
  await Promise.all([
    DOMContentLoaded(),
    google.charts.load("current", { packages: ["gauge"] }),
  ]);

  const LOS_chart = new google.visualization.Gauge(
    document.getElementById("LOS_chart_div"),
  );
  const LLR_chart = new google.visualization.Gauge(
    document.getElementById("LLR_chart_div"),
  );
  const ELO_chart = new google.visualization.Gauge(
    document.getElementById("ELO_chart_div"),
  );

  // Match legacy clearGauges() baseline: LOS 50%, LLR 0, ELO 0.
  let lastLOS = 50;
  let lastLLR = 0;
  let lastElo = 0;
  let hasDrawnOnce = false;
  let animationToken = 0;
  let animationTimers = [];

  const ANIMATION_START_DELAY_MS = 110;
  const ANIMATION_DURATION_FIRST_MS = 950;
  const ANIMATION_DURATION_NEXT_MS = 700;

  const LLR_FALLBACK_A = -2.94;
  const LLR_FALLBACK_B = 2.94;
  const ELO_MIN = -4;
  const ELO_MAX = 4;

  function finiteOr(value, fallback) {
    return Number.isFinite(value) ? value : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function normalizeGauges(sample) {
    let a = finiteOr(sample.a, LLR_FALLBACK_A);
    let b = finiteOr(sample.b, LLR_FALLBACK_B);
    if (a >= b) {
      a = LLR_FALLBACK_A;
      b = LLR_FALLBACK_B;
    }

    const llr = clamp(finiteOr(sample.llr, lastLLR), a, b);
    const los = clamp(finiteOr(sample.los, lastLOS), 0, 100);
    const elo = clamp(finiteOr(sample.elo, lastElo), ELO_MIN, ELO_MAX);

    let ciLower = finiteOr(sample.ciLower, 0);
    let ciUpper = finiteOr(sample.ciUpper, 0);
    if (ciLower > ciUpper) {
      [ciLower, ciUpper] = [ciUpper, ciLower];
    }
    ciLower = clamp(ciLower, ELO_MIN, ELO_MAX);
    ciUpper = clamp(ciUpper, ELO_MIN, ELO_MAX);

    return {
      llr,
      a,
      b,
      los,
      elo,
      ciLower,
      ciUpper,
    };
  }

  function clearAnimationTimers() {
    for (const timer of animationTimers) {
      clearTimeout(timer);
    }
    animationTimers = [];
  }

  function animateGaugeTo(chart, data, opts, targetValue, token, isFirstDraw) {
    const duration = isFirstDraw
      ? ANIMATION_DURATION_FIRST_MS
      : ANIMATION_DURATION_NEXT_MS;
    const animOpts = {
      ...opts,
      animation: {
        duration,
        easing: "out",
      },
    };

    chart.draw(data, animOpts);

    const timer = setTimeout(() => {
      if (token !== animationToken) {
        return;
      }
      data.setValue(0, 1, targetValue);
      chart.draw(data, animOpts);
    }, ANIMATION_START_DELAY_MS);
    animationTimers.push(timer);
  }

  function drawGauges(LLR, a, b, LOS, elo, ci_lower, ci_upper) {
    animationToken += 1;
    const token = animationToken;
    clearAnimationTimers();

    // LOS gauge
    const losStart = hasDrawnOnce ? lastLOS : 50;
    const LOS_data = google.visualization.arrayToDataTable([
      ["Label", "Value"],
      ["LOS", losStart],
    ]);
    const losValue = Math.round(10 * LOS) / 10;
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
    animateGaugeTo(
      LOS_chart,
      LOS_data,
      losOpts,
      losValue,
      token,
      !hasDrawnOnce,
    );
    lastLOS = losValue;

    // LLR gauge
    const llrValue = Math.round(100 * LLR) / 100;
    a = Math.round(100 * a) / 100;
    b = Math.round(100 * b) / 100;
    const llrStart = hasDrawnOnce ? clamp(lastLLR, a, b) : (a + b) / 2;
    const LLR_data = google.visualization.arrayToDataTable([
      ["Label", "Value"],
      ["LLR", llrStart],
    ]);
    const llrOpts = {
      width: 500,
      height: 150,
      greenFrom: b,
      greenTo: b * 1.04,
      redFrom: a * 1.04,
      redTo: a,
      yellowFrom: a,
      yellowTo: b,
      max: b,
      min: a,
      minorTicks: 3,
    };
    animateGaugeTo(
      LLR_chart,
      LLR_data,
      llrOpts,
      llrValue,
      token,
      !hasDrawnOnce,
    );
    lastLLR = llrValue;

    // ELO gauge (two draws for animation)
    const eloStart = hasDrawnOnce ? clamp(lastElo, ELO_MIN, ELO_MAX) : 0;
    const ELO_data = google.visualization.arrayToDataTable([
      ["Label", "Value"],
      ["Elo", eloStart],
    ]);
    const eloOpts = {
      width: 500,
      height: 150,
      max: 4,
      min: -4,
      minorTicks: 4,
    };
    if (ci_lower < 0 && ci_upper > 0) {
      eloOpts.redFrom = ci_lower;
      eloOpts.redTo = 0;
      eloOpts.yellowFrom = 0;
      eloOpts.yellowTo = 0;
      eloOpts.greenFrom = 0;
      eloOpts.greenTo = ci_upper;
    } else if (ci_lower >= 0) {
      eloOpts.redFrom = ci_lower;
      eloOpts.redTo = ci_lower;
      eloOpts.yellowFrom = ci_lower;
      eloOpts.yellowTo = ci_lower;
      eloOpts.greenFrom = ci_lower;
      eloOpts.greenTo = ci_upper;
    } else if (ci_upper <= 0) {
      eloOpts.redFrom = ci_lower;
      eloOpts.redTo = ci_upper;
      eloOpts.yellowFrom = ci_upper;
      eloOpts.yellowTo = ci_upper;
      eloOpts.greenFrom = ci_upper;
      eloOpts.greenTo = ci_upper;
    }
    elo = Math.round(100 * elo) / 100;
    animateGaugeTo(ELO_chart, ELO_data, eloOpts, elo, token, !hasDrawnOnce);
    lastElo = elo;
    hasDrawnOnce = true;
  }

  function updateFromDataAttrs(el) {
    if (!el) return;
    const d = el.dataset;
    const normalized = normalizeGauges({
      llr: parseFloat(d.llr),
      a: parseFloat(d.a),
      b: parseFloat(d.b),
      los: parseFloat(d.los),
      elo: parseFloat(d.elo),
      ciLower: parseFloat(d.ciLower),
      ciUpper: parseFloat(d.ciUpper),
    });
    drawGauges(
      normalized.llr,
      normalized.a,
      normalized.b,
      normalized.los,
      normalized.elo,
      normalized.ciLower,
      normalized.ciUpper,
    );
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
      updateFromDataAttrs(latestGaugeData);
    });
  }

  // Initial draw from server-rendered data attributes.
  scheduleGaugeUpdate(document.getElementById("gauge-data"));

  // Update on each htmx OOB swap (innerHTML of #live-elo-data).
  document.body.addEventListener("htmx:oobAfterSwap", (e) => {
    if (e?.detail?.target?.id === "live-elo-data") {
      scheduleGaugeUpdate(document.getElementById("gauge-data"));
    }
  });
})();
