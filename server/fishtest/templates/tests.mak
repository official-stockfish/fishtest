<%inherit file="base.mak"/>

<link href="/css/flags.css" rel="stylesheet">

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
      % if machines_shown:
          <%include file="machines_table.mak" args="machines=machines"/>
      % endif
    </div>
% endif

<%include file="run_tables.mak"/>
