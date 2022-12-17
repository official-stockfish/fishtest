<%inherit file="base.mak"/>

<link
  rel="stylesheet"
  href="/css/flags.css?v=${cache_busters['css/flags.css']}"
  integrity="sha384-${cache_busters['css/flags.css']}"
  crossorigin="anonymous"
>

<h2>Stockfish Testing Queue</h2>

% if page_idx == 0:
    <div class="mw-xxl">
      <div class="row g-3 mb-3">
        <div class="col-6 col-sm">
          <div class="card card-lg-sm text-center">
            <div class="card-header text-nowrap" title="Cores">Cores</div>
            <div class="card-body">
              <h4 class="card-title mb-0 monospace">${cores}</h4>
            </div>
          </div>
        </div>
        <div class="col-6 col-sm">
          <div class="card card-lg-sm text-center">
            <div class="card-header text-nowrap" title="Nodes per second">Nodes / sec</div>
            <div class="card-body">
              <h4 class="card-title mb-0 monospace">${f"{nps / (1000000 + 1):.0f}"}M</h4>
            </div>
          </div>
        </div>
        <div class="col-6 col-sm">
          <div class="card card-lg-sm text-center">
            <div class="card-header text-nowrap" title="Games per minute">Games / min</div>
            <div class="card-body">
              <h4 class="card-title mb-0 monospace">${games_per_minute}</h4>
            </div>
          </div>
        </div>
        <div class="col-6 col-sm">
          <div class="card card-lg-sm text-center">
            <div class="card-header text-nowrap" title="Time remaining">Time remaining</div>
            <div class="card-body">
              <h4 class="card-title mb-0 monospace">${pending_hours}h</h4>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <script>
      function toggle_machines() {
        const button = document.getElementById("machines-button");
        const div = document.getElementById("machines");
        const active = button.textContent.trim() === "Hide";
        button.textContent = active ? "Show" : "Hide";
        document.cookie =
          "machines_state" + "=" + button.textContent.trim() + ";max-age=${10 * 365 * 24 * 60 * 60};SameSite=Lax;";
      }
    </script>
    
    <h4>
      <a id="machines-button" class="btn btn-sm btn-light border" 
        data-bs-toggle="collapse" href="#machines" role="button" aria-expanded="false"
        aria-controls="machines" onclick="toggle_machines()" >
        ${'Hide' if machines_shown else 'Show'}
      </a>
      <span>
        Workers - ${len(machines)} machines
      </span>
    </h4>

    <div id="machines"
         class="overflow-auto ${'collapse show' if machines_shown else 'collapse'}">
      <%include file="machines_table.mak"/>
    </div>
% endif

<%include file="run_tables.mak"/>
