<%inherit file="base.mak"/>

<h3>Users</h3>

<dl class="dl-horizontal">
  <dt>Total Users</dt>
  <dd>${len(users)}</dd>
  <dt>Tests submitted</dt>
  <dd>${sum(u['tests'] for u in users)}</dd>
  <dt>Games played</dt>
  <dd>${sum(u['games'] for u in users)}</dd>
  <dt>CPU time</dt>
  <dd>${'%.2f years' % (sum(u['cpu_hours'] for u in users)/(24*365))}</dd>
</dl>

<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Username</th>
   <th>Last active</th>
   <th>CPU Hours</th>
   <th>Games played</th>
   <th>Tests submitted</th>
   <th>Tests repository</th>
  </tr>
 </thead>
 <tbody>
 %for user in users:
  <tr>
   <td>${user['username']}</td>
   <td>${user['last_updated']}</td>
   <td>${int(user['cpu_hours'])}</td>
   <td>${int(user['games'])}</td>
   <td><a href="/tests/user/${user['username']}">${user['tests']}</td>
   <td><a href="${user['tests_repo']}" target="_blank">${user['tests_repo']}</a></td>
  </tr>
 %endfor
 </tbody>
</table>
