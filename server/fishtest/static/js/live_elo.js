"use strict";

google.charts.load("current", { packages: ["gauge"] });
let LOS_chart = null;
let LLR_chart = null;
let ELO_chart = null;

google.charts.setOnLoadCallback(function () {
  LOS_chart = new google.visualization.Gauge(
    document.getElementById("LOS_chart_div")
  );
  LLR_chart = new google.visualization.Gauge(
    document.getElementById("LLR_chart_div")
  );
  ELO_chart = new google.visualization.Gauge(
    document.getElementById("ELO_chart_div")
  );
  clear_gauges();
  follow_live(test_id);
});

function collect(m) {
  const sprt = m.args.sprt;
  const results = m.results;
  const ret = m.elo;
  ret.alpha = sprt.alpha;
  ret.beta = sprt.beta;
  ret.elo_raw0 = sprt.elo0;
  ret.elo_raw1 = sprt.elo1;
  ret.elo_model = sprt.elo_model;
  ret.W = results.wins;
  ret.D = results.draws;
  ret.L = results.losses;
  ret.ci_lower = ret.ci[0];
  ret.ci_upper = ret.ci[1];
  ret.games = ret.W + ret.D + ret.L;
  ret.p = 0.05;
  return ret;
}

function set_gauges(LLR, a, b, LOS, elo, ci_lower, ci_upper) {
  if (!set_gauges.last_elo) {
    set_gauges.last_elo = 0;
  }
  const LOS_chart_data = google.visualization.arrayToDataTable([
    ["Label", "Value"],
    ["LOS", Math.round(1000 * LOS) / 10],
  ]);
  const LOS_chart_options = {
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
  LOS_chart.draw(LOS_chart_data, LOS_chart_options);

  const LLR_chart_data = google.visualization.arrayToDataTable([
    ["Label", "Value"],
    ["LLR", Math.round(100 * LLR) / 100],
  ]);
  a = Math.round(100 * a) / 100;
  b = Math.round(100 * b) / 100;
  const LLR_chart_options = {
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
  LLR_chart.draw(LLR_chart_data, LLR_chart_options);

  const ELO_chart_data = google.visualization.arrayToDataTable([
    ["Label", "Value"],
    ["Elo", set_gauges.last_elo],
  ]);
  const ELO_chart_options = {
    width: 500,
    height: 150,
    max: 4,
    min: -4,
    minorTicks: 4,
  };
  if (ci_lower < 0 && ci_upper > 0) {
    ELO_chart_options.redFrom = ci_lower;
    ELO_chart_options.redTo = 0;
    ELO_chart_options.yellowFrom = 0;
    ELO_chart_options.yellowTo = 0;
    ELO_chart_options.greenFrom = 0;
    ELO_chart_options.greenTo = ci_upper;
  } else if (ci_lower >= 0) {
    ELO_chart_options.redFrom = ci_lower;
    ELO_chart_options.redTo = ci_lower;
    ELO_chart_options.yellowFrom = ci_lower;
    ELO_chart_options.yellowTo = ci_lower;
    ELO_chart_options.greenFrom = ci_lower;
    ELO_chart_options.greenTo = ci_upper;
  } else if (ci_upper <= 0) {
    ELO_chart_options.redFrom = ci_lower;
    ELO_chart_options.redTo = ci_upper;
    ELO_chart_options.yellowFrom = ci_upper;
    ELO_chart_options.yellowTo = ci_upper;
    ELO_chart_options.greenFrom = ci_upper;
    ELO_chart_options.greenTo = ci_upper;
  }
  ELO_chart.draw(ELO_chart_data, ELO_chart_options);
  elo = Math.round(100 * elo) / 100;
  ELO_chart_data.setValue(0, 1, elo);
  ELO_chart.draw(ELO_chart_data, ELO_chart_options); // 2nd draw to get animation
  set_gauges.last_elo = elo;
}

function clear_gauges() {
  set_gauges(0, -2.94, 2.94, 0.5, 0, 0, 0);
}

const entityMap = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
  "/": "&#x2F;",
  "`": "&#x60;",
  "=": "&#x3D;",
};

function escapeHtml(string) {
  return String(string).replace(/[&<>"'`=\/]/g, function (s) {
    return entityMap[s];
  });
}

function display_data(items) {
  const j = collect(items);
  document.getElementById("error").style.display = "none";
  document.getElementById("data").style.visibility = "visible";
  document.getElementById("commit").innerHTML =
    "<a href=" +
    items.args.tests_repo +
    "/compare/" +
    items.args.resolved_base +
    "..." +
    items.args.resolved_new +
    ">" +
    escapeHtml(items.args.new_tag) +
    " (" +
    escapeHtml(items.args.msg_new) +
    ")</a>";
  document.getElementById("username").innerHTML = escapeHtml(
    items.args.username
  );
  document.getElementById("tc").innerHTML = escapeHtml(items.args.tc);
  document.getElementById("info").innerHTML = escapeHtml(items.args.info);
  document.getElementById("sprt").innerHTML =
    "elo0:&nbsp;" +
    j.elo_raw0.toFixed(2) +
    "&nbsp;&nbsp;alpha:&nbsp;" +
    j.alpha.toFixed(2) +
    "&nbsp;&nbsp;elo1:&nbsp;" +
    j.elo_raw1.toFixed(2) +
    "&nbsp;&nbsp;beta:&nbsp;" +
    j.beta.toFixed(2) +
    " (" +
    j.elo_model +
    ")";
  document.getElementById("elo").innerHTML =
    j.elo.toFixed(2) +
    " [" +
    j.ci_lower.toFixed(2) +
    "," +
    j.ci_upper.toFixed(2) +
    "] (" +
    100 * (1 - j.p).toFixed(2) +
    "%" +
    ")";
  document.getElementById("LLR").innerHTML =
    j.LLR.toFixed(2) +
    " [" +
    j.a.toFixed(2) +
    "," +
    j.b.toFixed(2) +
    "]" +
    (items.args.sprt.state ? " (" + items.args.sprt.state + ")" : "");
  document.getElementById("LOS").innerHTML =
    "" + (100 * j.LOS).toFixed(1) + "%";
  document.getElementById("games").innerHTML =
    j.games +
    " [w:" +
    ((100 * Math.round(j.W)) / (j.games + 0.001)).toFixed(1) +
    "%, l:" +
    ((100 * Math.round(j.L)) / (j.games + 0.001)).toFixed(1) +
    "%, d:" +
    ((100 * Math.round(j.D)) / (j.games + 0.001)).toFixed(1) +
    "%]";

  set_gauges(j.LLR, j.a, j.b, j.LOS, j.elo, j.ci_lower, j.ci_upper);
}

// Main worker.
function follow_live(test_id) {
  if (follow_live.timer_once === undefined) {
    follow_live.timer_once = null;
  }
  if (follow_live.timer_once != null) {
    clearTimeout(follow_live.timer_once);
    follow_live.timer_once = null;
  }
  let xhttp = new XMLHttpRequest();
  const timestamp = new Date().getTime();
  xhttp.open("GET", "/api/get_elo/" + test_id + "?" + timestamp, true);
  xhttp.onreadystatechange = function () {
    if (this.readyState == 4) {
      if (this.status == 200) {
        const m = JSON.parse(this.responseText);
        if (!m.args.sprt.state)
          follow_live.timer_once = setTimeout(follow_live, 20000, test_id);
        display_data(m);
      } else {
        follow_live.timer_once = setTimeout(follow_live, 20000, test_id);
      }
    }
  };
  xhttp.send();
}
