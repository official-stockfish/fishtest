<%inherit file="base.mak"/>

<h2>Stockfish Testing Queue</h2>
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
  <li>${run['name'] | n}
    <pre>${run['results']}</pre>
  </li>
%endfor
</ul>

<h3>Pending</h3>
<ul>
%for job in waiting:
  <li>${job | n}</li>
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

<h3>Finished</h3>
%for run in runs:
  <h4>${run['name'] | n}</h4>
  <pre>${run['results']}</pre>
%endfor
