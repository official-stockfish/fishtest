<%page args="runs"/>

<table class='table table-striped table-condensed'>
  <thead>
    <th width="8%">Date</th>
    <th width="14%">New</th>
    <th width="14%">Base</th>
    <th width="32%">Results</th>
    <th width="15%">Games/TC</th>
    <th>Diff</th>
    <th width="15%">Info</th>
  </thead>

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
    <!--
    <td>
      <form action="/tests/delete" method="POST" style="display:inline">
        <input type="hidden" name="run-id" value="${run['_id']}">
        <button type="submit" class="btn btn-danger btn-mini">
          <i class="icon-trash"></i>
        </button>
      </form>
    </td>
    -->
    <td>${run['start_time'].strftime("%d-%m-%y")}</td>
    <td>${run['args']['new_tag']}<br>${format_sha(run['args']['resolved_new']) | n}</td>
    <td>${run['args']['base_tag']}<br>${format_sha(run['args']['resolved_base']) | n}</td>
    <td><pre style="${get_run_style(run)}">${'\n'.join(run['results']['info'])}</pre></td>
    <td>${run['args']['num_games']} @ ${run['args']['tc']}</td>
    <td>
      <a href="${'%s/compare/%s...%s' % (repo, run['args']['resolved_base'][:7], run['args']['resolved_new'][:7])}">Diff</a>
    </td>
    <td>${run['args'].get('info', '')}</td>
   </tr>
  %endfor
  </tbody>
</table>
