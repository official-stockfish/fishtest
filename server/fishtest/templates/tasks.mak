<%!
  from fishtest.util import worker_name
%>

% for idx, task in enumerate(run['tasks'] + run.get('bad_tasks', [])):
  <%
    if 'bad' in task and idx < len(run['tasks']):
      continue
    task_id = task.get('task_id', idx)
    stats = task.get('stats', {})
    if 'stats' in task:
      total = stats['wins'] + stats['losses'] + stats['draws']
    else:
      continue

    if task_id == show_task:
      active_style = 'highlight'
    elif task['active']:
      active_style = 'info'
    else:
      active_style = ''
  %>
  <tr class="${active_style}" id=task${task_id}>
    <td>
      <a href=${f"/api/pgn/{run['_id']}-{task_id:d}.pgn"}>${task_id}</a>
    </td>
    % if 'bad' in task:
      <td style="text-decoration:line-through; background-color:#ffebeb">
    % else:
      <td>
    % endif
    % if approver and task['worker_info']['username'] != "Unknown_worker":
      <a href="/workers/${worker_name(task['worker_info'], short=True)}">
        ${worker_name(task['worker_info'])}
      </a>
    % elif 'worker_info' in task:
      ${worker_name(task["worker_info"])}
    % else:
      -
    % endif
    </td>
    <td>
      <%
        gcc_version = ".".join([str(m) for m in task['worker_info']['gcc_version']])
        compiler = task['worker_info'].get('compiler', 'g++')
        python_version = ".".join([str(m) for m in task['worker_info']['python_version']])
        version = task['worker_info']['version']
        ARCH = task['worker_info']['ARCH']
      %>
      os: ${task['worker_info']['uname']};
      ram: ${task['worker_info']['max_memory']}MiB;
      compiler: ${compiler} ${gcc_version};
      python: ${python_version};
      worker: ${version};
      arch: ${ARCH}
    </td>
    <td>${str(task.get('last_updated', '-')).split('.')[0]}</td>
    <td>${f"{total:03d} / {task['num_games']:03d}"}</td>
    % if 'pentanomial' not in run['results']:
      <td>${stats.get('wins', '-')}</td>
      <td>${stats.get('losses', '-')}</td>
      <td>${stats.get('draws', '-')}</td>
    % else:
      <%
        p = stats.get('pentanomial', [0] * 5)
      %>
      <td>[${p[0]},&nbsp;${p[1]},&nbsp;${p[2]},&nbsp;${p[3]},&nbsp;${p[4]}]</td>
    % endif
    <td>${stats.get('crashes', '-')}</td>
    <td>${stats.get('time_losses', '-')}</td>

    % if 'spsa' not in run['args']:
      % if 'residual' in task and task['residual']!=float("inf"):
        <td style="background-color:${task['residual_color']}">
          ${f"{task['residual']:.3f}"}
        </td>
      % else:
        <td>-</td>
      % endif
    % endif
  </tr>
% endfor

% if len(run['tasks'] + run.get('bad_tasks', [])) == 0:
  <tr id="no-tasks">
    <td colspan=20>No tasks running</td>
  </tr>
% endif
