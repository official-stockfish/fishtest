(function () {
  let raw = [],
    chart_object,
    chart_data,
    data_cache = [],
    smoothing_factor = 0,
    smoothing_max = 20,
    columns = [],
    viewAll = false;

  const chart_colors = [
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

  const chart_invisible_color = "#ccc";
  const chart_text_style = { color: "#888" };
  const gridlines_style = { color: "#666" };
  const minor_gridlines_style = { color: "#ccc" };

  let chart_options = {
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
      textStyle: chart_text_style,
      gridlines: gridlines_style,
      minorGridlines: minor_gridlines_style,
    },
    vAxis: {
      viewWindowMode: "maximized",
      textStyle: chart_text_style,
      gridlines: gridlines_style,
      minorGridlines: minor_gridlines_style,
    },
    legend: {
      position: "right",
      textStyle: chart_text_style,
    },
    colors: chart_colors.slice(0),
    seriesType: "line",
  };

  function gaussian_kernel_regression(y, h) {
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

  function smooth_data(b) {
    const spsa_params = spsa_data.params;
    const spsa_history = spsa_data.param_history;
    const spsa_iter_ratio = Math.min(spsa_data.iter / spsa_data.num_iter, 1);

    //cache the raw data
    if (!raw.length) {
      for (let j = 0; j < spsa_params.length; j++) raw.push([]);
      for (let i = 0; i < spsa_history.length; i++) {
        for (let j = 0; j < spsa_params.length; j++) {
          raw[j].push(spsa_history[i][j].theta);
        }
      }
    }
    //cache data table to avoid recomputing the smoothed graph
    if (!data_cache[b]) {
      let dt = new google.visualization.DataTable();
      dt.addColumn("number", "Iteration");
      for (let i = 0; i < spsa_params.length; i++) {
        dt.addColumn("number", spsa_params[i].name);
      }
      // adjust the bandwidth for tests with samples != 101
      const h = b * ((spsa_history.length - 1) / (spsa_iter_ratio * 100));
      let d = [];
      for (let j = 0; j < spsa_params.length; j++) {
        d.push(gaussian_kernel_regression(raw[j], h));
      }
      let googleformat = [];
      for (let i = 0; i < spsa_history.length; i++) {
        let c = [(i / (spsa_history.length - 1)) * spsa_iter_ratio];
        for (let j = 0; j < spsa_params.length; j++) {
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
    chart_options.animation = animate ? { duration: 800, easing: "out" } : {};
    let view = new google.visualization.DataView(chart_data);
    view.setColumns(columns);
    chart_object.draw(view, chart_options);
  }

  function update_column_visibility(col, visibility) {
    if (!visibility) {
      columns[col] = {
        label: chart_data.getColumnLabel(col),
        type: chart_data.getColumnType(col),
        calc: function () {
          return null;
        },
      };
      chart_options.colors[col - 1] = chart_invisible_color;
    } else {
      columns[col] = col;
      chart_options.colors[col - 1] =
        chart_colors[(col - 1) % chart_colors.length];
    }
  }

  $(document).ready(function () {
    $("#div_spsa_preload").fadeIn();

    //load google library
    google.charts.load("current", {
      packages: ["corechart"],
      callback: function () {
        const spsa_params = spsa_data.params;
        const spsa_history = spsa_data.param_history;
        const spsa_iter_ratio = Math.min(
          spsa_data.iter / spsa_data.num_iter,
          1
        );

        if (!spsa_history || spsa_history.length < 2) {
          $("#div_spsa_preload").hide();
          $("#div_spsa_history_plot")
            .html("<div class='alert alert-warning' role='alert'>Not enough data to generate plot.</div>");
          return;
        }

        for (let i = 0; i < smoothing_max; i++) data_cache.push(false);

        let googleformat = [];
        for (let i = 0; i < spsa_history.length; i++) {
          let d = [(i / (spsa_history.length - 1)) * spsa_iter_ratio];
          for (let j = 0; j < spsa_params.length; j++) {
            d.push(spsa_history[i][j].theta);
          }
          googleformat.push(d);
        }

        chart_data = new google.visualization.DataTable();

        chart_data.addColumn("number", "Iteration");
        for (let i = 0; i < spsa_params.length; i++) {
          chart_data.addColumn("number", spsa_params[i].name);
        }
        chart_data.addRows(googleformat);

        data_cache[0] = chart_data;
        chart_object = new google.visualization.LineChart(
          document.getElementById("div_spsa_history_plot")
        );
        chart_object.draw(chart_data, chart_options);

        $("#chart_toolbar").show();

        for (let i = 0; i < chart_data.getNumberOfColumns(); i++) {
          columns.push(i);
        }

        for (let j = 0; j < spsa_params.length; j++) {
          $("#dropdown_individual").append(
            '<li><a class="dropdown-item" href="javascript:" param_id="' +
              (j + 1) +
              '" >' +
              spsa_params[j].name +
              "</a></li>"
          );
        }

        $("#dropdown_individual")
          .find("a")
          .on("click", function () {
            let param_id = $(this).attr("param_id");

            for (let i = 1; i < chart_data.getNumberOfColumns(); i++) {
              update_column_visibility(i, i == param_id);
            }

            viewAll = false;
            redraw(false);
          });

        //show/hide functionality
        google.visualization.events.addListener(
          chart_object,
          "select",
          function (e) {
            let sel = chart_object.getSelection();
            if (sel.length > 0 && sel[0].row == null) {
              const col = sel[0].column;
              update_column_visibility(col, columns[col] != col);
              redraw(false);
            }
            viewAll = false;
          }
        );

        $("#div_spsa_preload").hide();

        $("#btn_smooth_plus").on("click", function () {
          if (smoothing_factor < smoothing_max) {
            smooth_data(++smoothing_factor);
          }
        });

        $("#btn_smooth_minus").on("click", function () {
          if (smoothing_factor > 0) {
            smooth_data(--smoothing_factor);
          }
        });

        $("#btn_view_all").on("click", function () {
          if (viewAll) return;
          viewAll = true;

          for (let i = 0; i < chart_data.getNumberOfColumns(); i++) {
            update_column_visibility(i, true);
          }

          redraw(false);
        });
      },
    });
  });
})();
