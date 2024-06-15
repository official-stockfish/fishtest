<%page args="run, show_gauge=False"/>

<%!
  from fishtest.util import is_active_sprt_ltc, format_results

  def results_pre_attrs(results_info, run):
    ret = ''
    style = results_info.get('style', '')
    if style:
      ret = f'style="background-color: {style};"'

    classes = 'rounded elo-results results-pre'
    tc = run ['args']['tc']
    new_tc = run['args'].get('new_tc',tc)
    if tc != new_tc:
      classes += ' time-odds'
    ret += f' class="{classes}"'

    return ret
%>
<%
    results_info = format_results(run)
%>
<%def name="list_info(run)">
  <%
    info = results_info['info']
    l = len(info)
    elo_ptnml_run = (
        "sprt" not in run["args"]
        and "spsa" not in run["args"]
        and "pentanomial" in run["results"]
    )
    if elo_ptnml_run:
      import math
      import fishtest.stats.stat_util
      import fishtest.stats.LLRcalc

      def t_conf(avg, var, skewness, exkurt):
        t = (avg - 0.5) / var**0.5
        # limit for rounding error
        var_t = max(1 - t * skewness + 0.25 * t**2 * (exkurt + 2), 0)
        return t, var_t

      results5 = run["results"]["pentanomial"]
      z975 = fishtest.stats.stat_util.Phi_inv(0.975)
      nelo5_coeff = 800 / math.log(10) / (2**0.5) ## 245.67405854855017099
      N5, pdf5 = fishtest.stats.LLRcalc.results_to_pdf(results5)
      avg5, var5, skewness5, exkurt5 = fishtest.stats.LLRcalc.stats_ex(pdf5)
      t5, var_t5 = t_conf(avg5, var5, skewness5, exkurt5)
      nelo5 = nelo5_coeff * t5
      nelo5_delta = nelo5_coeff * z975 * (var_t5 / N5) ** 0.5

      results5_pairs_ratio =  (
          sum(results5[3:]) / sum(results5[0:2])
          if any(results5[0:2])
          else float("inf")
          if any(results5[3:])
          else float("nan")
      )
  %>
  % for i in range(l):
    ${info[i].replace("ELO", "Elo") if elo_ptnml_run and i == 0 else info[i]}
    % if i < l-1:
      <br>
    % endif
  % endfor
  % if elo_ptnml_run:
    <br>
    ${f"nElo: {nelo5:.2f} ± {nelo5_delta:.1f} (95%) PairsRatio: {results5_pairs_ratio:.2f}"}
  % endif
</%def>

% if 'sprt' in run['args'] and 'Pending' not in results_info['info'][0]:
  <a href="/tests/live_elo/${str(run['_id'])}" style="color: inherit;">
% endif
% if show_gauge:
  <div id="chart_div_${str(run['_id'])}" style="width:90px;float:left;"></div>
  % if 'sprt' in run['args'] and 'Pending' not in results_info['info'][0]:
    <div style="margin-left:90px;padding: 30px 0;">
  % else:
    <div style="margin-left:90px;">
  % endif
% endif
<pre ${results_pre_attrs(results_info, run)|n}>
  ${list_info(run)}
</pre>
% if show_gauge:
  </div>
% endif
% if 'sprt' in run['args'] and 'Pending' not in results_info['info'][0]:
  </a>
% endif
