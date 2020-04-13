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
      %if machines_shown:
        <%include file="machines_table.mak" args="machines=machines"/>
      %endif
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
