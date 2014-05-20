<%inherit file="base.mak"/>

<%namespace name="base" file="base.mak"/>

<!--FIXME: add if condition to avoid running the following scripts if this test is not spsa -->

<!--FIXME: don't run this script to make a plot if spsa test is not approved or started -->

<script type="text/javascript" src="https://www.google.com/jsapi"></script>

<script>
(function (w) {
  var spsa_history, spsa_params, i, j, chart, data, googleformat, param_columns, visible_line;
  var columns = [];
  var series = {};

  var chartcolors = ["#3366cc", "#dc3912", "#ff9900", "#109618", "#990099", "#0099c6", "#dd4477", "#66aa00", "#b82e2e", "#316395", "#994499", "#22aa99", "#aaaa11", "#6633cc", "#e67300", "#8b0707", "#651067", "#329262", "#5574a6", "#3b3eac", "#b77322", "#16d620", "#b91383", "#f4359e", "#9c5935", "#a9c413", "#2a778d", "#668d1c", "#bea413", "#0c5922", "#743411"];

  var options = {
    'curveType': 'function',
    'chartArea': {
      'width': '800',
      'height': '450',
      'left': 40,
      'top': 20
    },
    'width': 1000,
    'height': 500,
    'legend': {
      'position': 'right'
    },
    'colors': chartcolors.slice(0)
  };

  google.load('visualization', '1.0', {'packages': ['corechart']});
  google.setOnLoadCallback(drawChart);

  function drawChart() {
    if (!spsa_history || spsa_history.length < 1) return;

    data = google.visualization.arrayToDataTable(googleformat);

    for (var i = 0; i < data.getNumberOfColumns(); i++) {
      columns.push(i);
      if (i > 0) {
        series[i - 1] = {};
      }
    }

    chart = new google.visualization.LineChart(document.getElementById('div_spsa_history_plot'));
    google.visualization.events.addListener(chart, 'select', selectHandler);

    chart.draw(data, options);
  }

  function selectHandler(e) {
    var sel = chart.getSelection();
    if (sel.length > 0) {
      if (sel[0].row == null) {
        var col = sel[0].column;
        if (columns[col] == col) {
          // hide the data series
          columns[col] = {
            label: data.getColumnLabel(col),
            type: data.getColumnType(col),
            calc: function () {
              return null;
            }
          };
          // grey out the legend entry
          visible_line[col - 1] = false;
        } else {
          // show the data series
          columns[col] = col;
          visible_line[col - 1] = true;
        }

        options.colors = chartcolors.slice(0);

        for (i = 0; i < columns.length; i++) {
          if (visible_line[i] == false) {
            options.colors[i] = '#CCCCCC';
          }
        }

        var view = new google.visualization.DataView(data);
        view.setColumns(columns);
        chart.draw(view, options);
      }
    }
  }

  $(w).ready(function () {
    $.get('${run_args[0][1]}/spsa_history', function (d) {
      spsa_params = d.params;

      googleformat = [];
      param_columns = [''];
      visible_line = [];

      for (i = 0; i < spsa_params.length; i++) {
        param_columns.push(spsa_params[i].name);
        visible_line.push(true);
      }
      googleformat.push(param_columns);

      spsa_history = d.param_history;
      if (!spsa_history || spsa_history.length < 1) return;

      for (i = 0; i < spsa_history.length; i++) {
        var d = [i];
        for (j = 0; j < spsa_params.length; j++) {
          d.push(spsa_history[i][j].theta);
        }
        googleformat.push(d);
      }

    });
  });
})(window);
</script>

<h3>${run['args']['new_tag']} vs ${run['args']['base_tag']} ${base.diff_url(run)}</h3>

<div class="row-fluid">
<div class="span4">
<%include file="elo_results.mak" args="run=run" />
</div>
</div>

<div class="row-fluid">

<div class="span8">
  <h4>Details</h4>

	<%! import markupsafe %>

  <table class="table table-condensed">
  %for arg in run_args:
    %if len(arg[2]) == 0:
		<tr><td>${arg[0]}</td><td>${str(markupsafe.Markup(arg[1])).replace('\n', '<br>') | n}</td></tr>
    %else:
    <tr><td>${arg[0]}</td><td><a href="${arg[2]}" target="_blank">${arg[1]}</a></td></tr>
    %endif
  %endfor
  </table>
</div>

<div class="span4">
  <h4>Actions</h4>
%if not run['finished']:
  <form action="/tests/stop" method="POST" style="display:inline">
    <input type="hidden" name="run-id" value="${run['_id']}">
    <button type="submit" class="btn btn-danger">
      Stop
    </button>
  </form>
%if not run.get('approved', False):
  <span>
    <a href="https://github.com/mcostalba/Stockfish/compare/master...${run['args']['resolved_base'][:7]}" target="_blank">Master diff</a>
    <form action="/tests/approve" method="POST" style="display:inline">
      <input type="hidden" name="run-id" value="${run['_id']}">
      <button type="submit" class="btn btn-success">
        Approve
      </button>
    </form>
  </span>
%endif
%else:
  <form action="/tests/purge" method="POST" style="display:inline">
    <input type="hidden" name="run-id" value="${run['_id']}">
    <button type="submit" class="btn btn-danger">
      Purge
    </button>
  </form>
%endif
  <a href="/tests/run?id=${run['_id']}">
    <button class="btn">Reschedule</button>
  </a>

  <hr>

  <form class="form" action="/tests/modify" method="POST">
    <label class="control-label">Number of games:</label>
    <input name="num-games" value="${run['args']['num_games']}">

    <label class="control-label">Adjust priority (higher is more urgent):</label>
    <input name="priority" value="${run['args']['priority']}">

    <input type="hidden" name="run" value="${run['_id']}" />
    <button type="submit" class="btn btn-primary">Modify</button>
  </form>

  <hr>

  %if 'spsa' not in run['args']:
  <h4>Stats</h4>
  <table class="table table-condensed">
    <tr><td>chi^2</td><td>${'%.2f' % (chi2['chi2'])}</td></tr>
    <tr><td>dof</td><td>${chi2['dof']}</td></tr>
    <tr><td>p-value</td><td>${'%.2f' % (chi2['p'] * 100)}%</td></tr>
  </table>
	%endif

  
</div>

</div>


<!--FIXME: add if condition around this div to avoid creating it if this test is not spsa -->

<div id="div_spsa_history_plot"></div>

<!-- -->

<h3>Tasks</h3>
<table class='table table-striped table-condensed'>
 <thead>
  <tr>
   <th>Idx</th>
   <th>Worker</th>
   <th>Last Updated</th>
   <th>Played</th>
   <th>Wins</th>
   <th>Losses</th>
   <th>Draws</th>
   <th>Crashes</th>
   <th>Time</th>

   %if 'spsa' not in run['args']:
   <th>Residual</th>
	 %endif
  </tr>
 </thead>
 <tbody>
  %for idx, task in enumerate(run['tasks']):
  <%
    stats = task.get('stats', {})
    if 'stats' in task:
      total = stats['wins'] + stats['losses'] + stats['draws']
    else:
      continue

    if task['active'] and task['pending']:
      active_style = 'info'
    elif task['active'] and not task['pending']:
      active_style = 'error'
    else:
      active_style = ''
  %>
  <tr class="${active_style}">
   <td>${idx}</td>
   <td>${task['worker_key']}</td>
   <td>${str(task.get('last_updated', '-')).split('.')[0]}</td>
   <td>${total} / ${task['num_games']}</td>
   <td>${stats.get('wins', '-')}</td>
   <td>${stats.get('losses', '-')}</td>
   <td>${stats.get('draws', '-')}</td>
   <td>${stats.get('crashes', '-')}</td>
   <td>${stats.get('time_losses', '-')}</td>

   %if 'spsa' not in run['args']:
   <td style="background-color:${task['residual_color']}">${'%.3f' % (task['residual'])}</td>
	 %endif
  </tr>
  %endfor
 </tbody>
</table>
