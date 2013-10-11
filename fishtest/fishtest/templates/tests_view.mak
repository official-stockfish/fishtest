<%inherit file="base.mak"/>

<%namespace name="base" file="base.mak"/>

<h3>${run['args']['new_tag']} vs ${run['args']['base_tag']} ${base.diff_url(run)}</h3>

<div class="row-fluid">
<div class="span4">
<%include file="elo_results.mak" args="run=run" />
</div>
</div>

<div class="row-fluid">

<div class="span8">
  <h4>Details</h4>

  <table class="table table-condensed">
  %for arg in run_args:
    %if len(arg[2]) == 0:
    <tr><td>${arg[0]}</td><td>${arg[1]}</td></tr>
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

  <h4>Stats</h4>
  <table class="table table-condensed">
    <tr><td>chi^2</td><td>${'%.2f' % (chi2['chi2'])}</td></tr>
    <tr><td>dof</td><td>${chi2['dof']}</td></tr>
    <tr><td>p-value</td><td>${'%.2f' % (chi2['p'] * 100)}%</td></tr>
  </table>
</div>

</div>

%if 'clop' in run['args']:
<%
  active_cnt  = sum([int(len(g['task_id'])  > 0) for g in run['games']])
  pending_cnt = sum([int(len(g['task_id']) == 0) for g in run['games']])
  games_per_task = {}
%>
<h3>Games - ${active_cnt} active  ${pending_cnt} pending</h3>
<table class='table table-striped table-condensed'>
 <thead>
  <tr>
   <th>Idx</th>
   <th>Seed</th>
   <th>White</th>
   <th>Parameters</th>
   <th>Result</th>
  </tr>
 </thead>
 <tbody>
  %for game in run['games']:
  <%
    idx = game['task_id'] if len(game['task_id']) > 0 else 'pending'
    parameters = ['%s=%s'%(x[0], x[1]) for x in game['params']]

    if idx != 'pending':
      active_style = 'info'
    elif len(game['result']) > 0:
        active_style = 'error'
    else:
      active_style = ''

    if 'clop' in run['args']:
      games_per_task[str(idx)] = games_per_task.get(str(idx), 0) + 1
  %>
  <tr class="${active_style}">
   <td>${idx}</td>
   <td>${game['seed']}</td>
   <td>${game['white']}</td>
   <td>${',  '.join(parameters)}</td>
   <td>${game['result']}</td>
  </tr>
  %endfor
 </tbody>
</table>
%endif

<h3>Tasks</h3>
<table class='table table-striped table-condensed'>
 <thead>
  <tr>
   <th>Idx</th>
   <th>Worker</th>
   <th>Last Updated</th>
   <th>Played</th>
   %if 'clop' in run['args']:
   <th>Playing now</th>
   %else:
   <th>Wins</th>
   <th>Losses</th>
   <th>Draws</th>
   %endif
   <th>Crashes</th>
   <th>Time</th>
   <th>Residual</th>
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
   %if 'clop' in run['args']:
   <td>${str(games_per_task.get(str(idx), '-'))}</td>
   %else:
   <td>${stats.get('wins', '-')}</td>
   <td>${stats.get('losses', '-')}</td>
   <td>${stats.get('draws', '-')}</td>
   %endif
   <td>${stats.get('crashes', '-')}</td>
   <td>${stats.get('time_losses', '-')}</td>
   <td style="background-color:${task['residual_color']}">${'%.3f' % (task['residual'])}</td>
  </tr>
  %endfor
 </tbody>
</table>
