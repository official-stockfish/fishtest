<%inherit file="base.mak"/>

<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Username</th>
   <th>Last active</th>
   <th>Games played</th>
   <th>Tests submitted</th>
  </tr>
 </thead>
 <tbody>
 %for user in users:
  <tr>
   <td>${user['username']}</td>
   <td>${user['last_updated']}</td>
   <td>${user['completed']}</td>
   <td>${user['tests']}</td>
  </tr>
 %endfor
 </tbody>
</table>
