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
      <div class="dropdown">
        <button type="submit" class="btn btn-danger btn-mini" data-toggle="dropdown">
          <i class="icon-trash"></i>
        </button>
        <div class="dropdown-menu" role="menu">
          <form action="/tests/delete" method="POST" style="display:inline">
            <input type="hidden" name="run-id" value="${run['_id']}">
            <button type="submit" class="btn btn-danger btn-mini">Confirm</button>
          </form>
        </div>
      </div>
    </td>
    %endif
    <td style="width:6%"><a href="/tests/view/${run['_id']}">${run['start_time'].strftime("%d-%m-%y")}</a></td>
    <td style="width:2%">${run['args'].get('username','')[:2]}</td>
    <td style="width:12%">${base.format_sha(run['args']['new_tag'], run['args']['resolved_new'], run) | n}</td>
    <td style="width:12%">
      ${base.format_sha(run['args']['base_tag'], run['args']['resolved_base'], run) | n}
      (${base.diff_url(run)})
    </td>
    <td style="min-width:285px;width:285px"><%include file="elo_results.mak" args="run=run" /></td>
    <td style="width:14%">${num_games} @ ${run['args']['tc']} th ${str(run['args'].get('threads',1))}</td>
    <td>${run['args'].get('info', '')}</td>
   </tr>
  %endfor
  </tbody>
</table>
