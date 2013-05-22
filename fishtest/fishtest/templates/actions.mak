<%inherit file="base.mak"/>
<h4>Actions</h4>

<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Time</th>
   <th>Username</th>
   <th>Action</th>
   <th>Details</th>
  </tr>
 </thead>
 <tbody>
 %for action in actions:
  <tr>
   <td>${action['time'].strftime("%d-%m-%y %H:%M:%S")}</td>
   <td>${action['username']}</td>
   <td>${action['action']}</td>
   <td>
     %if action['action'] == 'delete_run' or action['action'] == 'stop_run' or action['action'] == 'new_run':
       <a href="/tests/view/${action['data']['_id']}">${action['data']['args']['new_tag'][:23]}</a>
     %elif action['action'] == 'modify_run':
       Priority change from ${action['data']['before']['args']['priority']} to ${action['data']['after']['args']['priority']}
     %else:
       Unknown
     %endif
   </td>
  </tr>
 %endfor
 </tbody>
</table>
