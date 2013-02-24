<%page args="runs, show_delete=False"/>

<table class='table table-striped table-condensed'>
  <%
    repo = 'https://github.com/mcostalba/FishCooking'
    def format_sha(sha):
      return '<a href="%s/commit/%s">%s</a>' % (repo, sha, sha[:7])
  %>

  <tbody>
  %for run in runs:
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
    <td style="width:8%"><a href="/tests/view/${run['_id']}">${run['start_time'].strftime("%d-%m-%y")}</a></td>
    <td style="width:13%">${run['args']['new_tag']}<br>${format_sha(run['args']['resolved_new']) | n}</td>
    <td style="width:13%">
      ${run['args']['base_tag']}
      <a href="${'%s/compare/%s...%s' % (repo, run['args']['resolved_base'][:7], run['args']['resolved_new'][:7])}">diff</a>
      <br>
      ${format_sha(run['args']['resolved_base']) | n}
    </td>
    <td style="min-width:280px;width:280px"><%include file="elo_results.mak" args="run=run" /></td>
    <td style="width:12%">${run['args']['num_games']} @ ${run['args']['tc']}</td>
    <td>${run['args'].get('info', '')}</td>
   </tr>
  %endfor
  </tbody>
</table>
