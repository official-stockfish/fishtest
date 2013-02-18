<%page args="run, include_results=True"/>

<div>
<form action="/tests/delete" method="POST" style="display:inline">
  <input type="hidden" name="run-id" value="${run['_id']}">
  <button type="submit" class="btn btn-danger btn-mini">
    <i class="icon-trash"></i>
  </button>
</form>${run['name'] | n}
</div>
%if 'info' in run['args'] and len(run['args']['info']) > 0:
  <div>Info: ${run['args']['info']}</div>
%endif
%if include_results:
%for line in run['results']['info']:
  <div class="label ${run['results']['style']}">${line}</div>
%endfor
%endif
