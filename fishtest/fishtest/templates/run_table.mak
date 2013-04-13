<%page args="runs, show_delete=False"/>

<%namespace name="base" file="base.mak"/>

<table class='table table-striped table-condensed'>
  <tbody>
  %for run in runs:
   <%
    if 'sprt' in run['args']:
      num_games = 'sprt'
    else:
      num_games = run['args']['num_games']
   %>
   <tr>
   %if show_delete:
    <td>
      <form action="/tests/delete" method="POST" style="display:inline">
        <input type="hidden" name="run-id" value="${run['_id']}">
        <button type="submit" class="btn btn-danger btn-mini">
          <i class="icon-trash"></i>
        </button>
      </form>
    </td>
    %endif
    <td style="width:6%"><a href="/tests/view/${run['_id']}">${run['start_time'].strftime("%d-%m-%y")}</a></td>
    <td style="width:2%">${run['args'].get('username','')[:2]}</td>
    <td style="width:12%">${run['args']['new_tag']}<br>${base.format_sha(run['args']['resolved_new'], run) | n}</td>
    <td style="width:12%">
      ${run['args']['base_tag']}
      ${base.diff_url(run)}
      <br>
      ${base.format_sha(run['args']['resolved_base'], run) | n}
    </td>
    <td style="min-width:285px;width:285px"><%include file="elo_results.mak" args="run=run" /></td>
    <td style="width:14%">${num_games} @ ${run['args']['tc']} th ${str(run['args'].get('threads',1))}</td>
    <td>${run['args'].get('info', '')}</td>
   </tr>
  %endfor
  </tbody>
</table>
