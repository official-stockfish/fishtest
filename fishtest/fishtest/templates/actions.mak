<%inherit file="base.mak"/>
<h3> </h3>

<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Time</th>
   <th>Username</th>
   <th>Run</th>
   <th>Action</th>
  </tr>
 </thead>
 <tbody>
 %for action in actions:
  <tr>
   <td>${action['time'].strftime("%d-%m-%y %H:%M:%S")}</td>
   <td>${action['username']}</td>
   <td><a href="/tests/view/${action['_id']}">${action['run'][:23]}</a></td>
   <td>${action['description']}</td>
  </tr>
 %endfor
 </tbody>
</table>
