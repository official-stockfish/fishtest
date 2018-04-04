<%inherit file="base.mak"/>
<h3> </h3>

<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Time</th>
   <th>Username</th>
   <th>Run/User</th>
   <th>Action</th>
  </tr>
 </thead>
 <tbody>
 %for action in actions:
  <tr>
   <td>${action['time'].strftime("%d-%m-%y %H:%M:%S")}</td>
   %if approver:
   <td><a href="/user/${action['username']}">${action['username']}</a></td>
   %else:
   <td>${action['username']}</td>
   %endif
   %if 'run' in action:
   <td><a href="/tests/view/${action['_id']}">${action['run'][:23]}</a></td>
   %elif approver:
   <td><a href="/user/${action['user']}">${action['user']}</a></td>
   %else:
   <td>${action['user']}</td>
   %endif
   <td>${action['description']}</td>
  </tr>
 %endfor
 </tbody>
</table>
