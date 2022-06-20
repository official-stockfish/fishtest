<%inherit file="base.mak"/>

<style>
  .form-control.number {
    width: 4em;
    text-align: right;
    margin-right: 0.5em;
  }
  .chart-div {
    height: 500px;
  }
  ul {
    word-break: break-word;
  }
</style>

<script>
  document.title = 'Chess SPRT Calculator | Stockfish Testing';
</script>

<h2>Chess SPRT Calculator</h2>

<div class="row">
  <form id="parameters" class="form-inline row">
    <div class="col-auto form-group">
      <label for="elo-model">Elo model</label>
      <select id="elo-model" class="form-select">
        <option>Normalized</option>
        <option>Logistic</option>
      </select>
    </div>
    <div class="col-auto form-group">
      <label for="elo-0">Elo0</label>
      <input id="elo-0" class="form-control number" />
    </div>
    <div class="col-auto form-group">
      <label for="elo-1">Elo1</label>
      <input id="elo-1" class="form-control number" />
    </div>
    <div class="col-auto form-group">
      <label for="draw-ratio">Draw ratio</label>
      <input id="draw-ratio" class="form-control number" />
    </div>
    <div class="col-auto form-group">
      <label for="rms-bias">RMS bias</label>
      <input id="rms-bias" class="form-control number" />
    </div>
    <div class="col-auto form-group position-relative">
      <input
        class="btn btn-success position-absolute bottom-0"
        type="button"
        value="Calculate"
        onclick="draw_charts();"
      />
    </div>
  </form>
  <div>
    <hr />
  </div>
  <div id="mouse_screen" class="row g-0">
    <div id="pass_prob_chart_div" class="chart-div col-12 col-md-6"></div>
    <div id="expected_chart_div" class="chart-div col-12 col-md-6"></div>
  </div>
  <div>
    <ul>
      <li>
        The fields <b>Elo0</b> and <b>Elo1</b> represent the bounds for an
        <a
          href="https://en.wikipedia.org/wiki/Sequential_probability_ratio_test"
          >SPRT test</a
        >
        with &alpha;=&beta;=0.05. In other words, if the true Elo is less
        than Elo0 then the probability of the test passing is less
        than&nbsp;5%. On the other hand if the true Elo is more than Elo1
        then the pass probablility is more than&nbsp;95%.
      </li>
      <li>
        If the Elo model is <b>Logistic</b> then the pass/fail probabilities
        are independent of the auxiliary data <em>Draw ratio</em> and
        <em>RMS bias</em>. On the other hand if the Elo model is
        <b>Normalized</b> then it is the expected duration of the test that
        is independent of the auxiliary data.
      </li>
      <li>
        The <b>Draw ratio</b> is mainly a function of the opening book and
        the time control. The draw ratio can be found on the
        <em>live_elo page</em>
        of a test with typical URL
        <a
          href="http://tests.stockfishchess.org/html/live_elo.html?5e15b3e061fe5f83a67dd926"
          >http://tests.stockfishchess.org/html/live_elo.html?5e15b3e061fe5f83a67dd926</a
        >
        or the <em>raw statistics page</em> with typical URL
        <a
          href="http://tests.stockfishchess.org/tests/stats/5e15b3e061fe5f83a67dd926"
          >http://tests.stockfishchess.org/tests/stats/5e15b3e061fe5f83a67dd926</a
        >.
      </li>
      <li>
        The <b>RMS bias</b> is the Root Mean Square of the biases of the
        openings in the book where the <em>bias of an opening</em> is
        defined as the conversion to Elo (using the standard logistic
        formula) of the expected score for white between engines of "equal
        strength". Explicitly the RMS bias is the square root of the average
        of the squares of the biases expressed in Elo. The RMS bias appears
        to be relatively independent of time control and Elo differences. It
        can be found at the bottom of the raw statistics page, but it should
        be noted that the value reported there is only reliable for tests
        that have at least a few tens of thousands of games. Also note that
        for non-functional simplifications or small speed-ups, correlations
        between games in a game pair cause the (virtual) RMS bias to be much
        higher than normal.
      </li>
      <li>
        More information on the mathematics behind this web page can be
        found on the
        <a
          href="https://github.com/glinscott/fishtest/wiki/Fishtest-mathematics"
          >Fishtest wiki</a
        >.
      </li>
      <li>
        The original version of this web page was written by
        <a href="https://github.com/hwiechers">Henri Wiechers</a>.
      </li>
    </ul>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/js-url/2.5.3/url.min.js"
        integrity="sha512-YlfjbwbVZGikywbRiBmrMZh4gkigfbNHBLi8ZVQUMCGn/5Fnc700QDiZ3OC4WY2peX1nrqUbCcHyOyvKR8hwNA=="
        crossorigin="anonymous"
        referrerpolicy="no-referrer"></script>
<script src="https://www.gstatic.com/charts/loader.js"></script>
<script src="/js/sprt.js?v=${cache_busters['js/sprt.js']}"
            integrity="sha384-${cache_busters['js/sprt.js']}"
            crossorigin="anonymous"></script>
<script src="/js/calc.js?1&v=${cache_busters['js/calc.js']}"
            integrity="sha384-${cache_busters['js/calc.js']}"
            crossorigin="anonymous"></script>
