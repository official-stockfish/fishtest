<%page args="run, show_gauge=False"/>

<%
  def get_run_style(run):
    ret='white-space:nowrap;'      
    style= run['results_info'].get('style','')
    if style!='':
      ret+='background-color:' + style+';'
    tc=run['args']['tc']
    new_tc=run['args'].get('new_tc',tc)
    if tc!=new_tc:
       ret+='border-style:solid;border-color:Pink;border-width:medium;border-radius:0px;'
    return ret
%>
<%def name="list_info(run)">
<%
      info=run['results_info']['info']
      l=len(info)
%>
      % for i in range(0,l):
      	${info[i]}
        % if i<l-1:
	   <br/>
	% endif   
      % endfor
</%def>

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
<pre style="${get_run_style(run)}" class="elo-results">
${list_info(run)}
</pre>
%if show_gauge:
</div>
%endif
%if 'sprt' in run['args'] and not 'Pending' in run['results_info']['info'][0]:
</a>
%endif
