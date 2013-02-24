<%page args="run"/>

<%
  def get_run_style(run):
    if 'style' in run['results']:
      return 'background-color:' + run['results']['style']
    return ''
%>

<pre style="${get_run_style(run)};" class="elo-results">${'\n'.join(run['results']['info'])}</pre>
