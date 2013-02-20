<%inherit file="base.mak"/>

<h2>Stockfish Testing Queue</h2>

<h3>Pending</h3>
%if len(waiting) == 0:
  None
%else:
  <%include file="run_table.mak" args="runs=waiting, show_delete=True"/>
%endif

%if len(failed) > 0:
<h3>Failed</h3>
<%include file="run_table.mak" args="runs=failed"/>
%endif

<h3>Active</h3>
<ul>
%for machine, jobs in machines.iteritems():
  <li>Machine: ${machine} - ${jobs}</li>
%endfor
%if len(machines) == 0:
  <li>No machines running</li>
%endif
</ul>
<%include file="run_table.mak" args="runs=active"/>

<h3>Finished</h3>
<%include file="run_table.mak" args="runs=runs"/>
