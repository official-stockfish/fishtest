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

  function drawGauges(LLR, a, b, LOS, elo, ci_lower, ci_upper) {
    // LOS gauge
    const LOS_data = google.visualization.arrayToDataTable([
      ["Label", "Value"],
      ["LOS", lastLOS],
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
    LOS_chart.draw(LOS_data, losOpts);
    LOS_data.setValue(0, 1, losValue);
    LOS_chart.draw(LOS_data, losOpts);
    lastLOS = losValue;

    // LLR gauge
    const LLR_data = google.visualization.arrayToDataTable([
      ["Label", "Value"],
      ["LLR", lastLLR],
    ]);
    const llrValue = Math.round(100 * LLR) / 100;
    a = Math.round(100 * a) / 100;
    b = Math.round(100 * b) / 100;
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
    LLR_chart.draw(LLR_data, llrOpts);
    LLR_data.setValue(0, 1, llrValue);
    LLR_chart.draw(LLR_data, llrOpts);
    lastLLR = llrValue;

    // ELO gauge (two draws for animation)
    const ELO_data = google.visualization.arrayToDataTable([
      ["Label", "Value"],
      ["Elo", lastElo],
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
    ELO_chart.draw(ELO_data, eloOpts);
    elo = Math.round(100 * elo) / 100;
    ELO_data.setValue(0, 1, elo);
    ELO_chart.draw(ELO_data, eloOpts);
    lastElo = elo;
  }

  function updateFromDataAttrs(el) {
    if (!el) return;
    const d = el.dataset;
    drawGauges(
      parseFloat(d.llr),
      parseFloat(d.a),
      parseFloat(d.b),
      parseFloat(d.los),
      parseFloat(d.elo),
      parseFloat(d.ciLower),
      parseFloat(d.ciUpper),
    );
  }

  // Initial draw from server-rendered data attributes.
  updateFromDataAttrs(document.getElementById("gauge-data"));

  // Update on each htmx OOB swap (innerHTML of #live-elo-data).
  document.body.addEventListener("htmx:oobAfterSwap", (e) => {
    if (e.detail.target.id === "live-elo-data") {
      updateFromDataAttrs(document.getElementById("gauge-data"));
    }
  });
})();
