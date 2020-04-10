<%inherit file="base.mak"/>

<link href="/css/flags.css" rel="stylesheet">

<h2>Stockfish Testing Queue</h2>

%if page_idx == 0:
  %if show_machines:
    <h3>
      <span>
        ${len(machines)} machines ${cores}
        cores ${'%.2fM' % (nps / (cores * 1000000.0 + 1))} nps
        (${'%.2fM' % (nps / (1000000.0 + 1))} total nps)
        ${games_per_minute} games/minute
        ${pending_hours} hours remaining
      </span>
      <button id="machines-button" class="btn">
        ${'Hide' if machines_shown else 'Show'}
      </button>
    </h3>

    <div id="machines"
         style="${'' if machines_shown else 'display: none;'}">
      <table class="table table-striped table-condensed"
             style="max-width: 960px;">
        <thead>
          <tr>
          <th>Machine</th>
          <th>Cores</th>
          <th>MNps</th>
          <th>System</th>
          <th>Version</th>
          <th>Running on</th>
          <th>Last updated</th>
          </tr>
        </thead>
        <tbody>
          %for machine in machines:
            <tr>
              <td>${machine['username']}</td>
              <td>
                %if 'country_code' in machine:
                  <div class="flag flag-${machine['country_code'].lower()}"
                      style="display: inline-block"></div>
                %endif
                ${machine['concurrency']}
              </td>
              <td>${'%.2f' % (machine['nps'] / 1000000.0)}</td>
              <td>${machine['uname']}</td>
              <td>${machine['version']}</td>
              <td>
                <a href="/tests/view/${machine['run']['_id']}">${machine['run']['args']['new_tag']}</a>
              </td>
              <td>${machine['last_updated']}</td>
            </tr>
          %endfor
          %if len(machines) == 0:
            <td>No machines running</td>
          %endif
        </tbody>
      </table>
    </div>
  %endif

  <h3>
    Pending - ${len(runs['pending'])} tests
    <button id="pending-button" class="btn">
      ${'Hide' if pending_shown else 'Show'}
    </button>
  </h3>
  <div id="pending"
       style="${'' if pending_shown else 'display: none;'}">
    %if len(runs['pending']) == 0:
      No pending runs
    %else:
      <%include file="run_table.mak" args="runs=runs['pending'], show_delete=True"/>
    %endif
  </div>

  %if len(runs['failed']) > 0:
    <h3>Failed</h3>
    <%include file="run_table.mak" args="runs=runs['failed'], show_delete=True"/>
  %endif

  <h3>Active - ${len(runs['active'])} tests</h3>
  <%include file="run_table.mak" args="runs=runs['active']"/>
%endif

<%def name="pagination()">
  %if len(pages) > 3:
    <span class="pagination pagination-small">
      <ul>
        %for page in pages:
          <li class="${page['state']}"><a href="${page['url']}">${page['idx']}</a></li>
        %endfor
      </ul>
    </span>
  %endif
</%def>

<h3>Finished - ${finished_runs} tests ${pagination()}</h3>
<%include file="run_table.mak" args="runs=runs['finished']"/>
<h3>${pagination()}</h3>
