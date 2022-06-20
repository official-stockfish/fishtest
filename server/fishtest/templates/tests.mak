<%inherit file="base.mak"/>

<link rel="stylesheet"
      href="/css/flags.css?v=${cache_busters['css/flags.css']}"
      integrity="sha384-${cache_busters['css/flags.css']}"
      crossorigin="anonymous" />

<h2>Stockfish Testing Queue</h2>

% if page_idx == 0:
    <h4>
      <span class="d-block d-sm-inline text-nowrap">${cores} <small>cores</small></span>
      <span class="d-none d-sm-inline"> @ </span>
      <span class="d-block d-sm-inline text-nowrap">${f"{nps / (cores * 1000000 + 1):.2f}"} <small>Mnps</small> (${f"{nps / (1000000 + 1):.2f}"} <small>Mnps</small>)</span>
      <span class="d-none d-md-inline"> - </span>
      <div class="d-block d-md-inline">
        <span class="d-block d-sm-inline text-nowrap">${games_per_minute} <small>games/minute</small></span>
        <span class="d-none d-sm-inline"> - </span>
        <span class="d-block d-sm-inline text-nowrap">${pending_hours} <small>hours remaining</small></span>
      </div>
    </h4>
    <h4>
      <button id="machines-button" class="btn btn-sm btn-light border">
        ${'Hide' if machines_shown else 'Show'}
      </button>
      <span>
        Workers - ${len(machines)} machines
      </span>
    </h4>

    <div id="machines"
         class="overflow-auto"
         style="${'' if machines_shown else 'display: none;'}">
      <%include file="machines_table.mak"/>
    </div>
% endif

<%include file="run_tables.mak"/>
