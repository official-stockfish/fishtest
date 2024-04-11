async function handleSPSA() {
  let raw = [],
    chart_object,
    chart_data,
    data_cache = [],
    smoothing_factor = 0,
    smoothing_max = 20,
    columns = [],
    viewAll = false;

  const chartColors = [
    "#3366cc",
    "#dc3912",
    "#ff9900",
    "#109618",
    "#990099",
    "#0099c6",
    "#dd4477",
    "#66aa00",
    "#b82e2e",
    "#316395",
    "#994499",
    "#22aa99",
    "#aaaa11",
    "#6633cc",
    "#e67300",
    "#8b0707",
    "#651067",
    "#329262",
    "#5574a6",
    "#3b3eac",
    "#b77322",
    "#16d620",
    "#b91383",
    "#f4359e",
    "#9c5935",
    "#a9c413",
    "#2a778d",
    "#668d1c",
    "#bea413",
    "#0c5922",
    "#743411",
    "#3366cc",
    "#dc3912",
    "#ff9900",
    "#109618",
    "#990099",
    "#0099c6",
    "#dd4477",
    "#66aa00",
    "#b82e2e",
    "#316395",
    "#994499",
    "#22aa99",
    "#aaaa11",
    "#6633cc",
    "#e67300",
    "#8b0707",
    "#651067",
    "#329262",
    "#5574a6",
    "#3b3eac",
    "#b77322",
    "#16d620",
    "#b91383",
    "#f4359e",
    "#9c5935",
    "#a9c413",
    "#2a778d",
    "#668d1c",
    "#bea413",
    "#0c5922",
    "#743411",
  ];

  const chartInvisibleColor = "#ccc";
  const chartTextStyle = { color: "#888" };
  const gridlinesStyle = { color: "#666" };
  const minorGridlinesStyle = { color: "#ccc" };

  let chartOptions = {
    backgroundColor: {
      fill: "transparent",
    },
    curveType: "function",
    chartArea: {
      width: "800",
      height: "450",
      left: 40,
      top: 20,
    },
    width: 1000,
    height: 500,
    hAxis: {
      format: "percent",
      textStyle: chartTextStyle,
      gridlines: gridlinesStyle,
      minorGridlines: minorGridlinesStyle,
    },
    vAxis: {
      viewWindowMode: "maximized",
      textStyle: chartTextStyle,
      gridlines: gridlinesStyle,
      minorGridlines: minorGridlinesStyle,
    },
    legend: {
      position: "right",
      textStyle: chartTextStyle,
    },
    colors: chartColors.slice(0),
    seriesType: "line",
  };

  function gaussianKernelRegression(y, h) {
    if (!h) return y;

    let rf = [];
    for (let i = 0; i < y.length; i++) {
      let yt = 0;
      let zt = 0;
      for (let j = 0; j < y.length; j++) {
        const p = (i - j) / h;
        const z = Math.exp((p * -1 * p) / 2);
        zt += z;
        yt += z * y[j];
      }
      rf.push(yt / zt);
    }
    return rf;
  }

  function smoothData(b) {
    const spsaParams = spsaData.params;
    const spsaHistory = spsaData.param_history;
    const spsaIterRatio = Math.min(spsaData.iter / spsaData.num_iter, 1);

    //cache the raw data
    if (!raw.length) {
      for (let j = 0; j < spsaParams.length; j++) raw.push([]);
      for (let i = 0; i < spsaHistory.length; i++) {
        for (let j = 0; j < spsaParams.length; j++) {
          raw[j].push(spsaHistory[i][j].theta);
        }
      }
    }
    //cache data table to avoid recomputing the smoothed graph
    if (!data_cache[b]) {
      let dt = new google.visualization.DataTable();
      dt.addColumn("number", "Iteration");
      for (let i = 0; i < spsaParams.length; i++) {
        dt.addColumn("number", spsaParams[i].name);
      }
      // adjust the bandwidth for tests with samples != 101
      const h = b * ((spsaHistory.length - 1) / (spsaIterRatio * 100));
      let d = [];
      for (let j = 0; j < spsaParams.length; j++) {
        d.push(gaussianKernelRegression(raw[j], h));
      }
      let googleformat = [];
      for (let i = 0; i < spsaHistory.length; i++) {
        let c = [(i / (spsaHistory.length - 1)) * spsaIterRatio];
        for (let j = 0; j < spsaParams.length; j++) {
          c.push(d[j][i]);
        }
        googleformat.push(c);
      }
      dt.addRows(googleformat);
      data_cache[b] = dt;
    }
    chart_data = data_cache[b];
    redraw(true);
  }

  function redraw(animate) {
    chartOptions.animation = animate ? { duration: 800, easing: "out" } : {};
    let view = new google.visualization.DataView(chart_data);
    view.setColumns(columns);
    chart_object.draw(view, chartOptions);
  }

  function updateColumnVisibility(col, visibility) {
    if (!visibility) {
      columns[col] = {
        label: chart_data.getColumnLabel(col),
        type: chart_data.getColumnType(col),
        calc: function () {
          return null;
        },
      };
      chartOptions.colors[col - 1] = chartInvisibleColor;
    } else {
      columns[col] = col;
      chartOptions.colors[col - 1] =
        chartColors[(col - 1) % chartColors.length];
    }
  }
  await DOMContentLoaded();
  //fade in loader
  const loader = document.getElementById("spsa_preload");
  loader.style.display = "";
  loader.classList.add("fade");
  setTimeout(() => {
    loader.classList.add("show");
  }, 150);

  //load google library
  await google.charts.load("current", { packages: ["corechart"] });
  const spsaParams = spsaData.params;
  const spsaHistory = spsaData.param_history;
  const spsaIterRatio = Math.min(spsaData.iter / spsaData.num_iter, 1);

  if (!spsaHistory || spsaHistory.length < 2) {
    document.getElementById("spsa_preload").style.display = "none";
    const alertElement = document.createElement("div");
    alertElement.className = "alert alert-warning";
    alertElement.role = "alert";
    if (spsaParams.length >= 1000)
      alertElement.textContent = "Too many tuning parameters to generate plot.";
    else alertElement.textContent = "Not enough data to generate plot.";
    const historyPlot = document.getElementById("spsa_history_plot");
    historyPlot.replaceChildren();
    historyPlot.append(alertElement);
    return;
  }

  for (let i = 0; i < smoothing_max; i++) data_cache.push(false);

  let googleformat = [];
  for (let i = 0; i < spsaHistory.length; i++) {
    let d = [(i / (spsaHistory.length - 1)) * spsaIterRatio];
    for (let j = 0; j < spsaParams.length; j++) {
      d.push(spsaHistory[i][j].theta);
    }
    googleformat.push(d);
  }

  chart_data = new google.visualization.DataTable();

  chart_data.addColumn("number", "Iteration");
  for (let i = 0; i < spsaParams.length; i++) {
    chart_data.addColumn("number", spsaParams[i].name);
  }
  chart_data.addRows(googleformat);

  data_cache[0] = chart_data;
  chart_object = new google.visualization.LineChart(
    document.getElementById("spsa_history_plot"),
  );
  chart_object.draw(chart_data, chartOptions);
  document.getElementById("chart_toolbar").style.display = "";

  for (let i = 0; i < chart_data.getNumberOfColumns(); i++) {
    columns.push(i);
  }

  for (let j = 0; j < spsaParams.length; j++) {
    const dropdownItem = document.createElement("li");
    const anchorItem = document.createElement("a");
    anchorItem.className = "dropdown-item";
    anchorItem.href = "javascript:";
    anchorItem.param_id = j + 1;
    anchorItem.append(spsaParams[j].name);
    dropdownItem.append(anchorItem);
    document.getElementById("dropdown_individual").append(dropdownItem);
  }

  document
    .getElementById("dropdown_individual")
    .addEventListener("click", (e) => {
      if (!e.target.matches("a")) return;
      const { target } = e;
      const param_id = target.param_id;
      for (let i = 1; i < chart_data.getNumberOfColumns(); i++) {
        updateColumnVisibility(i, i == param_id);
      }

      viewAll = false;
      redraw(false);
    });

  //show/hide functionality
  google.visualization.events.addListener(chart_object, "select", function (e) {
    let sel = chart_object.getSelection();
    if (sel.length > 0 && sel[0].row == null) {
      const col = sel[0].column;
      updateColumnVisibility(col, columns[col] != col);
      redraw(false);
    }
    viewAll = false;
  });

  document.getElementById("spsa_preload").style.display = "none";

  document.getElementById("btn_smooth_plus").addEventListener("click", () => {
    if (smoothing_factor < smoothing_max) {
      smoothData(++smoothing_factor);
    }
  });

  document.getElementById("btn_smooth_minus").addEventListener("click", () => {
    if (smoothing_factor > 0) {
      smoothData(--smoothing_factor);
    }
  });

  document.getElementById("btn_view_all").addEventListener("click", () => {
    if (viewAll) return;
    viewAll = true;
    for (let i = 0; i < chart_data.getNumberOfColumns(); i++) {
      updateColumnVisibility(i, true);
    }

    redraw(false);
  });
}
