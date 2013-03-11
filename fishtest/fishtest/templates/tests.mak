<%inherit file="base.mak"/>

<h2>Stockfish Testing Queue</h2>

<h3>Pending - ${pending_hours}hrs</h3>
%if len(pending) == 0:
  None
%else:
  <%include file="run_table.mak" args="runs=pending, show_delete=True"/>
%endif

%if len(failed) > 0:
<h3>Failed</h3>
<%include file="run_table.mak" args="runs=failed, show_delete=True"/>
%endif

<h3>Active</h3>
<table class="table table-striped table-condensed" style="width:60%">
 <thead>
  <tr>
   <th>Machine</th>
   <th>Cores</th>
   <th>System</th>
   <th>Last updated</th>
  </tr>
 </thead>
%for machine in machines:
 <tbody>
  <tr>
   <td>${machine['username']}</td>
   <td>${machine['concurrency']}</td>
   <td>${machine['uname'][0]} ${machine['uname'][2]}</td>
   <td>${machine['last_updated']}</td>
  </tr>
 </tbody>
%endfor
%if len(machines) == 0:
  <td>No machines running</td>
%endif
</table>
<%include file="run_table.mak" args="runs=active"/>

<h3>Finished</h3>
<%include file="run_table.mak" args="runs=runs"/>
