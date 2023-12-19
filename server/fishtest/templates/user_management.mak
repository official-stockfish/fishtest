<%inherit file="base.mak"/>

<script>
  document.title = "User Management | Stockfish Testing";
</script>

<h2>User Management</h2>

<h4>Pending Users</h4>

<table class="table table-striped table-sm">
  <thead>
    <tr>
      <th style="width:20%">Username</th>
      <th style="width:20%">Registration Time</th>
      <th style="width:60%">Email</th>
    </tr>
  </thead>
  <tbody>
    % for user in pending_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:60%">${user['email']}</td>
      </tr>
    % endfor
    % if len(pending_users) == 0:
      <tr>
        <td colspan=20>No pending users</td>
      </tr>
    % endif
  </tbody>
</table>

<h4>Blocked Users</h4>

<table class="table table-striped table-sm">
  <thead>
    <tr>
      <th style="width:20%">Username</th>
      <th style="width:20%">Registration Time</th>
      <th style="width:60%">Email</th>
    </tr>
  </thead>
  <tbody>
    % for user in blocked_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:60%">${user['email']}</td>
      </tr>
    % endfor
    % if len(blocked_users) == 0:
      <tr>
        <td colspan=20>No blocked users</td>
      </tr>
    % endif
  </tbody>
</table>

<h4>Idle Users</h4>

<table class="table table-striped table-sm">
  <thead>
    <tr>
      <th style="width:20%">Username</th>
      <th style="width:20%">Registration Time</th>
      <th style="width:60%">Email</th>
    </tr>
  </thead>
  <tbody>
    % for user in idle_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:60%">${user['email']}</td>
      </tr>
    % endfor
    % if len(idle_users) == 0:
      <tr>
        <td colspan=20>No idle users</td>
      </tr>
    % endif
  </tbody>
</table>
