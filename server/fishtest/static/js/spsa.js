"use strict";

let googleChartsPromise = null;
let queueSPSARefresh = null;
let spsaOobListenerRegistered = false;

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

function waitForGoogleCharts() {
  if (!googleChartsPromise) {
    const loadResult = google.charts.load("current", {
      packages: ["corechart"],
    });
    if (loadResult && typeof loadResult.then === "function") {
      googleChartsPromise = loadResult;
    } else {
      googleChartsPromise = new Promise((resolve) => {
        google.charts.setOnLoadCallback(resolve);
      });
    }
  }

  return googleChartsPromise;
}

function getSPSARoot() {
  return document.getElementById("tests-view-spsa");
}

function getSPSADataElement() {
  return (
    getSPSARoot()?.querySelector(
      'script[type="application/json"][id^="spsa-data-"]',
    ) || null
  );
}

function readSPSAData() {
  const dataElement = getSPSADataElement();
  if (!dataElement) {
    return null;
  }

  try {
    return JSON.parse(dataElement.textContent || "{}");
  } catch (error) {
    console.warn("Unable to parse SPSA data", error);
    return null;
  }
}

function asFiniteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function buildChartOptions() {
  return {
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
      format: "decimal",
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
}

function setLoaderVisible(visible) {
  const loader = document.getElementById("spsa_preload");
  if (!loader) {
    return;
  }

  if (visible) {
    loader.style.display = "";
    loader.classList.add("fade");
    setTimeout(() => {
      if (loader.isConnected && loader.style.display !== "none") {
        loader.classList.add("show");
      }
    }, 150);
    return;
  }

  loader.style.display = "none";
  loader.classList.remove("show");
}

function showSPSAAlert(text) {
  const historyPlot = document.getElementById("spsa_history_plot");
  if (!historyPlot) {
    return;
  }

  const alertElement = document.createElement("div");
  alertElement.className = "alert alert-warning";
  alertElement.role = "alert";
  alertElement.textContent = text;
  historyPlot.replaceChildren(alertElement);
}

async function handleSPSA() {
  const dataCache = [];
  const columns = [];
  const smoothingMax = 10;
  let chartObject = null;
  let chartData = null;
  let chartOptions = buildChartOptions();
  let smoothingFactor = 0;
  let viewAll = false;
  let usePercentage = false;
  let lastSelectedParam = null;
  let spsaData = null;
  let hasRendered = false;
  let refreshQueued = false;

  function gaussianKernelRegression(values, bandwidth) {
    if (!bandwidth) {
      return values;
    }

    const smoothedValues = [];
    for (let i = 0; i < values.length; i += 1) {
      let weightedSum = 0;
      let weightTotal = 0;
      for (let j = 0; j < values.length; j += 1) {
        const distance = (i - j) / bandwidth;
        const weight = Math.exp(-0.5 * distance * distance);
        weightTotal += weight;
        weightedSum += weight * values[j];
      }
      smoothedValues.push(weightedSum / weightTotal);
    }
    return smoothedValues;
  }

  function redraw() {
    chartOptions.animation = {};
    const view = new google.visualization.DataView(chartData);
    view.setColumns(columns);
    chartObject.draw(view, chartOptions);
  }

  function updateColumnVisibility(col, visibility) {
    if (col === 0) {
      columns[0] = 0;
      return;
    }

    if (!visibility) {
      columns[col] = {
        label: chartData.getColumnLabel(col),
        type: chartData.getColumnType(col),
        calc() {
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

  function buildData(nextSmoothingFactor) {
    const spsaParams = spsaData.params;
    const spsaHistory = spsaData.param_history;
    const numIter = asFiniteNumber(spsaData.num_iter, 0);
    const iterValue = asFiniteNumber(spsaData.iter, 0);
    const spsaIterRatio =
      numIter > 0 ? Math.min(Math.max(iterValue / numIter, 0), 1) : 0;

    if (!dataCache[0]) {
      const dt0 = new google.visualization.DataTable();
      dt0.addColumn("number", "Iteration");
      for (let i = 0; i < spsaParams.length; i += 1) {
        dt0.addColumn("number", spsaParams[i].name);
      }

      const lastValues = spsaParams.map((param) =>
        asFiniteNumber(param.start, asFiniteNumber(param.theta, 0)),
      );
      const unsmoothedData = [];
      for (let i = 0; i <= spsaHistory.length; i += 1) {
        const rowData = [
          spsaHistory.length > 0 ? (i / spsaHistory.length) * spsaIterRatio : 0,
        ];
        for (let j = 0; j < spsaParams.length; j += 1) {
          if (i === 0) {
            rowData.push(lastValues[j]);
            continue;
          }

          const nextValue = asFiniteNumber(
            spsaHistory[i - 1]?.[j]?.theta,
            lastValues[j],
          );
          rowData.push(nextValue);
          lastValues[j] = nextValue;
        }
        unsmoothedData.push(rowData);
      }
      dt0.addRows(unsmoothedData);
      dataCache[0] = dt0;
    }

    if (!dataCache[nextSmoothingFactor] && nextSmoothingFactor !== 0) {
      const dt0 = dataCache[0];
      const dt = new google.visualization.DataTable();
      dt.addColumn("number", "Iteration");
      for (let i = 0; i < spsaParams.length; i += 1) {
        dt.addColumn("number", spsaParams[i].name);
      }

      const bandwidth =
        spsaHistory.length > 0 && spsaIterRatio > 0
          ? 2 *
            nextSmoothingFactor *
            (spsaHistory.length / (spsaIterRatio * 100))
          : 0;
      const rawArrays = [];
      for (let col = 1; col < dt0.getNumberOfColumns(); col += 1) {
        const colData = [];
        for (let row = 0; row < dt0.getNumberOfRows(); row += 1) {
          colData.push(dt0.getValue(row, col));
        }
        rawArrays.push(colData);
      }

      const smoothedArrays = rawArrays.map((values) =>
        gaussianKernelRegression(values, bandwidth),
      );
      const newData = [];
      for (let row = 0; row < dt0.getNumberOfRows(); row += 1) {
        const rowArray = [dt0.getValue(row, 0)];
        for (let i = 0; i < smoothedArrays.length; i += 1) {
          rowArray.push(smoothedArrays[i][row]);
        }
        newData.push(rowArray);
      }
      dt.addRows(newData);
      dataCache[nextSmoothingFactor] = dt;
    }

    chartData = dataCache[nextSmoothingFactor];
    chartOptions.vAxis.format = usePercentage ? "percent" : "decimal";

    if (usePercentage) {
      const view = new google.visualization.DataView(chartData);
      view.setColumns([
        0,
        ...spsaParams.map((_, i) => ({
          calc: (dt, row) => {
            if (row === 0) {
              return 0;
            }
            const cValue = Number(spsaHistory[row - 1]?.[i]?.c);
            if (!Number.isFinite(cValue) || cValue === 0) {
              return null;
            }
            return (dt.getValue(row, i + 1) - dt.getValue(0, i + 1)) / cValue;
          },
          type: "number",
          label: spsaParams[i].name,
        })),
      ]);
      chartData = view;
    }

    columns.length = 0;
    for (let i = 0; i < chartData.getNumberOfColumns(); i += 1) {
      columns.push(i);
    }

    if (
      !viewAll &&
      lastSelectedParam != null &&
      lastSelectedParam < chartData.getNumberOfColumns()
    ) {
      for (let i = 1; i < chartData.getNumberOfColumns(); i += 1) {
        updateColumnVisibility(i, i === lastSelectedParam);
      }
    }

    redraw();
  }

  function rebuildDropdown(dropdown) {
    dropdown.replaceChildren();
    for (let j = 0; j < spsaData.params.length; j += 1) {
      const dropdownItem = document.createElement("li");
      const anchorItem = document.createElement("a");
      anchorItem.className = "dropdown-item";
      if (!viewAll && lastSelectedParam === j + 1) {
        anchorItem.classList.add("active");
      }
      anchorItem.href = "javascript:";
      anchorItem.dataset.paramId = j + 1;
      anchorItem.append(spsaData.params[j].name);
      dropdownItem.append(anchorItem);
      dropdown.append(dropdownItem);
    }
  }

  function renderSPSA(nextData) {
    const historyPlot = document.getElementById("spsa_history_plot");
    const chartToolbar = document.getElementById("chart_toolbar");
    const dropdown = document.getElementById("dropdown_individual");
    const percentageToggle = document.getElementById("spsa_percentage");
    if (!historyPlot || !chartToolbar || !dropdown || !percentageToggle) {
      return;
    }

    spsaData = {
      ...nextData,
      params: Array.isArray(nextData.params) ? nextData.params : [],
      param_history: Array.isArray(nextData.param_history)
        ? nextData.param_history
        : [],
    };
    dataCache.length = 0;
    chartData = null;
    columns.length = 0;
    chartOptions = buildChartOptions();
    usePercentage = percentageToggle.checked;

    if (!chartObject) {
      chartObject = new google.visualization.LineChart(historyPlot);
      google.visualization.events.addListener(chartObject, "select", () => {
        const selection = chartObject.getSelection();
        if (selection.length > 0 && selection[0].row == null) {
          const col = selection[0].column;
          updateColumnVisibility(col, columns[col] !== col);
          redraw();
        }
        viewAll = false;
      });
    }

    if (!spsaData.param_history.length) {
      chartToolbar.style.display = "none";
      showSPSAAlert(
        spsaData.params.length >= 1000
          ? "Too many tuning parameters to generate plot."
          : "Not enough data to generate plot.",
      );
      hasRendered = true;
      return;
    }

    if (
      lastSelectedParam != null &&
      lastSelectedParam > spsaData.params.length
    ) {
      lastSelectedParam = null;
      viewAll = true;
    }

    rebuildDropdown(dropdown);
    buildData(smoothingFactor);
    chartToolbar.style.display = "";
    hasRendered = true;
  }

  async function refreshSPSA({ showLoader = false } = {}) {
    const nextData = readSPSAData();
    if (!nextData) {
      return;
    }

    if (showLoader && !hasRendered) {
      setLoaderVisible(true);
    }

    await waitForGoogleCharts();
    renderSPSA(nextData);
    setLoaderVisible(false);
  }

  function scheduleRefresh() {
    if (refreshQueued) {
      return;
    }

    refreshQueued = true;
    requestAnimationFrame(() => {
      refreshQueued = false;
      void refreshSPSA();
    });
  }

  await DOMContentLoaded();

  const root = getSPSARoot();
  const dropdown = document.getElementById("dropdown_individual");
  const smoothPlus = document.getElementById("btn_smooth_plus");
  const smoothMinus = document.getElementById("btn_smooth_minus");
  const viewAllButton = document.getElementById("btn_view_all");
  const percentageToggle = document.getElementById("spsa_percentage");

  if (
    !root ||
    !dropdown ||
    !smoothPlus ||
    !smoothMinus ||
    !viewAllButton ||
    !percentageToggle
  ) {
    return;
  }

  dropdown.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || !event.target.matches("a")) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const paramId = Number(event.target.dataset.paramId);
    if (!Number.isInteger(paramId) || !chartData) {
      return;
    }

    const currentScroll = dropdown.scrollTop;
    Array.from(dropdown.querySelectorAll("a.active")).forEach((element) => {
      element.classList.remove("active");
    });
    event.target.classList.add("active");
    lastSelectedParam = paramId;

    for (let i = 1; i < chartData.getNumberOfColumns(); i += 1) {
      updateColumnVisibility(i, i === paramId);
    }

    viewAll = false;
    redraw();
    dropdown.scrollTop = currentScroll;
  });

  smoothPlus.addEventListener("click", () => {
    if (smoothingFactor < smoothingMax && spsaData) {
      smoothingFactor += 1;
      buildData(smoothingFactor);
    }
  });

  smoothMinus.addEventListener("click", () => {
    if (smoothingFactor > 0 && spsaData) {
      smoothingFactor -= 1;
      buildData(smoothingFactor);
    }
  });

  viewAllButton.addEventListener("click", () => {
    if (viewAll || !chartData) {
      return;
    }

    viewAll = true;
    lastSelectedParam = null;
    Array.from(dropdown.querySelectorAll("a.active")).forEach((element) => {
      element.classList.remove("active");
    });
    for (let i = 0; i < chartData.getNumberOfColumns(); i += 1) {
      updateColumnVisibility(i, true);
    }
    redraw();
  });

  percentageToggle.addEventListener("change", () => {
    usePercentage = percentageToggle.checked;
    if (spsaData) {
      buildData(smoothingFactor);
    }
  });

  queueSPSARefresh = scheduleRefresh;
  if (!spsaOobListenerRegistered) {
    spsaOobListenerRegistered = true;
    document.body.addEventListener("htmx:oobAfterSwap", (event) => {
      const target = event?.detail?.target;
      if (target instanceof Element && target.id.startsWith("spsa-data-")) {
        queueSPSARefresh?.();
      }
    });
  }

  try {
    await refreshSPSA({ showLoader: true });
  } catch (error) {
    console.warn("Unable to render SPSA chart", error);
    setLoaderVisible(false);
    if (!hasRendered) {
      const chartToolbar = document.getElementById("chart_toolbar");
      if (chartToolbar) {
        chartToolbar.style.display = "none";
      }
      showSPSAAlert("Unable to render SPSA graph.");
    }
  }
}
