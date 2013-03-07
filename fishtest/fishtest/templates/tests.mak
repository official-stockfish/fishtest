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
<ul>
%for machine in machines:
  <li>Machine: ${machine['username']} - ${machine['concurrency']} cores</li>
%endfor
%if len(machines) == 0:
  <li>No machines running</li>
%endif
</ul>
<%include file="run_table.mak" args="runs=active"/>

<h3>Finished</h3>
<%include file="run_table.mak" args="runs=runs"/>
