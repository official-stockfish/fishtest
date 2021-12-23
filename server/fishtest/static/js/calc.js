"use strict";

google.charts.load("current", { packages: ["corechart"] });

var pass_chart = null;
var expected_chart = null;

google.charts.setOnLoadCallback(function () {
  var pass_prob_chart_div = document.getElementById("pass_prob_chart_div");
  pass_chart = new google.visualization.LineChart(pass_prob_chart_div);
  pass_chart.div = pass_prob_chart_div;
  pass_chart.loaded = false;
  google.visualization.events.addListener(pass_chart, "ready", function () {
    pass_chart.loaded = true;
  });

  var expected_chart_div = document.getElementById("expected_chart_div");
  expected_chart = new google.visualization.LineChart(expected_chart_div);
  expected_chart.div = expected_chart_div;
  expected_chart.loaded = false;
  google.visualization.events.addListener(expected_chart, "ready", function () {
    expected_chart.loaded = true;
  });

  var mouse_screen = document.getElementById("mouse_screen");
  mouse_screen.addEventListener(
    "click",
    function (e) {
      e.stopPropagation();
    },
    true
  );
  mouse_screen.addEventListener(
    "mouseover",
    function (e) {
      e.stopPropagation();
    },
    true
  );
  mouse_screen.addEventListener("mousemove", handle_tooltips, true);
  mouse_screen.addEventListener("mouseleave", handle_tooltips, true);
  set_fields();
  draw_charts();
});

function set_field_from_url(name, defaultValue) {
  var value = url("?" + name);
  var input = document.getElementById(name);
  input.value = value !== null ? value : defaultValue;
}

function set_fields() {
  set_field_from_url("elo-model", "Normalized");
  set_field_from_url("elo-0", "-1");
  set_field_from_url("elo-1", "3");
  set_field_from_url("draw-ratio", "0.61");
  set_field_from_url("rms-bias", "0");
}

function draw_charts() {
  var elo_model = document.getElementById("elo-model").value;
  var elo0 = parseFloat(document.getElementById("elo-0").value);
  var elo1 = parseFloat(document.getElementById("elo-1").value);
  var draw_ratio = parseFloat(document.getElementById("draw-ratio").value);
  var rms_bias = parseFloat(document.getElementById("rms-bias").value);
  var val = "";
  if (isNaN(elo0) || isNaN(elo1) || isNaN(draw_ratio) || isNaN(rms_bias)) {
    val = "Unreadable input.";
  } else if (elo1 < elo0 + 0.5) {
    val = "The difference between Elo1 and Elo0 must be at least 0.5.";
  } else if (Math.abs(elo0) > 10 || Math.abs(elo1) > 10) {
    val = "Elo values must be between -10 and 10.";
  } else if (draw_ratio <= 0.0 || draw_ratio >= 1.0) {
    val = "The draw ratio must be strictly between 0.0 and 1.0.";
  } else if (rms_bias < 0) {
    val = "The RMS bias must be positive.";
  } else {
    var sprt = new Sprt(
      0.05,
      0.05,
      elo0,
      elo1,
      draw_ratio,
      rms_bias,
      elo_model
    );
    if (sprt.variance <= 0) {
      val = "The draw ratio and the RMS bias are not compatible.";
    }
  }
  if (val != "") {
    alert(val);
    return;
  }
  elo0 = sprt.elo0;
  elo1 = sprt.elo1;
  pass_chart.loaded = false;
  expected_chart.loaded = false;
  var data_pass = [["Elo", { role: "annotation" }, "Pass Probability"]];
  var data_expected = [
    ["Elo", { role: "annotation" }, "Expected Number of Games"],
  ];
  var d = elo1 - elo0;
  var elo_start = Math.floor(elo0 - d / 3);
  var elo_end = Math.ceil(elo1 + d / 3);
  var N = elo_end - elo_start <= 5 ? 20 : 10;
  // pseudo globals
  pass_chart.elo_start = elo_start;
  pass_chart.elo_end = elo_end;
  const specials = [elo0, elo1];
  var anchors = [];
  pass_chart.anchors = anchors;
  for (var i = elo_start * N; i <= elo_end * N; i += 1) {
    var elo = i / N;
    anchors.push(elo);
    var elo_next = (i + 1) / N;
    var c = sprt.characteristics(elo);
    data_pass.push([elo, null, { v: c[0], f: (c[0] * 100).toFixed(1) + "%" }]);
    data_expected.push([
      elo,
      null,
      { v: c[1], f: (c[1] / 1000).toFixed(1) + "K" },
    ]);
    for (const elo_ of specials) {
      if (elo < elo_ && elo_next >= elo_) {
        anchors.push(elo_);
        var c_ = sprt.characteristics(elo_);
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
  var options = {
    legend: { position: "none" },
    curveType: "function",
    hAxis: { title: "Logistic Elo", gridlines: { count: elo_end - elo_start } },
    vAxis: { title: "Pass Probability", format: "percent" },
    tooltip: { trigger: "selection" },
    chartArea: {
      backgroundColor: "#F0F0F0",
      left: "15%",
      top: "5%",
      width: "80%",
      height: "80%",
    },
    annotations: { style: "line", stem: { color: "orange" } },
  };
  var data_table = google.visualization.arrayToDataTable(data_pass);
  pass_chart.draw(data_table, options);
  options.vAxis = { title: "Expected Number of Games", format: "short" };
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
  var x = e.clientX;
  var y = e.clientY;
  var rect;
  var rect_pass = pass_chart.div.getBoundingClientRect();
  var rect_expected = expected_chart.div.getBoundingClientRect();
  var chart;
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
  var elo = chart.getChartLayoutInterface().getHAxisValue(x - rect.left);
  var anchors = pass_chart.anchors;
  var last_dist = null;
  for (var row = 0; row < anchors.length; row++) {
    var dist = Math.abs(anchors[row] - elo);
    if (last_dist != null && dist > last_dist) {
      break;
    } else {
      last_dist = dist;
    }
  }
  row--;
  var elo_start = pass_chart.elo_start;
  var elo_end = pass_chart.elo_end;
  var d = (elo_end - elo_start) / 20;
  if (elo >= elo_start - d && elo <= elo_end + d) {
    pass_chart.setSelection([{ row: row, column: 2 }]);
    expected_chart.setSelection([{ row: row, column: 2 }]);
  } else {
    pass_chart.setSelection([]);
    expected_chart.setSelection([]);
  }
}
