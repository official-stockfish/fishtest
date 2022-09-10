<%inherit file="base.mak"/>

<%!
  title = "Users - Pending & Idle | Stockfish Testing"
%>

<%block name="head">
  <meta property="og:title" content="${title}" />
</%block>

<script>
  document.title = '${title}';
</script>

<h2>Users - Pending & Idle</h2>

<h4>Pending Users</h4>

<table class="table table-striped table-sm">
  <thead>
    <tr>
      <th>Username</th>
      <th>Registration Time</th>
      <th>eMail</th>
    </tr>
  </thead>
  <tbody>
    % for user in users:
        <tr>
          <td style="width:15%"><a href="/user/${user['username']}">${user['username']}</a></td>
          <td style="width:15%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
          <td style="width:70%">${user['email']}</td>
        </tr>
    % endfor
  </tbody>
</table>

<h4>Idle Users</h4>

<table class="table table-striped table-sm">
  <thead>
    <tr>
      <th>Username</th>
      <th>Registration Time</th>
      <th>eMail</th>
    </tr>
  </thead>
  <tbody>
    % for user in idle:
        <tr>
          <td style="width:15%"><a href="/user/${user['username']}">${user['username']}</a></td>
          <td style="width:15%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
          <td style="width:60%">${user['email']}</td>
        </tr>
    % endfor
  </tbody>
</table>
