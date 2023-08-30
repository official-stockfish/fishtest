<%inherit file="base.mak"/>

<%!
  import datetime
  from fishtest.util import delta_date, diff_date
%>

<script>
  document.title = 'Workers | Stockfish Testing';
</script>
<style>
  div.worker td {vertical-align:top; padding-right: 15px;}
  div.worker th {padding-right: 15px;}
  div.worker {margin-bottom: 10px;}
</style>

<h2>Workers Management</h2>

% if show_admin:
  <div class="worker">
    <h3>Worker admin</h3>
    <form method="POST">
      <table>
        <thead>
          <tr>
            <th>Worker</th>
            <th>Blocked</th>
            <th>Last touched</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>${worker_name}</td>
            <td><input type="checkbox" name="blocked" ${"checked" if blocked else ""}></td>
            <td>${delta_date(diff_date(last_updated)) if last_updated is not None else "Never"}</td>
            <td><textarea cols=40 rows=4 name="message">${message}</textarea><td>
          </tr>
          <tr>
            <td><input type="submit" name="submit" value="Submit" style="margin-right: 5px;"><input type="submit" name="sumbit" value="Cancel"></td>
          </tr>
        </tbody>
      </table>
    </form>
  </div>
% endif  ## show_admin

<div class="worker">
  <h3> Blocked workers </h3>
  <table class="table table-striped table-sm">
    <thead class="sticky-top">
      <tr>
        <th> Worker </th>
        <th> Last touched</th>
        <th> Events</th>
      </tr>
    </thead>
    <tbody>
      % for w in blocked_workers:
        <tr>
          <td> <a href="/workers/${w['worker_name']}">${w["worker_name"]}</td>
          <td> ${delta_date(diff_date(w["last_updated"])) if last_updated is not None else "Never"}</td>
          <td> <a href="/actions?text=%22${w['worker_name']}%22">/actions?text="${w['worker_name']}"</a></td>
        </tr>
      % endfor
    </tbody>
  </table>
</div>
