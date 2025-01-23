async function handleSPSA() {
  let raw = [],
    chartObject,
    chartData,
    dataCache = [],
    smoothingFactor = 0,
    smoothingMax = 20,
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
  let usePercentage = false;

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
      format: usePercentage ? "percent" : "decimal",
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

  function gaussianKernelRegression(values, bandwidth) {
    if (!bandwidth) return values;

    let smoothedValues = [];
    for (let i = 0; i < values.length; i++) {
      let weightedSum = 0;
      let weightTotal = 0;
      for (let j = 0; j < values.length; j++) {
        const distance = (i - j) / bandwidth;
        const weight = Math.exp(-0.5 * distance * distance);
        weightTotal += weight;
        weightedSum += weight * values[j];
      }
      smoothedValues.push(weightedSum / weightTotal);
    }
    return smoothedValues;
  }

  function smoothData(smoothingFactor) {
    const spsaParams = spsaData.params;
    const spsaHistory = spsaData.param_history;
    const spsaIterRatio = Math.min(spsaData.iter / spsaData.num_iter, 1);

    // cache the raw data
    if (!raw.length) {
      for (let j = 0; j < spsaParams.length; j++) raw.push([]);
      for (let i = 0; i < spsaHistory.length; i++) {
        for (let j = 0; j < spsaParams.length; j++) {
          raw[j].push(spsaHistory[i][j].theta);
        }
      }
    }
    // cache data table to avoid recomputing the smoothed graph
    if (!dataCache[smoothingFactor]) {
      let dt = new google.visualization.DataTable();
      dt.addColumn("number", "Iteration");
      for (let i = 0; i < spsaParams.length; i++) {
        dt.addColumn("number", spsaParams[i].name);
      }
      // adjust the bandwidth for tests with samples != 101
      const bandwidth =
        smoothingFactor * ((spsaHistory.length - 1) / (spsaIterRatio * 100));
      let data = [];
      for (let j = 0; j < spsaParams.length; j++) {
        data.push(gaussianKernelRegression(raw[j], bandwidth));
      }
      let googleFormat = [];
      for (let i = 0; i < spsaHistory.length; i++) {
        let rowData = [(i / (spsaHistory.length - 1)) * spsaIterRatio];
        for (let j = 0; j < spsaParams.length; j++) {
          rowData.push(data[j][i]);
        }
        googleFormat.push(rowData);
      }
      dt.addRows(googleFormat);
      dataCache[smoothingFactor] = dt;
    }
    chartData = dataCache[smoothingFactor];
    chartOptions.vAxis.format = usePercentage ? "percent" : "decimal";
    if (usePercentage) {
      let view = new google.visualization.DataView(chartData);
      view.setColumns([
        0,
        ...spsaParams.map((_, i) => ({
          calc: function (dt, row) {
            // column 0 is the iteration number, the parameter columns start from index 1
            return (
              (dt.getValue(row, i + 1) - spsaParams[i].start) /
              spsaHistory[row][i].c
            );
          },
          type: "number",
          label: spsaParams[i].name,
        })),
      ]);
      chartData = view;
    }
    redraw(true);
  }

  function redraw(animate) {
    chartOptions.animation = animate ? { duration: 800, easing: "out" } : {};
    let view = new google.visualization.DataView(chartData);
    view.setColumns(columns);
    chartObject.draw(view, chartOptions);
  }

  function updateColumnVisibility(col, visibility) {
    if (!visibility) {
      columns[col] = {
        label: chartData.getColumnLabel(col),
        type: chartData.getColumnType(col),
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
  // fade in loader
  const loader = document.getElementById("spsa_preload");
  loader.style.display = "";
  loader.classList.add("fade");
  setTimeout(() => {
    loader.classList.add("show");
  }, 150);

  // load google library
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

  for (let i = 0; i < smoothingMax; i++) dataCache.push(false);

  let googleFormat = [];
  for (let i = 0; i < spsaHistory.length; i++) {
    let rowData = [(i / (spsaHistory.length - 1)) * spsaIterRatio];
    for (let j = 0; j < spsaParams.length; j++) {
      if (usePercentage) {
        rowData.push(
          (spsaHistory[i][j].theta - spsaParams[j].start) / spsaHistory[i][j].c,
        );
      } else {
        rowData.push(spsaHistory[i][j].theta);
      }
    }
    googleFormat.push(rowData);
  }

  chartData = new google.visualization.DataTable();

  chartData.addColumn("number", "Iteration");
  for (let i = 0; i < spsaParams.length; i++) {
    chartData.addColumn("number", spsaParams[i].name);
  }
  chartData.addRows(googleFormat);

  dataCache[0] = chartData;
  chartObject = new google.visualization.LineChart(
    document.getElementById("spsa_history_plot"),
  );
  chartObject.draw(chartData, chartOptions);
  document.getElementById("chart_toolbar").style.display = "";

  for (let i = 0; i < chartData.getNumberOfColumns(); i++) {
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
      const paramId = target.param_id;
      for (let i = 1; i < chartData.getNumberOfColumns(); i++) {
        updateColumnVisibility(i, i == paramId);
      }

      viewAll = false;
      redraw(false);
    });

  // show/hide functionality
  google.visualization.events.addListener(chartObject, "select", function (e) {
    let sel = chartObject.getSelection();
    if (sel.length > 0 && sel[0].row == null) {
      const col = sel[0].column;
      updateColumnVisibility(col, columns[col] != col);
      redraw(false);
    }
    viewAll = false;
  });

  document.getElementById("spsa_preload").style.display = "none";

  document.getElementById("btn_smooth_plus").addEventListener("click", () => {
    if (smoothingFactor < smoothingMax) {
      smoothData(++smoothingFactor);
    }
  });

  document.getElementById("btn_smooth_minus").addEventListener("click", () => {
    if (smoothingFactor > 0) {
      smoothData(--smoothingFactor);
    }
  });

  document.getElementById("btn_view_all").addEventListener("click", () => {
    if (viewAll) return;
    viewAll = true;
    for (let i = 0; i < chartData.getNumberOfColumns(); i++) {
      updateColumnVisibility(i, true);
    }

    redraw(false);
  });

  document.getElementById("spsa_percentage").addEventListener("change", (e) => {
    usePercentage = e.target.checked;
    smoothData(smoothingFactor);
  });
}
