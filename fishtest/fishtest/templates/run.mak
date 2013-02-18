<%page args="run, include_results=True"/>

<div>${run['name'] | n}
<form action="/tests/delete" method="POST" style="display:inline">
  <input type="hidden" name="run-id" value="${run['_id']}">
  <input type="submit" value="Delete" class="btn btn-danger btn-mini">
</form>
</div>
%if 'info' in run['args'] and len(run['args']['info']) > 0:
  <div>Info: ${run['args']['info']}</div>
%endif
%if include_results:
%for line in run['results']['info']:
  <div class="label ${run['results']['style']}">${line}</div>
%endfor
%endif
