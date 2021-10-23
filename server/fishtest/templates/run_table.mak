<%page args="runs, pages=None, show_delete=False, active=False"/>

<%namespace name="base" file="base.mak"/>

% if active:
    <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
    <script type="text/javascript">
      google.charts.load('current', {'packages':['gauge']});
      google.charts.setOnLoadCallback(drawCharts);

      function drawCharts() {
        var a = -2.94, b = 2.94;
        var options = {
          redFrom: a,
          redTo: 0,
          greenFrom: 0,
          greenTo: b,
          min: a,
          max: b,
          minorTicks: 5
        };

        % for run in runs:
            % if 'sprt' in run['args']:
                var data = google.visualization.arrayToDataTable([
                  ['Label', 'Value'],
                  ['LLR', ${run['results_info']['info'][0].split(' ')[1]}]
                ]);
                var chart = new google.visualization.Gauge(
                  document.getElementById('chart_div_${str(run['_id'])}')
                );
                chart.draw(data, options);
            % endif
        % endfor
      }
    </script>
% endif

<%def name="pagination()">
  % if pages and len(pages) > 3:
      <nav>
        <ul class="pagination pagination-sm">
        % for page in pages:
            <li class="${page['state']}">
              % if page['state'] not in ['disabled', 'active']:
                  <a class="page-link" href="${page['url']}">${page['idx']}</a>
              % else:
                  <a class="page-link">${page['idx']}</a>
              % endif
            </li>
        % endfor
        </ul>
      </nav>
  % endif
</%def>

${pagination()}

<div>
  <table class="table table-striped table-sm">
    <tbody>
      % for run in runs:
          <tr>
            % if show_delete:
                <td style="width: 1%;" class="run-button run-deny">
                  <div class="dropdown">
                    <button type="submit" class="btn btn-danger btn-sm" data-bs-toggle="dropdown">
                      <svg viewBox="0 0 8 8" style="width: 12px; height: 12px; fill: white; background: none;">
                        <path d="M3 0c-.55 0-1 .45-1 1h-1c-.55 0-1 .45-1 1h7c0-.55-.45-1-1-1h-1c0-.55-.45-1-1-1h-1zm-2 3v4.813c0 .11.077.188.188.188h4.625c.11 0 .188-.077.188-.188v-4.813h-1v3.5c0 .28-.22.5-.5.5s-.5-.22-.5-.5v-3.5h-1v3.5c0 .28-.22.5-.5.5s-.5-.22-.5-.5v-3.5h-1z" data-id="trash"></path>
                      </svg>
                    </button>
                    <div class="dropdown-menu" role="menu">
                      <form action="/tests/delete" method="POST" style="display: inline;">
                        <input type="hidden" name="csrf_token"
                               value="${request.session.get_csrf_token()}" />
                        <input type="hidden" name="run-id" value="${run['_id']}">
                        <button type="submit" class="btn btn-danger btn-mini">Confirm</button>
                      </form>
                    </div>
                  </div>
                </td>

                <td style="width: 1%;" class="run-button">
                  % if run.get('approved', False):
                      <button class="btn btn-success btn-sm">
                        ## thumbs up
                        <svg viewBox="0 0 8 8" style="width: 12px; height: 12px; fill: white; background: none;">
                          <path d="M4.438 0c-.19.021-.34.149-.438.344-.13.26-1.101 2.185-1.281 2.375-.19.18-.439.281-.719.281v4.001h3.5c.21 0 .389-.133.469-.313 0 0 1.031-2.908 1.031-3.188 0-.28-.22-.5-.5-.5h-1.5c-.28 0-.5-.25-.5-.5s.389-1.574.469-1.844c.08-.27-.053-.545-.313-.625l-.219-.031zm-4.438 3v4h1v-4h-1z" data-id="thumb-up"></path>
                        </svg>
                      </button>
                  % else:
                      <button class="btn btn-warning btn-sm">
                        ## question mark
                        <svg viewBox="0 0 8 8" style="width: 12px; height: 12px; fill: white; background: none;">
                          <path d="M4.469 0c-.854 0-1.48.256-1.875.656s-.54.901-.594 1.281l1 .125c.036-.26.125-.497.313-.688.188-.19.491-.375 1.156-.375.664 0 1.019.163 1.219.344.199.181.281.405.281.656 0 .833-.313 1.063-.813 1.5-.5.438-1.188 1.083-1.188 2.25v.25h1v-.25c0-.833.344-1.063.844-1.5.5-.438 1.156-1.083 1.156-2.25 0-.479-.168-1.02-.594-1.406-.426-.387-1.071-.594-1.906-.594zm-.5 7v1h1v-1h-1z" data-id="question-mark"></path>
                        </svg>
                      </button>
                  % endif
                </td>
            % endif

            <td style="width: 6%;" class="run-date">
              ${run['start_time'].strftime("%y-%m-%d")}
            </td>

            <td style="width: 2%;" class="run-user">
              <a href="/tests/user/${run['args'].get('username', '')}"
                 title="${run['args'].get('username', '')}">
                ${run['args'].get('username', '')[:3]}
              </a>
            </td>

            <td style="width: 16%;" class="run-view">
              <a href="/tests/view/${run['_id']}">${run['args']['new_tag'][:23]}</a>
            </td>

            <td style="width: 2%;" class="run-diff">
              <a href="${h.diff_url(run)}" target="_blank" rel="noopener">diff</a>
            </td>

            <td style="width: 1%;" class="run-elo">
              <%include file="elo_results.mak" args="run=run, show_gauge=active" />
            </td>

            <td style="width: 11%;" class="run-live">
              % if 'sprt' in run['args']:
                  <a href="/html/live_elo.html?${str(run['_id'])}" target="_blank">sprt</a>
              % else:
                  ${run['args']['num_games']}
              % endif
              @ ${run['args']['tc']} th ${str(run['args'].get('threads',1))}
              <br>
              ${('cores: '+str(run['cores'])) if not run['finished'] and 'cores' in run else ''}
            </td>

            <td style="min-width: 150px;" class="run-info">
              ${run['args'].get('info', '')}
            </td>
          </tr>
      % endfor
    </tbody>
  </table>
</div>

${pagination()}
