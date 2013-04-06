<%inherit file="base.mak"/>

<h3>Users</h3>
<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Username</th>
   <th>Last active</th>
   <th>Games played</th>
  </tr>
 </thead>
 <tbody>
 %for user in users:
  <tr>
   <td>${user['username']}</td>
   <td>${user.get('last_updated', '-')}</td>
   <td>${user.get('completed', 0)}</td>
  </tr>
 %endfor
 </tbody>
</table>
