<%inherit file="base.mak"/>

<script src="https://www.gstatic.com/charts/loader.js"></script>

<script src="/js/live_elo.js?v=${cache_busters['js/live_elo.js']}"
        integrity="sha384-${cache_busters['js/live_elo.js']}"
        crossorigin="anonymous"
></script>

<script>
  document.title = "Live Elo - ${page_title} | Stockfish Testing";
  const testId = "${str(run['_id'])}";
  followLive(testId);
</script>

<h2>Live Elo for SPRT test <a href="/tests/view/${str(run['_id'])}" aria-label="View test ${str(run['_id'])}">${str(run['_id'])}</a></h2>

<div class="form-check form-switch mb-3">
  <input class="form-check-input" type="checkbox" id="auto-refresh-switch" checked>
  <label class="form-check-label" for="auto-refresh-switch">Enable auto-refresh (updates every 20 seconds)</label>
</div>

<div class="row">
  <div class="col-12 d-flex justify-content-center align-items-center flex-column flex-sm-row">
    <div id="LLR_chart_div" aria-label="LLR Chart" role="img"></div>
    <div style="width: 1em"></div>
    <div id="LOS_chart_div" aria-label="LOS Chart" role="img"></div>
    <div style="width: 1em"></div>
    <div id="ELO_chart_div" aria-label="Elo Chart" role="img"></div>
  </div>
  <h4 id="live_details">Details</h4>
  <div class="col-12 table-responsive-lg">
    <table
      id="data"
      class="details-table table table-striped table-sm"
      style="visibility: hidden"
      aria-labelledby="live_details"
      aria-live="polite"
      role="presentation"
    >
      <thead></thead>
      <tbody>
        <tr>
          <td>Commit</td>
          <td>
            <a href="#" id="commit" target="_blank" rel="noopener noreferrer" aria-label="Commit link"></a>
          </td>
        </tr>
        <tr>
          <td>Info</td>
          <td id="info" aria-label="Information"></td>
        </tr>
        <tr>
          <td>Submitter</td>
          <td>
            <a href="#" id="username" aria-label="Submitter username"></a>
          </td>
        </tr>
        <tr>
          <td>TC</td>
          <td id="tc" aria-label="Time Control"></td>
        </tr>
        <tr>
          <td>SPRT</td>
          <td id="sprt" aria-label="SPRT details"></td>
        </tr>
        <tr>
          <td>LLR</td>
          <td id="LLR" aria-label="LLR details"></td>
        </tr>
        <tr>
          <td>Elo</td>
          <td id="elo" aria-label="Elo details"></td>
        </tr>
        <tr>
          <td>LOS</td>
          <td id="LOS" aria-label="LOS details"></td>
        </tr>
        <tr>
          <td>Games</td>
          <td id="games" aria-label="Games details"></td>
        </tr>
        <tr>
          <td>Pentanomial</td>
          <td id="pentanomial" aria-label="Pentanomial details"></td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
