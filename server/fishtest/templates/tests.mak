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
        <div class="card card-lg-sm text-center" role="region">
          <div
            class="card-header text-nowrap"
            id="cores-header"
            title="Total cores connected to the framework"
            aria-label="Total cores connected to the framework"
          >Cores</div>
          <div class="card-body">
            <h4 class="card-title mb-0 monospace">${cores}</h4>
          </div>
        </div>
      </div>
      <div class="col-6 col-sm">
        <div class="card card-lg-sm text-center" role="region">
          <div
            class="card-header text-nowrap"
            id="nps-header"
            title="Total nodes per second running"
            aria-label="Total nodes per second running"
          >Nodes / sec</div>
          <div class="card-body">
            <h4 class="card-title mb-0 monospace">${f"{nps / (1000000 + 1):.0f}"}M</h4>
          </div>
        </div>
      </div>
      <div class="col-6 col-sm">
        <div class="card card-lg-sm text-center" role="region">
          <div
            class="card-header text-nowrap"
            id="games-header"
            title="Games per minute"
            aria-label="Games per minute"
          >Games / min</div>
          <div class="card-body">
            <h4 class="card-title mb-0 monospace">${games_per_minute}</h4>
          </div>
        </div>
      </div>
      <div class="col-6 col-sm">
        <div class="card card-lg-sm text-center" role="region">
          <div
            class="card-header text-nowrap"
            id="time-header"
            title="Time remaining to finish the runs"
            aria-label="Time remaining to finish the runs"
          >Time remaining</div>
          <div class="card-body">
            <h4 class="card-title mb-0 monospace">${pending_hours}h</h4>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let fetchedMachinesBefore = false;
    let machinesSkeleton = null;
    let machinesBody = null;
    async function handleRenderMachines(){
        await DOMContentLoaded();
        machinesBody = document.getElementById("machines");
        if (!machinesSkeleton) {
          machinesSkeleton = document.querySelector("#machines .ssc-wrapper").cloneNode(true);
        }
        const machinesButton = document.getElementById("machines-button");
        machinesButton?.addEventListener("click", async () => {
          await toggleMachines();
        })
        if (${str(machines_shown).lower()})
          await renderMachines();
      }

    async function renderMachines() {
      await DOMContentLoaded();
      if (fetchedMachinesBefore) {
        return Promise.resolve();
      }
      try {
        if (document.querySelector("#machines .retry")) {
          machinesBody.replaceChildren(machinesSkeleton);
        }
        const html = await fetchText("/tests/machines");
        machinesBody.replaceChildren();
        machinesBody.insertAdjacentHTML("beforeend", html);
        const machinesTbody = document.querySelector("#machines tbody");
        let newMachinesCount = machinesTbody?.childElementCount;

        if (newMachinesCount === 1) {
          const noMachines = document.getElementById("no-machines");
          if (noMachines) newMachinesCount = 0;
        }

        const countSpan = document.getElementById("workers-count");
        countSpan.textContent = `Workers - ${"${newMachinesCount}"} machines`;
        fetchedMachinesBefore = true;
      } catch (error) {
        console.log("Request failed: " + error);
        machinesBody.replaceChildren();
        createRetryMessage(machinesBody, renderMachines);
      }
    }

    async function toggleMachines() {
      const button = document.getElementById("machines-button");
      const active = button.textContent.trim() === "Hide";
      if (active) {
        button.textContent = "Show";
      }
      else {
        button.textContent = "Hide";
        await renderMachines();
      }

      document.cookie =
        "machines_state" + "=" + button.textContent.trim() + "; max-age=${60 * 60}; SameSite=Lax";
    }

    handleRenderMachines();
  </script>

  <h4>
    <a id="machines-button" class="btn btn-sm btn-light border"
      data-bs-toggle="collapse"
      href="#machines"
      role="button"
      aria-expanded=${'true' if machines_shown else 'false'}
      aria-controls="machines">
      ${'Hide' if machines_shown else 'Show'}
    </a>
    <span id="workers-count">
      Workers - ${machines_count} machines
    </span>
  </h4>
  <%
    height = str(machines_count * 37) + "px"
    min_height = str(37) + "px"
    max_height = str(34.7) + "vh"
  %>
  <section id="machines"
      class="overflow-auto ${'collapse show' if machines_shown else 'collapse'}"
      aria-labelledby="machines-button" aria-live="polite">
      <div class="ssc-card ssc-wrapper">
        <div class="ssc-head-line"></div>
        <div
          class="ssc-square"
          style="height: clamp(${min_height}, ${height}, ${max_height});">
        </div>
      </div>
  </section>
% endif

<%include file="run_tables.mak"/>
