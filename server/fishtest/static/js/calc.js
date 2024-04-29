"use strict";

const defaultParameters = {
  "elo-model": "Normalized",
  "elo-0": "0.0",
  "elo-1": "2.0",
  "draw-ratio": "0.49",
  "rms-bias": "191",
};

let validSprt = null;

google.charts.load("current", { packages: ["corechart"] });

let passChart = null;
let expectedChart = null;
let resizeTimeout;

google.charts.setOnLoadCallback(function () {
  const passProbChartDiv = document.getElementById("pass_prob_chart_div");
  passChart = new google.visualization.LineChart(passProbChartDiv);
  passChart.div = passProbChartDiv;
  passChart.loaded = false;
  google.visualization.events.addListener(passChart, "ready", function () {
    passChart.loaded = true;
  });

  const expectedChartDiv = document.getElementById("expected_chart_div");
  expectedChart = new google.visualization.LineChart(expectedChartDiv);
  expectedChart.div = expectedChartDiv;
  expectedChart.loaded = false;
  google.visualization.events.addListener(expectedChart, "ready", function () {
    expectedChart.loaded = true;
  });

  const mouseScreen = document.getElementById("mouse_screen");
  mouseScreen.addEventListener("click", (e) => e.stopPropagation(), true);
  mouseScreen.addEventListener("mouseover", (e) => e.stopPropagation(), true);
  mouseScreen.addEventListener("mousemove", handleTooltips, true);
  mouseScreen.addEventListener("mouseleave", handleTooltips, true);
  setFields();
  drawCharts(false);
  window.onresize = function () {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => drawCharts(true), 100);
  };
});

function setFieldFromUrl(name, defaultValue, currentValue) {
  const input = document.getElementById(name);
  input.value = currentValue !== null ? currentValue : defaultValue;
}

function setFields() {
  const urlObj = new URL(window.location.href);
  for (let key in defaultParameters) {
    setFieldFromUrl(key, defaultParameters[key], urlObj.searchParams.get(key));
  }
}

function drawCharts(resize) {
  const eloModel = document.getElementById("elo-model").value;
  let elo0 = parseFloat(document.getElementById("elo-0").value);
  let elo1 = parseFloat(document.getElementById("elo-1").value);
  const drawRatio = parseFloat(document.getElementById("draw-ratio").value);
  const rmsBias = parseFloat(document.getElementById("rms-bias").value);
  let error = "";
  let sprt = null;

  if (isNaN(elo0) || isNaN(elo1) || isNaN(drawRatio) || isNaN(rmsBias)) {
    error = "Unreadable input.";
  } else if (elo1 < elo0 + 0.5) {
    error = "The difference between Elo1 and Elo0 must be at least 0.5.";
  } else if (Math.abs(elo0) > 10 || Math.abs(elo1) > 10) {
    error = "Elo values must be between -10 and 10.";
  } else if (drawRatio <= 0.0 || drawRatio >= 1.0) {
    error = "The draw ratio must be strictly between 0.0 and 1.0.";
  } else if (rmsBias < 0) {
    error = "The RMS bias must be positive.";
  } else {
    sprt = new Sprt(0.05, 0.05, elo0, elo1, drawRatio, rmsBias, eloModel);
    if (sprt.variance <= 0) {
      error = "The draw ratio and the RMS bias are not compatible.";
    }
  }
  if (error) {
    // do not show a stale alert with a resize
    // and use last valid sprt to draw chart
    if (!resize || !validSprt) {
      if (alertError) {
        // if a global custom alertError is defined when using this package
        alertError(error);
      } else {
        alert(error);
      }

      return;
    } else sprt = validSprt;
  } else validSprt = sprt;

  history.replaceState(
    null,
    "",
    `/sprt_calc?elo-model=${eloModel}&elo-0=${elo0}&elo-1=${elo1}&draw-ratio=${drawRatio}&rms-bias=${rmsBias}`,
  );
  elo0 = sprt.elo0;
  elo1 = sprt.elo1;
  passChart.loaded = false;
  expectedChart.loaded = false;
  const dataPass = [["Elo", { role: "annotation" }, "Pass Probability"]];
  const dataExpected = [
    ["Elo", { role: "annotation" }, "Expected Number of Games"],
  ];
  const d = elo1 - elo0;
  const eloStart = Math.floor(elo0 - d / 3);
  const eloEnd = Math.ceil(elo1 + d / 3);
  const N = eloEnd - eloStart <= 5 ? 20 : 10;
  // pseudo globals
  passChart.eloStart = eloStart;
  passChart.eloEnd = eloEnd;
  const specials = [elo0, elo1];
  let anchors = [];
  passChart.anchors = anchors;
  for (let i = eloStart * N; i <= eloEnd * N; i += 1) {
    const elo = i / N;
    anchors.push(elo);
    const eloNext = (i + 1) / N;
    const c = sprt.characteristics(elo);
    dataPass.push([elo, null, { v: c[0], f: (c[0] * 100).toFixed(1) + "%" }]);
    dataExpected.push([
      elo,
      null,
      { v: c[1], f: (c[1] / 1000).toFixed(1) + "K" },
    ]);
    for (const elo_ of specials) {
      if (elo < elo_ && eloNext >= elo_) {
        anchors.push(elo_);
        const c_ = sprt.characteristics(elo_);
        dataPass.push([
          elo_,
          elo_,
          { v: c_[0], f: (c_[0] * 100).toFixed(1) + "%" },
        ]);
        dataExpected.push([
          elo_,
          elo_,
          { v: c_[1], f: (c_[1] / 1000).toFixed(1) + "K" },
        ]);
      }
    }
  }

  const chartTextStyle = { color: "#888" };
  const gridlinesStyle = { color: "#666" };
  const minorGridlinesStyle = { color: "#aaa" };
  const titleTextStyle = {
    color: "#999",
    fontSize: 16,
    bold: true,
    italic: false,
  };

  const options = {
    legend: {
      position: "none",
    },
    curveType: "function",
    hAxis: {
      title: "Logistic Elo",
      titleTextStyle: titleTextStyle,
      textStyle: chartTextStyle,
      gridlines: {
        count: eloEnd - eloStart,
        color: "#666",
      },
      minorGridlines: minorGridlinesStyle,
    },
    vAxis: {
      title: "Pass Probability",
      titleTextStyle: titleTextStyle,
      textStyle: chartTextStyle,
      gridlines: gridlinesStyle,
      minorGridlines: minorGridlinesStyle,
      format: "percent",
    },
    tooltip: {
      trigger: "selection",
    },
    backgroundColor: {
      fill: "transparent",
    },
    chartArea: {
      left: "15%",
      top: "5%",
      width: "80%",
      height: "80%",
    },
    annotations: {
      style: "line",
      stem: { color: "orange" },
      textStyle: titleTextStyle,
    },
  };
  let data_table = google.visualization.arrayToDataTable(dataPass);
  passChart.draw(data_table, options);
  options.vAxis = {
    title: "Expected Number of Games",
    titleTextStyle: titleTextStyle,
    textStyle: chartTextStyle,
    gridlines: gridlinesStyle,
    minorGridlines: minorGridlinesStyle,
    format: "short",
  };
  data_table = google.visualization.arrayToDataTable(dataExpected);
  expectedChart.draw(data_table, options);
}

function ready() {
  return (
    passChart !== null &&
    passChart.loaded &&
    expectedChart !== null &&
    expectedChart.loaded
  );
}

function contains(rect, x, y) {
  return x >= rect.left && x <= rect.right && y <= rect.bottom && y >= rect.top;
}

function handleTooltips(e) {
  // generic mouse events handler
  e.stopPropagation();
  if (!ready()) {
    return;
  }
  const x = e.clientX;
  const y = e.clientY;
  let rect;
  let rectPass = passChart.div.getBoundingClientRect();
  let rectExpected = expectedChart.div.getBoundingClientRect();
  let chart;
  if (contains(rectPass, x, y)) {
    chart = passChart;
    rect = rectPass;
  } else if (contains(rectExpected, x, y)) {
    chart = expectedChart;
    rect = rectExpected;
  } else {
    passChart.setSelection([]);
    expectedChart.setSelection([]);
    return;
  }
  const elo = chart.getChartLayoutInterface().getHAxisValue(x - rect.left);
  const anchors = passChart.anchors;
  let row;
  let lastDist = null;
  for (row = 0; row < anchors.length; row++) {
    const dist = Math.abs(anchors[row] - elo);
    if (lastDist !== null && dist > lastDist) {
      break;
    } else {
      lastDist = dist;
    }
  }
  row--;
  const eloStart = passChart.eloStart;
  const eloEnd = passChart.eloEnd;
  const d = (eloEnd - eloStart) / 20;
  if (elo >= eloStart - d && elo <= eloEnd + d) {
    passChart.setSelection([{ row: row, column: 2 }]);
    expectedChart.setSelection([{ row: row, column: 2 }]);
  } else {
    passChart.setSelection([]);
    expectedChart.setSelection([]);
  }
}
