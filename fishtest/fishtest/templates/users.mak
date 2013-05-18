<%inherit file="base.mak"/>

<h4>Total Users: ${len(users)}
    Tests submitted: ${sum(u['tests'] for u in users)}
    CPU time: ${'%.2f years' % (sum(u['completed'] for u in users)/(24*365))}
</h4>

<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Username</th>
   <th>Last active</th>
   <th>CPU Hours</th>
   <th>Tests submitted</th>
   <th>Tests repository</th>
  </tr>
 </thead>
 <tbody>
 %for user in users:
  <tr>
   <td>${user['username']}</td>
   <td>${user['last_updated']}</td>
   <td>${int(user['completed'])}</td>
   <td><a href="/tests/user/${user['username']}">${user['tests']}</td>
   <td><a href="${user['tests_repo']}" target="_blank">${user['tests_repo']}</a></td>
  </tr>
 %endfor
 </tbody>
</table>
