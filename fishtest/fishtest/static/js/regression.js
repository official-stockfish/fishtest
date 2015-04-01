(function() {
  var current_jl_testid, fishtest_data, jl_data;

  function draw_fishtest() {
    var data = !fishtest_data || fishtest_data.length < 1 ? [] : fishtest_data;

    data.sort(function(a, b) {
      var d1 = new Date(a.date_committed),
        d2 = new Date(b.date_committed);
      if (d1.getTime() > d2.getTime()) {
        return 1
      } else {
        return -1
      }
    });

    var datatable = new google.visualization.DataTable();
    datatable.addColumn('string', 'commit');
    datatable.addColumn('number', 'elo');
    datatable.addColumn({
      id: 'eloplus',
      type: 'number',
      role: 'interval'
    });
    datatable.addColumn({
      id: 'elominus',
      type: 'number',
      role: 'interval'
    });

    for (var i = 0; i < data.length; i++) {
      datatable.addRow([data[i].commit,
        parseFloat(data[i].elo),
        parseFloat(data[i].elo) + parseFloat(data[i].error),
        parseFloat(data[i].elo) - parseFloat(data[i].error)
      ]);
    }

    var options_lines = {
      lineWidth: 3,
      intervals: {
        style: 'bars'
      }, //, barWidth: 0.1
      legend: 'none',
      chartArea: {
        left: 50,
        top: 50,
        width: '90%',
        height: 450
      },
      hAxis: {
        slantedText: true,
        slantedTextAngle: 70
      }
    };

    var fishtest_graph = new google.visualization.LineChart(document.getElementById('fishtest_graph'));
    fishtest_graph.draw(datatable, options_lines);

    update_table_of_standings(fishtest_data, "fishtest", "#table_standings_fishtest");

    google.visualization.events.addListener(fishtest_graph, 'select', function(e) {
      if (fishtest_graph.getSelection()[0]) {
        window.open('tests/view/' + data[fishtest_graph.getSelection()[0]['row']].link, '_blank');
      }
    });
  }

  function draw_jl_tests(test_id) {
    var data = !jl_data || jl_data.length < 1 ? [] : jl_data[test_id].data;

    data.sort(function(a, b) {
      var d1 = new Date(a.date_committed),
        d2 = new Date(b.date_committed);
      if (d1.getTime() > d2.getTime()) {
        return 1
      } else {
        return -1
      }
    });

    var datatable = new google.visualization.DataTable();
    datatable.addColumn('string', 'commit');
    datatable.addColumn('number', 'elo');
    datatable.addColumn({
      id: 'eloplus',
      type: 'number',
      role: 'interval'
    });
    datatable.addColumn({
      id: 'elominus',
      type: 'number',
      role: 'interval'
    });

    for (var i = 0; i < data.length; i++) {
      datatable.addRow([data[i].sha.substring(0, 7),
        parseFloat(data[i].elo),
        parseFloat(data[i].elo) + parseFloat(data[i].error),
        parseFloat(data[i].elo) - parseFloat(data[i].error)
      ]);
    }

    var graph = new google.visualization.LineChart(document.getElementById('jl_graph'));

    graph.draw(datatable, {
      lineWidth: 2,
      intervals: {
        style: 'bars'
      },
      legend: 'none',
      chartArea: {
        left: 50,
        top: 50,
        width: '90%',
        height: 450
      },
      hAxis: {
        slantedText: true,
        slantedTextAngle: 70
      }
    });

    google.visualization.events.addListener(graph, 'select', function(e) {
      if (graph.getSelection()[0]) {
        window.open('https://github.com/official-stockfish/Stockfish/commit/' + data[graph.getSelection()[0]['row']].sha, '_blank');
      }
    });

    current_jl_testid = test_id;
    if (!jl_data || jl_data.length < 1) {
      $("#btn_select_jl_test_caption").html("No data available");
      $("#jl_games_count").html("N/A")
    } else {
      $("#btn_select_jl_test_caption").html(jl_data[test_id].description);
      $("#description").html(jl_data[test_id].long_description.replace(/\n/g, '<br/>'));

      var date = new Date(jl_data[test_id].date_saved);
      $("#date").html(date.toDateString())

      update_table_of_standings(jl_data[current_jl_testid].data, "jl", "#table_standings_jl");
    }
  }

  function elo_change_color(elo_difference) {

    function scaled_sigmoid(value) {
      return (200 / (1 + Math.exp(-1 * value / 8))) - 100
    }

    function makeGradientColor(color1, color2, percent) {
      var newColor = {};

      function makeChannel(a, b) {
        return (a + Math.round((b - a) * (percent / 100)));
      }

      function makeColorPiece(num) {
        num = Math.min(num, 255); // not more than 255
        num = Math.max(num, 0); // not less than 0
        var str = num.toString(16);
        if (str.length < 2) {
          str = "0" + str;
        }
        return (str);
      }

      newColor.r = makeChannel(color1.r, color2.r);
      newColor.g = makeChannel(color1.g, color2.g);
      newColor.b = makeChannel(color1.b, color2.b);
      newColor.cssColor = "#" +
        makeColorPiece(newColor.r) +
        makeColorPiece(newColor.g) +
        makeColorPiece(newColor.b);
      return (newColor);
    }

    var red = {
      r: 255,
      g: 106,
      b: 106
    }; //#FF6A6A
    var green = {
      r: 68,
      g: 235,
      b: 68
    }; //#44EB44
    var white = {
      r: 255,
      g: 255,
      b: 255
    };

    if (elo_difference > 0) {
      return makeGradientColor(white, green, scaled_sigmoid(elo_difference)).cssColor;
    } else {
      return makeGradientColor(white, red, -1 * scaled_sigmoid(elo_difference)).cssColor;
    }
  }

  function update_table_of_standings(data, test_type, element) {

    var github_commit_link = "https://github.com/official-stockfish/Stockfish/commit/";
    var github_compare_link = "https://github.com/official-stockfish/Stockfish/compare/";

    $(element + " tbody").html("");

    for (var i = 0; i < data.length; i++) {

      var commit_field = test_type == "fishtest" ? "commit" : "sha";

      var link = test_type != "fishtest" ? "" :
        "<td><a target=\"_blank\" href=\"tests\/view\/" + data[i].link + "\">details</a></td>";

      var date_committed = test_type == "fishtest" ? "" :
        "<td>" + (new Date(data[i].date_committed)).toString() + "</td>";

      var sha = "<td><a href=\"" +
        github_commit_link + data[i][commit_field] +
        "\" target=\"_blank\">" + data[i][commit_field].substring(0, 7) + "</a></td>"

      var elo = "<td>" + (Math.round(data[i].elo * 100) / 100) + " ± " +
        (Math.round(data[i].error * 100) / 100) + "</td>";

      var change = i == 0 ? "<td></td>" :
        "<td style=\"background-color: " +
        elo_change_color(data[i].elo - data[i - 1].elo) + "\">" +
        (Math.round((data[i].elo - data[i - 1].elo) * 100) / 100) + " </td>";

      var diff = i == 0 ? "<td></td>" :
        "<td><a class=\"btn btn-default\" href=\"" + github_compare_link +
        data[i - 1][commit_field] + "..." + data[i][commit_field] + "\" target=\"_blank\">diff</a></td>";

      $(element + " tbody").append("<tr>" + date_committed + sha + link + elo + change + diff + "</tr>");
    }
  }

  $(document).ready(function() {
    //load google library
    google.load('visualization', '1.0', {
      packages: ['corechart'],
      callback: function() {

        $.get('/regression/data/json', function(d) {
          data = $.parseJSON(d);
          fishtest_data = data.fishtest_regression_data;
          jl_data = data.jl_regression_data;

          //sort by date so that most recent runs are placed on top
          jl_data.sort(function(a, b) {
            var d1 = new Date(a.date_saved),
              d2 = new Date(b.date_saved);
            if (d1.getTime() < d2.getTime()) {
              return 1
            } else {
              return -1
            }
          })

          draw_fishtest();
          draw_jl_tests(0);

          if (!jl_data || jl_data.length < 1) return;

          for (j = 0; j < jl_data.length; j++) {
            $("#dropdown_jl_tests").append("<li><a test_id=\"" + j + "\" >" + jl_data[j].description + "</a></li>");
          }

          $("#dropdown_jl_tests").find('a').on('click', function() {
            draw_jl_tests($(this).attr('test_id'));
          });

        })
      }
    });
  });
})();