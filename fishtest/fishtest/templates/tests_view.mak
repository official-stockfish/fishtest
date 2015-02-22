<%inherit file="base.mak"/>

<%namespace name="base" file="base.mak"/>

%if 'spsa' in run['args']:
<script type="text/javascript" src="https://www.google.com/jsapi"></script>
<script type="text/javascript" src="/js/gkr.js"></script>
<script>
var spsa_history_url = '${run_args[0][1]}/spsa_history';
</script>
<script type="text/javascript" src="/js/spsa.js"></script>
%endif

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
    <a href="https://github.com/official-stockfish/Stockfish/compare/master...${run['args']['resolved_base'][:7]}" target="_blank">Master diff</a>
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

%if 'spsa' in run['args']:
<div id="div_spsa_preload" style="background-image:url('/img/preload.gif'); width: 256px; height: 32px; display: none;">
<div style="height: 100%; width: 100%; text-align:center; padding-top: 5px;">
Loading graph...
</div></div>
<div id="div_spsa_error" style="display: none; border: 1px solid red; color: red; width: 400px; "></div>
<div id="chart_toolbar" style="display: none;">
Gaussian Kernel Smoother&nbsp;&nbsp;<div class="btn-group"><button id="btn_smooth_plus" class="btn">&nbsp;&nbsp;&nbsp;+&nbsp;&nbsp;&nbsp;</button>
<button id="btn_smooth_minus" class="btn">&nbsp;&nbsp;&nbsp;−&nbsp;&nbsp;&nbsp;</button>
</div>
<div class="btn-group">
<button id="btn_view_individual" type="button" class="btn btn-default dropdown-toggle" data-toggle="dropdown">
    View Individual Parameter<span class="caret"></span>
  </button>
  <ul class="dropdown-menu" role="menu" id="dropdown_individual"></ul>
</div>
<button id="btn_view_all" class="btn">View All</button>
</div>
<div id="div_spsa_history_plot"></div>
%endif

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
