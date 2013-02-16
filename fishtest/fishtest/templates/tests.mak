<%inherit file="base.mak"/>

<h2>Stockfish Tests</h2>
<h3>Active</h3>
<ul>
%for machine, jobs in machines.iteritems():
  <li>Machine: ${machine} - Running: ${jobs} chunks</li>
%endfor
%if len(machines) == 0:
  <li>No machines running</li>
%endif
</ul>
<ul>
%for run in active:
  <li>${run['name'] | n}
    <pre>${run['results']}</pre>
  </li>
%endfor
</ul>

<h3>Waiting</h3>
<ul>
%for job in waiting:
  <li>${job | n}</li>
%endfor
%if len(waiting) == 0:
  <li>None</li>
%endif
</ul>

<h3>Recent Runs</h3>
%for run in runs:
  <h4>${run['name'] | n}</h4>
  <pre>${run['results']}</pre>
%endfor
