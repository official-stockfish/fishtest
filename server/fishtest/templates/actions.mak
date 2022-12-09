<%inherit file="base.mak"/>

<%
  import datetime
%>

<h2>Events Log</h2>

<script>
  document.title = 'Events Log | Stockfish Testing';
</script>

<form class="row mb-3">
  <div class="col-12 col-md-auto mb-3">
    <label for="restrict" class="form-label">Show only</label>
    <select id="restrict" class="form-select" name="action">
      <option value="">All</option>
      <option value="new_run">New Run</option>
      <option value="approve_run">Approve Run</option>
      <option value="modify_run">Modify Run</option>
      <option value="stop_run">Stop Run</option>
      <option value="delete_run">Delete Run</option>
      <option value="purge_run">Purge Run</option>
      <option value="block_user">Block/Unblock User</option>
      <option value="upload_nn">Upload NN file</option>
      <option value="failed_task">Failed Tasks</option>
      <option value="dead_task" class="grayedoutoption">Dead Tasks</option>
      <option value="update_stats" class="grayedoutoption">System Events</option>
    </select>
  </div>

  <div class="col-12 col-md-auto mb-3">
    <label for="user" class="form-label">From user</label>
    <input
      id="user"
      class="form-control"
      autocomplete="off"
      placeholder="Search by username"
      type="text"
      name="user"
      list="users-list"
      value="${request.GET.get('user') if request.GET.get('user') is not None else ''}"
    />
    <datalist id="users-list">
      % for user in request.userdb.get_users():
        <option value="${user["username"]}">${user["username"]}</option>
      % endfor
    </datalist>
  </div>

  <div class="col-12 col-md-auto mb-3 d-flex align-items-end">
    <button type="submit" class="btn btn-success w-100">Search</button>
  </div>
</form>

<%include file="pagination.mak" args="pages=pages"/>

<div class="table-responsive-lg">
  <table class="table table-striped table-sm">
    <thead class="sticky-top">
      <tr>
        <th>Time</th>
        <th>Event</th>
        <th>Source</th>
        <th>Target</th>
        <th>Comment</th>
      </tr>
    </thead>
    <tbody>
      % for action in actions:
          <tr>
            ## Dates in mongodb have millisecond precision. So they fit comfortably in a float without precision loss.
            <td><a href=/actions?max_actions=1${"&action="+action['action'] if action_param else ""}${"&user="+action['username'] if username_param else ""}&before=${action['time'].replace(tzinfo=datetime.timezone.utc).timestamp()}>
             ${action['time'].strftime(r"%y&#8209;%m&#8209;%d %H:%M:%S")|n}</a></td>
            <td>${action['action']}</td>
	    <%
               if 'worker' in action:
                 agent = action['worker']
               else:
                 agent = action['username']
	    %>
            % if approver and 'fishtest.' not in action['username']:
                <td><a href="/user/${action['username']}">${agent|n}</a></td>
            % else:
                <td>${agent|n}</td>
            % endif
            % if 'nn' in action:
                <td><a href=/api/nn/${action['nn']}>${action['nn'].replace('-', '&#8209;')|n}</a></td>
            % elif 'run' in action:
                <td><a href="/tests/view/${action['run_id']}">${action['run'][:23] + \
                            ("/{}".format(action["task_id"]) if "task_id" in action else "")}</a></td>
            % elif approver:
                <td><a href="/user/${action['user']}">${action['user']}</a></td>
            % else:
                <td>${action['user']}</td>
            % endif
            <td style="word-break: break-all">${action.get('message','?')}</td>
          </tr>
      % endfor
    </tbody>
  </table>
</div>

<%include file="pagination.mak" args="pages=pages"/>

<script>
  document.querySelector('#restrict').value = ('${request.GET.get("action") if request.GET.get("action") != None else ''}');
</script>
