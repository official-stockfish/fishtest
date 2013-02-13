<%inherit file="base.mak"/>

<h2>Stockfish Tests</h2>
<h3>Active</h3>
<ul>
%for machine, jobs in machines.iteritems():
  <li>Machine: ${machine} --
  %if len(jobs) == 0:
    None
  %else:
    %for job in jobs:
      ${job['name']}
      <pre>${job['results']}</pre>
    %endfor
  %endif
  </li>
%endfor
%if len(machines) == 0:
  <li>None</li>
%endif
</ul>

<h3>Waiting</h3>
<ul>
%for job in waiting:
  <li>${job}</li>
%endfor
%if len(waiting) == 0:
  <li>None</li>
%endif
</ul>

<h3>Recent Runs</h3>
%for run in runs:
  <h4>${run['name']}</h4>
  <pre>${run['results']}</pre>
%endfor
