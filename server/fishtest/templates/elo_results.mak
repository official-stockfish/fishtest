<%page args="run, show_gauge=False"/>

<%
  def get_run_style(run):
    ret = 'white-space:nowrap; border: 1px solid rgba(0,0,0,0.15);'
    style = run['results_info'].get('style','')
    if style != '':
      ret += 'background-color:' + style+';'
    tc = run ['args']['tc']
    new_tc = run['args'].get('new_tc',tc)
    if tc != new_tc:
       ret += 'border-style:solid;border-color:Pink;border-width:medium;'
    return ret
%>
<%def name="list_info(run)">
  <%
    info = run['results_info']['info']
    l = len(info)
    has_pairs_ratio = (
        "sprt" not in run["args"]
        and "spsa" not in run["args"]
        and "pentanomial" in run["results"]
    )
    if has_pairs_ratio:
      results5 = run["results"]["pentanomial"]
      results5_pairs_ratio =  (
          sum(results5[3:]) / sum(results5[0:2])
          if any(results5[0:2])
          else float("inf")
          if any(results5[3:])
          else float("nan")
      )
  %>
  % for i in range(l):
      ${info[i]}
      % if i < l-1:
          <br/>
      % endif
  % endfor
  % if has_pairs_ratio:
      <br/>
      ${f"PairsRatio: {results5_pairs_ratio:.5f}"}
  % endif
</%def>

% if 'sprt' in run['args'] and not 'Pending' in run['results_info']['info'][0]:
    <a href="${'/html/live_elo.html?' + str(run['_id'])}" style="color: inherit">
% endif
% if show_gauge:
    <div id="chart_div_${str(run['_id'])}" style="width:90px;float:left;"></div>
    % if 'sprt' in run['args'] and not 'Pending' in run['results_info']['info'][0]:
        <div style="margin-left:90px;padding: 30px 0;">
    % else:
        <div style="margin-left:90px;">
    % endif
% endif
<pre style="${get_run_style(run)}" class="rounded elo-results">
  ${list_info(run)}
</pre>
% if show_gauge:
    </div>
% endif
% if 'sprt' in run['args'] and not 'Pending' in run['results_info']['info'][0]:
    </a>
% endif
