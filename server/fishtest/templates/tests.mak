<%inherit file="base.mak"/>

<link rel="stylesheet"
      href="/css/flags.css?v=${cache_busters['css/flags.css']}"
      integrity="sha384-${cache_busters['css/flags.css']}"
      crossorigin="anonymous" />

<h2>Stockfish Testing Queue</h2>

% if page_idx == 0:
    <h4>
      <button id="machines-button" class="btn btn-sm btn-light border">
        ${'Hide' if machines_shown else 'Show'}
      </button>
      <span>
        ${len(machines)} machines ${cores}
        cores ${f"{nps / (cores * 1000000 + 1):.2f}"} MNps
        (${f"{nps / (1000000 + 1):.2f}"} total MNps)
        ${games_per_minute} games/minute
        ${pending_hours} hours remaining
      </span>
    </h4>

    <div id="machines"
         class="overflow-auto"
         style="${'' if machines_shown else 'display: none;'}">
      <%include file="machines_table.mak"/>
    </div>
% endif

<%include file="run_tables.mak"/>
