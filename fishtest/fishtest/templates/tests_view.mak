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
    <tr><td>${arg[0]}</td><td>${arg[1]}</td></tr>
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
</div>

</div>

<h3>Tasks</h3>
<table class='table table-striped table-condensed'>
 <thead>
  <tr>
   <th>Idx</th>
   <th>Started</td>
   <th>Pending</th>
   <th>Worker</th>
   <th>Last Updated</th>
   <th>Games</th>
   <th>Played</th>
   <th>Wins</th>
   <th>Losses</th>
   <th>Draws</th>
   <th>Crashes</th>
  </tr>
 </thead>
 <tbody>
  %for idx, task in enumerate(run['tasks']):
  <tr>
   <%
     stats = task.get('stats', {})
     if 'stats' in task:
       total = stats['wins'] + stats['losses'] + stats['draws']
     else:
       total = '0'

     if 'worker_info' in task:
       machine_info = task['worker_info'].get('username', '') + '-' + str(task['worker_info']['concurrency']) + 'cores'
     else:
       machine_info = '-'

     if task['active'] and task['pending']:
       active_style = 'font-weight:bold'
     else:
       active_style = ''
   %>
   <td>${idx}</td>
   <td>${task['active']}</td>
   <td>${task['pending']}</td>
   <td><span style=${active_style}>${machine_info}</span></td>
   <td>${str(task.get('last_updated', '-')).split('.')[0]}</td>
   <td>${task['num_games']}</td>
   <td><span style=${active_style}>${total}</span></td>
   <td>${stats.get('wins', '-')}</td>
   <td>${stats.get('losses', '-')}</td>
   <td>${stats.get('draws', '-')}</td>
   <td>${stats.get('crashes', '-')}</td>
  </tr>
  %endfor
 </tbody>
</table>

