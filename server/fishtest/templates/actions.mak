<%inherit file="base.mak"/>

<%!
  import datetime
%>

<h2>Events Log</h2>

<script>
  document.title = "Events Log | Stockfish Testing";
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
      <option value="finished_run">Finished Runs</option>
      <option value="block_user">Block/Unblock User</option>
      <option value="block_worker">Block/Unblock Worker</option>
      <option value="accept_user">Accept User</option>
      <option value="upload_nn">Upload NN file</option>
      <option value="failed_task">Failed Tasks</option>
      <option value="crash_or_time">Crashes or Time losses</option>
      <option value="log_message">Log Messages</option>
      <option value="dead_task" class="grayedoutoption">Dead Tasks</option>
      <option value="system_event" class="grayedoutoption">System Events</option>
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
      value="${username_param}"
    >
    <datalist id="users-list">
      % for user in request.userdb.get_users():
        <option value="${user["username"]}">${user["username"]}</option>
      % endfor
    </datalist>
  </div>

  <div class="col-12 col-md-auto mb-3">
    <label for="text" class="form-label">Free text search</label>
    <i
      class="fa-solid fa-circle-info"
      role="button"
      data-bs-toggle="modal"
      data-bs-target="#autoselect-modal"
    ></i>
    <div
      class="modal fade"
      id="autoselect-modal"
      tabindex="-1"
      aria-hidden="true"
    >
      <div class="modal-dialog modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Free text search information</h5>
            <button
              type="button"
              class="btn-close"
              data-bs-dismiss="modal"
              aria-label="Close"
            ></button>
          </div>
          <div class="modal-body text-break">
            This will perform a case insensitive text search on the fields event
            name, user name, worker name, target user, network name, branch name
            and comment. One can only search for a list of full words, i.e.
            strings bounded by delimiters. For example the worker name
            <i>fishtestfan-128cores-abcdefgh-uvwx</i> matches <i>abcdefgh</i> but
            not <i>abcde</i>. To force a word or a combination of words to be
            included in the result, use quotes like in <i>&quot;dog cat&quot;</i>.
            To exclude a word, precede it with a minus sign like in
            <i>dog &minus;cat</i>. For more information see
            <a
              href="https://www.mongodb.com/docs/manual/reference/operator/query/text/#mongodb-query-op.-text"
            >
              https://www.mongodb.com/docs/manual/reference/operator/query/text/#mongodb-query-op.-text
            </a>.
          </div>
        </div>
      </div>
    </div>

    <input
      id="text"
      class="form-control"
      placeholder="Enter some text"
      type="text"
      name="text"
      value="${text_param}"
    >
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
      % for idx, action in enumerate(actions):
        <tr>
          ## Dates in mongodb have millisecond precision. So they fit comfortably in a float without precision loss.
          <td>
            <a
              href="/actions?max_actions=1&amp;action=${action_param}&amp;user=${username_param|u,n}&amp;text=${text_param|u,n}&amp;before=${action['time']}&amp;run_id=${run_id_param}"
            >
                 ${datetime.datetime.utcfromtimestamp(action['time']).strftime(r"%y&#8209;%m&#8209;%d %H:%M:%S")|n}
            </a>
          </td>
          <td>${action['action']}</td>
          <%
            if 'worker' in action and action['action'] != 'block_worker':
              agent = action['worker']
              short_agent = "-".join(agent.split("-")[0:3])
              agent_link = "/workers/"+short_agent
            else:
              agent = action['username']
              agent_link = "/user/"+agent
          %>
          % if action['action'] in ('system_event', 'log_message'):
            <td>${action['username']}</td>
          % else:
            <td><a href="${agent_link|n}">${agent|n}</a></td>
          % endif
          % if 'nn' in action:
            <td><a href=/api/nn/${action['nn']}>${action['nn'].replace('-', '&#8209;')|n}</a></td>
          % elif 'run' in action and 'run_id' in action:
            <td><a href="/tests/view/${action['run_id']}${"?show_task={}".format(action["task_id"]) if "task_id" in action else ""}">${action['run']}${("/{}".format(action["task_id"]) if "task_id" in action else "")}</a></td>
          % elif approver and 'user' in action:
            <td><a href="/user/${action['user']}">${action['user']}</a></td>
	  % elif action['action'] == 'block_worker':
            <td><a href="/workers/${action['worker']}">${action['worker']}</a></td>
          % else:
            <td>${action.get('user','')}</td>
          % endif
          <td class="text-break">${action.get('message','')}</td>
        </tr>
      % endfor
      % if "idx" not in locals():
        <tr>
          <td colspan=20>No actions available</td>
        </tr>
      % endif
    </tbody>
  </table>
</div>

<%include file="pagination.mak" args="pages=pages"/>

<script>
  document.getElementById('restrict').value =
    ('${request.GET.get("action") if request.GET.get("action") != None else ''}');
</script>
