<%page args="run, show_gauge=False"/>

<%
  def get_run_style(run):
    if 'style' in run['results_info']:
      return 'background-color:' + run['results_info']['style']
    return ''
%>

%if 'sprt' in run['args'] and not 'Pending' in run['results_info']['info'][0]:
<a href="${'/html/live_elo.html?' + str(run['_id'])}" style="text-decoration:none">
%endif
%if show_gauge:
<div id="chart_div_${str(run['_id'])}" style="width:90px;float:left;"></div>
%if 'sprt' in run['args'] and not 'Pending' in run['results_info']['info'][0]:
<div style="margin-left:90px;padding: 30px 0;">
%else:
<div style="margin-left:90px;">
%endif
%endif
<pre style="${get_run_style(run)};white-space:nowrap;" class="elo-results">
${run['results_info']['info'][0]}<br/>
${run['results_info']['info'][1] if len(run['results_info']['info']) > 1 else ''}
</pre>
%if show_gauge:
</div>
%endif
%if 'sprt' in run['args'] and not 'Pending' in run['results_info']['info'][0]:
</a>
%endif
