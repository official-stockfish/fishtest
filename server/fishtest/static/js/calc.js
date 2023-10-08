"use strict";

const defaultParameters = {
  "elo-model": "Normalized",
  "elo-0": "0.0",
  "elo-1": "2.0",
  "draw-ratio": "0.49",
  "rms-bias": "191",
};

let valid_sprt = null;

google.charts.load("current", { packages: ["corechart"] });

let pass_chart = null;
let expected_chart = null;
let resize_timeout;

google.charts.setOnLoadCallback(function () {
  const pass_prob_chart_div = document.getElementById("pass_prob_chart_div");
  pass_chart = new google.visualization.LineChart(pass_prob_chart_div);
  pass_chart.div = pass_prob_chart_div;
  pass_chart.loaded = false;
  google.visualization.events.addListener(pass_chart, "ready", function () {
    pass_chart.loaded = true;
  });

  const expected_chart_div = document.getElementById("expected_chart_div");
  expected_chart = new google.visualization.LineChart(expected_chart_div);
  expected_chart.div = expected_chart_div;
  expected_chart.loaded = false;
  google.visualization.events.addListener(expected_chart, "ready", function () {
    expected_chart.loaded = true;
  });

  const mouse_screen = document.getElementById("mouse_screen");
  mouse_screen.addEventListener("click", (e) => e.stopPropagation(), true);
  mouse_screen.addEventListener("mouseover", (e) => e.stopPropagation(), true);
  mouse_screen.addEventListener("mousemove", handle_tooltips, true);
  mouse_screen.addEventListener("mouseleave", handle_tooltips, true);
  set_fields();
  draw_charts(false);
  window.onresize = function () {
    clearTimeout(resize_timeout);
    resize_timeout = setTimeout(() => draw_charts(true), 100);
  };
});

function set_field_from_url(name, defaultValue, currentValue) {
  const input = document.getElementById(name);
  input.value = currentValue !== null ? currentValue : defaultValue;
}

function set_fields() {
  const urlObj = new URL(window.location.href);
  for (let key in defaultParameters) {
    set_field_from_url(
      key,
      defaultParameters[key],
      urlObj.searchParams.get(key),
    );
  }
}

function draw_charts(resize) {
  const elo_model = document.getElementById("elo-model").value;
  let elo0 = parseFloat(document.getElementById("elo-0").value);
  let elo1 = parseFloat(document.getElementById("elo-1").value);
  const draw_ratio = parseFloat(document.getElementById("draw-ratio").value);
  const rms_bias = parseFloat(document.getElementById("rms-bias").value);
  let error = "";
  let sprt = null;

  if (isNaN(elo0) || isNaN(elo1) || isNaN(draw_ratio) || isNaN(rms_bias)) {
    error = "Unreadable input.";
  } else if (elo1 < elo0 + 0.5) {
    error = "The difference between Elo1 and Elo0 must be at least 0.5.";
  } else if (Math.abs(elo0) > 10 || Math.abs(elo1) > 10) {
    error = "Elo values must be between -10 and 10.";
  } else if (draw_ratio <= 0.0 || draw_ratio >= 1.0) {
    error = "The draw ratio must be strictly between 0.0 and 1.0.";
  } else if (rms_bias < 0) {
    error = "The RMS bias must be positive.";
  } else {
    sprt = new Sprt(0.05, 0.05, elo0, elo1, draw_ratio, rms_bias, elo_model);
    if (sprt.variance <= 0) {
      error = "The draw ratio and the RMS bias are not compatible.";
    }
  }
  if (error) {
    // do not show a stale alert with a resize
    // and use last valid sprt to draw chart
    if (!resize || !valid_sprt) {
      alert(error);
      return;
    } else sprt = valid_sprt;
  } else valid_sprt = sprt;

  history.replaceState(
    null,
    "",
    `/sprt_calc?elo-model=${elo_model}&elo-0=${elo0}&elo-1=${elo1}&draw-ratio=${draw_ratio}&rms-bias=${rms_bias}`,
  );
  elo0 = sprt.elo0;
  elo1 = sprt.elo1;
  pass_chart.loaded = false;
  expected_chart.loaded = false;
  const data_pass = [["Elo", { role: "annotation" }, "Pass Probability"]];
  const data_expected = [
    ["Elo", { role: "annotation" }, "Expected Number of Games"],
  ];
  const d = elo1 - elo0;
  const elo_start = Math.floor(elo0 - d / 3);
  const elo_end = Math.ceil(elo1 + d / 3);
  const N = elo_end - elo_start <= 5 ? 20 : 10;
  // pseudo globals
  pass_chart.elo_start = elo_start;
  pass_chart.elo_end = elo_end;
  const specials = [elo0, elo1];
  let anchors = [];
  pass_chart.anchors = anchors;
  for (let i = elo_start * N; i <= elo_end * N; i += 1) {
    const elo = i / N;
    anchors.push(elo);
    const elo_next = (i + 1) / N;
    const c = sprt.characteristics(elo);
    data_pass.push([elo, null, { v: c[0], f: (c[0] * 100).toFixed(1) + "%" }]);
    data_expected.push([
      elo,
      null,
      { v: c[1], f: (c[1] / 1000).toFixed(1) + "K" },
    ]);
    for (const elo_ of specials) {
      if (elo < elo_ && elo_next >= elo_) {
        anchors.push(elo_);
        const c_ = sprt.characteristics(elo_);
        data_pass.push([
          elo_,
          elo_,
          { v: c_[0], f: (c_[0] * 100).toFixed(1) + "%" },
        ]);
        data_expected.push([
          elo_,
          elo_,
          { v: c_[1], f: (c_[1] / 1000).toFixed(1) + "K" },
        ]);
      }
    }
  }

  const chart_text_style = { color: "#888" };
  const gridlines_style = { color: "#666" };
  const minor_gridlines_style = { color: "#aaa" };
  const title_text_style = {
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
      titleTextStyle: title_text_style,
      textStyle: chart_text_style,
      gridlines: {
        count: elo_end - elo_start,
        color: "#666",
      },
      minorGridlines: minor_gridlines_style,
    },
    vAxis: {
      title: "Pass Probability",
      titleTextStyle: title_text_style,
      textStyle: chart_text_style,
      gridlines: gridlines_style,
      minorGridlines: minor_gridlines_style,
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
      textStyle: title_text_style,
    },
  };
  let data_table = google.visualization.arrayToDataTable(data_pass);
  pass_chart.draw(data_table, options);
  options.vAxis = {
    title: "Expected Number of Games",
    titleTextStyle: title_text_style,
    textStyle: chart_text_style,
    gridlines: gridlines_style,
    minorGridlines: minor_gridlines_style,
    format: "short",
  };
  data_table = google.visualization.arrayToDataTable(data_expected);
  expected_chart.draw(data_table, options);
}

function ready() {
  return (
    pass_chart != null &&
    pass_chart.loaded &&
    expected_chart != null &&
    expected_chart.loaded
  );
}

function contains(rect, x, y) {
  return x >= rect.left && x <= rect.right && y <= rect.bottom && y >= rect.top;
}

function handle_tooltips(e) {
  // generic mouse events handler
  e.stopPropagation();
  if (!ready()) {
    return;
  }
  const x = e.clientX;
  const y = e.clientY;
  let rect;
  let rect_pass = pass_chart.div.getBoundingClientRect();
  let rect_expected = expected_chart.div.getBoundingClientRect();
  let chart;
  if (contains(rect_pass, x, y)) {
    chart = pass_chart;
    rect = rect_pass;
  } else if (contains(rect_expected, x, y)) {
    chart = expected_chart;
    rect = rect_expected;
  } else {
    pass_chart.setSelection([]);
    expected_chart.setSelection([]);
    return;
  }
  const elo = chart.getChartLayoutInterface().getHAxisValue(x - rect.left);
  const anchors = pass_chart.anchors;
  let row;
  let last_dist = null;
  for (row = 0; row < anchors.length; row++) {
    const dist = Math.abs(anchors[row] - elo);
    if (last_dist != null && dist > last_dist) {
      break;
    } else {
      last_dist = dist;
    }
  }
  row--;
  const elo_start = pass_chart.elo_start;
  const elo_end = pass_chart.elo_end;
  const d = (elo_end - elo_start) / 20;
  if (elo >= elo_start - d && elo <= elo_end + d) {
    pass_chart.setSelection([{ row: row, column: 2 }]);
    expected_chart.setSelection([{ row: row, column: 2 }]);
  } else {
    pass_chart.setSelection([]);
    expected_chart.setSelection([]);
  }
}
