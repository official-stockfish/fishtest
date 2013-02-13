<%inherit file="base.mak"/>

<h2>Stockfish Tests</h2>
<h3>Active</h3>
<ul>
%for machine, jobs in machines.iteritems():
  <li>Machine: ${machine} --
  %if len(jobs) == 0:
    None
  %else:
    Running
    %for job in jobs:
      <a href="${job['url']}">$job['name']</a>
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
