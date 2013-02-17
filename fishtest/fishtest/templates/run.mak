<%page args="run"/>

<div>${run['name'] | n}</div>
%if 'info' in run['args']:
  <div>Info: ${run['info']}</div>
%endif
%for line in run['results']['info']:
  <div class="label ${run['results']['style']}">${line}</div>
%endfor

