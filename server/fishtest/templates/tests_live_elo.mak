<%inherit file="base.mak"/>

<link rel="stylesheet"
      href="/css/live_elo.css?2&v=${cache_busters['css/live_elo.css']}"
      integrity="sha384-${cache_busters['css/live_elo.css']}"
      crossorigin="anonymous" />

<script>
  document.title = 'Live Elo - ${page_title} | Stockfish Testing';
  const test_id = "${str(run['_id'])}";
</script>

<div class="container">
  <h2>Live Elo for SPRT test <a href="/tests/view/${str(run['_id'])}">${str(run['_id'])}</a></h2>

  <div class="row">
    <div class="col-12 d-flex justify-content-center align-items-center flex-column flex-sm-row" >
      <div id="LLR_chart_div"></div>
      <div style="width: 1em"></div>
      <div id="LOS_chart_div"></div>
      <div style="width: 1em"></div>
      <div id="ELO_chart_div"></div>
    </div>
    <h4>Details</h4>
    <div class="error" id="error"></div>
    <div class="col-12 table-responsive-lg">
      <table
        id="data"
        class="table table-striped table-sm"
        style="visibility: hidden">
        <tr>
          <td>Commit</td>
          <td id="commit"></td>
        </tr>
        <tr>
          <td>Info</td>
          <td id="info"></td>
        </tr>
        <tr>
          <td>Submitter</td>
          <td id="username"></td>
        </tr>
        <tr>
          <td>TC</td>
          <td id="tc"></td>
        </tr>
        <tr>
          <td>SPRT</td>
          <td id="sprt"></td>
        </tr>
        <tr>
          <td>LLR</td>
          <td id="LLR"></td>
        </tr>
        <tr>
          <td>Elo</td>
          <td id="elo"></td>
        </tr>
        <tr>
          <td>LOS</td>
          <td id="LOS"></td>
        </tr>
        <tr>
          <td>Games</td>
          <td id="games"></td>
        </tr>
      </table>
    </div>
  </div>
</div>
<script src="https://www.gstatic.com/charts/loader.js"></script>
<script src="/js/live_elo.js?v=${cache_busters['js/live_elo.js']}"
        integrity="sha384-${cache_busters['js/live_elo.js']}"
        crossorigin="anonymous"></script>
