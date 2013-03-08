<%page args="run"/>

<%
  def get_run_style(run):
    if 'style' in run['results_info']:
      return 'background-color:' + run['results_info']['style']
    return ''
%>

<pre style="${get_run_style(run)};" class="elo-results">${'\n'.join(run['results_info']['info'])}</pre>
