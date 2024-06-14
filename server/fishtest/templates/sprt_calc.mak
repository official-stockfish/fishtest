<%inherit file="base.mak"/>

<script>
  document.title = "Chess SPRT Calculator | Stockfish Testing";
</script>

<h2>Chess SPRT Calculator</h2>

<form id="parameters" class="row">
  <div class="col-12 col-md-auto mb-3">
    <label for="elo-model" class="form-label">Elo model</label>
    <select id="elo-model" class="form-select">
      <option>Normalized</option>
      <option>Logistic</option>
    </select>
  </div>
  <div class="col-6 col-md-auto mb-3">
    <label for="elo-0" class="form-label">Elo0</label>
    <input
      id="elo-0"
      class="form-control number no-arrows"
      type="number"
      step="0.1"
      min="-10"
      max="10"
    >
  </div>
  <div class="col-6 col-md-auto mb-3">
    <label for="elo-1" class="form-label">Elo1</label>
    <input
      id="elo-1"
      class="form-control number no-arrows"
      type="number"
      step="0.1"
      min="-10"
      max="10"
    >
  </div>
  <div class="col-6 col-md-auto mb-3">
    <label for="draw-ratio" class="form-label">Draw ratio</label>
    <input
      id="draw-ratio"
      class="form-control number no-arrows"
      type="number"
      step="0.01"
      min="0"
      max="1"
    >
  </div>
  <div class="col-6 col-md-auto mb-3">
    <label for="rms-bias" class="form-label">RMS bias</label>
    <input
      id="rms-bias"
      class="form-control number no-arrows"
      type="number"
      min="0"
    >
  </div>
  <div class="col-12 col-md-auto mb-3 d-flex align-items-end">
    <input
      class="btn btn-success w-100"
      type="button"
      value="Calculate"
      onclick="drawCharts()"
    >
  </div>
</form>
<div>
  <hr>
</div>
<div id="mouse_screen" class="row g-0">
  <div id="pass_prob_chart_div" class="sprt-calc-chart col-12 col-md-6"></div>
  <div id="expected_chart_div" class="sprt-calc-chart col-12 col-md-6"></div>
</div>
<div id="sprt-calc-description">
  <ul>
    <li>
      The fields <b>Elo0</b> and <b>Elo1</b> represent the bounds for an
      <a href="https://en.wikipedia.org/wiki/Sequential_probability_ratio_test"
        >SPRT test</a
      >
      with &alpha;=&beta;=0.05. In other words, if the true Elo is less than
      Elo0 then the probability of the test passing is less than 5%. On the
      other hand if the true Elo is more than Elo1 then the pass probability is
      more than 95%.
    </li>
    <li>
      If the Elo model is <b>Logistic</b> then the pass/fail probabilities are
      independent of the auxiliary data <em>Draw ratio</em> and
      <em>RMS bias</em>. On the other hand if the Elo model is
      <b>Normalized</b> then it is the expected duration of the test that is
      independent of the auxiliary data.
    </li>
    <li>
      The <b>Draw ratio</b> is mainly a function of the opening book and the
      time control. The draw ratio can be found on the
      <em>live_elo page</em>
      of a test with typical URL
      <a
        href="https://montychess.org/tests/live_elo/5e15b3e061fe5f83a67dd926"
        >https://montychess.org/tests/live_elo/5e15b3e061fe5f83a67dd926</a
      >
      or the <em>raw statistics page</em> with typical URL
      <a
        href="http://montychess.org/tests/stats/5e15b3e061fe5f83a67dd926"
        >http://montychess.org/tests/stats/5e15b3e061fe5f83a67dd926</a
      >.
    </li>
    <li>
      The <b>RMS bias</b> is the Root Mean Square of the biases of the openings
      in the book where the <em>bias of an opening</em> is defined as the
      conversion to Elo (using the standard logistic formula) of the expected
      score for white between engines of "equal strength". Explicitly the RMS
      bias is the square root of the average of the squares of the biases
      expressed in Elo. The RMS bias appears to be relatively independent of
      time control and Elo differences. It can be found at the bottom of the raw
      statistics page, but it should be noted that the value reported there is
      only reliable for tests that have at least a few tens of thousands of
      games. Also note that for non-functional simplifications or small
      speed-ups, correlations between games in a game pair cause the (virtual)
      RMS bias to be much higher than normal.
    </li>
    <li>
      More information on the mathematics behind this web page can be found on
      the
      <a
        href="https://github.com/official-stockfish/fishtest/wiki/Fishtest-mathematics"
        >Fishtest wiki</a
      >.
    </li>
    <li>
      The original version of this web page was written by
      <a href="https://github.com/hwiechers">Henri Wiechers</a>.
    </li>
  </ul>
</div>

<script src="https://www.gstatic.com/charts/loader.js"></script>

<script
  src="/js/sprt.js?v=${cache_busters['js/sprt.js']}"
  integrity="sha384-${cache_busters['js/sprt.js']}"
  rossorigin="anonymous"
></script>

<script
  src="/js/calc.js?1&v=${cache_busters['js/calc.js']}"
  integrity="sha384-${cache_busters['js/calc.js']}"
  crossorigin="anonymous"
></script>
