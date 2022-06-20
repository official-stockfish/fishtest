<%inherit file="base.mak"/>
<%
  import datetime
%>
<h2>Events Log</h2>
<p></p>
<script>
  document.title = 'Events Log | Stockfish Testing';

  function timestamp(){
    $('#before').val(Date.now()/1000);
    return true;
  }
</script>

<form onsubmit="timestamp();">
  Show only:
  <select id="restrict" name="action">
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
    <option class=grayedoutoption value="dead_task">Dead Tasks</option>
    <option class=grayedoutoption value="update_stats">System Events</option>
  </select>
  &nbsp;From user:
  <input id="user" type="text" name="user" class="submit_on_enter">
  <br/>
  <input type="hidden" id="before" name="before" value=-1>
  <input type="hidden" id="count" name="count" value=100>
<button type="submit" class="btn btn-success">Select</button>
</form>

<div class="table-responsive-lg">
  <table class="table table-striped table-sm">
    <thead class="sticky-top">
      <tr>
        <th>Time</th>
        <th>Username</th>
        <th>Run/User</th>
        <th>Event</th>
      </tr>
    </thead>
    <tbody>
      % for action in actions:
          <tr>
## Dates in mongodb have millisecond precision. So they fit comfortably in a float without precision loss.
            <td><a href=/actions?count=1&before=${action['time'].replace(tzinfo=datetime.timezone.utc).timestamp()}>
             ${action['time'].strftime(r"%y&#8209;%m&#8209;%d %H:%M:%S")|n}</a></td>
            % if approver and 'fishtest.' not in action['username']:
                <td><a href="/user/${action['username']}">${action['username']}</a></td>
            % else:
                <td>${action['username']}</td>
            % endif
            % if 'run' in action:
                <td><a href="/tests/view/${action['_id']}">${action['run'][:23]}</a></td>
            % elif approver:
                <td><a href="/user/${action['user']}">${action['user']}</a></td>
            % else:
                <td>${action.get('user','?')}</td>
            % endif
            <td>${action.get('description','?')}</td>
          </tr>
      % endfor
    </tbody>
  </table>
</div>
