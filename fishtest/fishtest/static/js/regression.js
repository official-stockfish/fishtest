(function() {
  var current_jl_testid;

  function draw_fishtest() {
    fishtest_data.sort(function(a, b) {
      var d1 = new Date(a.date),
        d2 = new Date(b.date);
      if (d1.getTime() > d2.getTime()) {
        return 1
      } else {
        return -1
      }
    });

    var fishtest_datatable = new google.visualization.DataTable();
    fishtest_datatable.addColumn('string', 'commit');
    fishtest_datatable.addColumn('number', 'elo');
    fishtest_datatable.addColumn({
      id: 'eloplus',
      type: 'number',
      role: 'interval'
    });
    fishtest_datatable.addColumn({
      id: 'elominus',
      type: 'number',
      role: 'interval'
    });

    for (var i = 0; i < fishtest_data.length; i++) {
      fishtest_datatable.addRow([fishtest_data[i].commit,
        parseFloat(fishtest_data[i].elo),
        parseFloat(fishtest_data[i].elo) + parseFloat(fishtest_data[i].error),
        parseFloat(fishtest_data[i].elo) - parseFloat(fishtest_data[i].error)
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
    fishtest_graph.draw(fishtest_datatable, options_lines);

    google.visualization.events.addListener(fishtest_graph, 'select', function(e) {
      if (fishtest_graph.getSelection()[0]) {
        window.open('tests/view/' + fishtest_data[fishtest_graph.getSelection()[0]['row']].link, '_blank');
      }
    });
  }

  function draw_jl_tests(test_id) {
    var data = jl_data[test_id].data;

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
    });

    google.visualization.events.addListener(graph, 'select', function(e) {
      if (graph.getSelection()[0]) {
        window.open('https://github.com/official-stockfish/Stockfish/commit/' + data[graph.getSelection()[0]['row']].sha, '_blank');
      }
    });

    current_jl_testid = test_id;
    $("#btn_select_jl_test_caption").html(jl_data[test_id].description);
    $("#jl_games_count").html(jl_data[test_id].games)
  }

  $(document).ready(function() {
    //load google library
    google.load('visualization', '1.0', {
      packages: ['corechart'],
      callback: function() {
        draw_fishtest();
        draw_jl_tests(0);

        for (j = 0; j < jl_data.length; j++) {
          $("#dropdown_jl_tests").append("<li><a test_id=\"" + j + "\" >" + jl_data[j].description + "</a></li>");
        }

        $("#dropdown_jl_tests").find('a').on('click', function() {
          draw_jl_tests($(this).attr('test_id'));
        });

      }
    });
  });
})();
