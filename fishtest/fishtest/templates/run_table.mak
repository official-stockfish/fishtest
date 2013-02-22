<%page args="runs, show_delete=False"/>

<table class='table table-striped table-condensed'>
  <%
    repo = 'https://github.com/mcostalba/FishCooking'
    def format_sha(sha):
      return '<a href="%s/commit/%s">%s</a>' % (repo, sha, sha[:7])

    def get_run_style(run):
      if 'style' in run['results']:
        return 'background-color:' + run['results']['style']
      return ''
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
    <td style="width:8%">${run['start_time'].strftime("%d-%m-%y")}</td>
    <td style="width:13%">${run['args']['new_tag']}<br>${format_sha(run['args']['resolved_new']) | n}</td>
    <td style="width:13%">
      ${run['args']['base_tag']}
      <a href="${'%s/compare/%s...%s' % (repo, run['args']['resolved_base'][:7], run['args']['resolved_new'][:7])}">diff</a>
      <br>
      ${format_sha(run['args']['resolved_base']) | n}
    </td>
    <td style="min-width:325px;width:325px"><pre style="${get_run_style(run)};font-size:12px;margin:2px;padding:1px;line-height:13px">${'\n'.join(run['results']['info'])}</pre></td>
    <td style="width:12%">${run['args']['num_games']} @ ${run['args']['tc']}</td>
    <td>${run['args'].get('info', '')}</td>
   </tr>
  %endfor
  </tbody>
</table>
