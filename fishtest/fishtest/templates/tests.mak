<%inherit file="base.mak"/>

<h2>Stockfish Testing Queue</h2>

<h3>Pending</h3>
<ul>
%for job in waiting:
  <li>${job['name'] | n}</li>
%endfor
%if len(waiting) == 0:
  <li>None</li>
%endif
</ul>

%if len(failed) > 0:
<h3>Failed</h3>
<ul>
%for job in failed:
  <li>${job | n}</li>
%endfor
</ul>
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
<ul>
%for run in active:
  <li>
    <%include file="run.mak" args="run=run"/>
  </li>
%endfor
</ul>

<h3>Finished</h3>
<ol>
%for run in runs:
  <li style="margin-bottom:6px">
    <%include file="run.mak" args="run=run"/>
  </li>
%endfor
</ol>
