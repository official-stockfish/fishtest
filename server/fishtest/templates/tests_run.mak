<%inherit file="base.mak"/>

<%
from fishtest.util import format_bounds
elo_model="normalized"
fb=lambda e0,e1:format_bounds(elo_model,e0,e1)

tc=args.get('tc','10+0.1')
new_tc=args.get('new_tc',tc)

if new_tc!=tc:
  is_odds=True
else:
  is_odds=False
%>
<style>
  input[type=number].no-arrows::-webkit-inner-spin-button,
  input[type=number].no-arrows::-webkit-outer-spin-button {
      -webkit-appearance: none;
      -moz-appearance: none;
      appearance: none;
      margin: 0;
  }

  input[type=number] {
    -moz-appearance: textfield;
  }

  .main .flex-row {
    display: flex;
    align-items: center;
    margin: 10px 0;
  }

  .field-label {
    font-size: 12px;
    margin: 0;
    text-align: right;
    padding-right: 15px;
    width: 120px;
  }

  .field-label.leftmost {
    width: 100px;
    flex-shrink: 0;
  }

  .rightmost {
    margin-left: auto;
  }

  .third-size {
    width: 107px;
    flex-shrink: 0;
  }

  input.quarter-size {
    margin-right: 10px;
    width: 70px;
    flex-shrink: 0;
  }

  #create-new-test {
    width: 720px;
    margin: 7px auto;
    padding-right: 30px;
  }

  #create-new-test input, #create-new-test select {
    margin: 0;
  }

  .quarter-size {
    width: 80px;
    flex-shrink: 0;
  }

  .choose-test-type .btn {
    width: 98px;
  }

  #create-new-test label:hover {
    cursor: text;
  }

  #create-new-test textarea {
    min-height: 40px;
    margin: 0;
    width: 100%;
  }

  section.test-settings input {
    width: 235px;
  }
</style>

<script>
  document.title = 'Create New Test | Stockfish Testing';
</script>

<header style="text-align: center; padding-top: 7px">
  <h2>Create New Test</h2>
  <section class="instructions" style="margin-bottom: 35px">
    Please read the
    <a href="https://github.com/glinscott/fishtest/wiki/Creating-my-first-test">Testing Guidelines</a>
    before creating your test.
  </section>
</header>

<div class="overflow-auto">
  <form id="create-new-test" action="${request.url}" method="POST">
    <section class="test-settings" style="margin-bottom: 35px">
      <div class="flex-row">
        <label class="field-label leftmost">Test type</label>
        <div class="btn-group btn-group-sm text-nowrap choose-test-type">
          <div class="btn border" id="fast_test"
              data-options='{"tc": "10+0.1", "new_tc": "10+0.1", "threads": 1, "options": "Hash=16 Use NNUE=true", "bounds": "standard STC"}'>
            Short (STC)
          </div>
          <div class="btn border" id="slow_test"
              data-options='{"tc": "60+0.6", "new_tc": "60+0.6", "threads": 1, "options": "Hash=64 Use NNUE=true", "bounds": "standard LTC"}'>
            Long (LTC)
          </div>
          <div class="btn border" id="fast_smp_test"
              data-options='{"tc": "5+0.05", "new_tc": "5+0.05", "threads": 8, "options": "Hash=64 Use NNUE=true", "bounds": "standard STC"}'>
            SMP (STC)
          </div>
          <div class="btn border" id="slow_smp_test"
              data-options='{"tc": "20+0.2", "new_tc": "20+0.2", "threads": 8, "options": "Hash=256 Use NNUE=true", "bounds": "standard LTC"}'>
            SMP (LTC)
          </div>
        </div>
        <button type="submit" class="btn btn-primary btn-sm rightmost" id="submit-test"
                style="width: 180px">
          Submit test
        </button>
      </div>

      <div class="flex-row">
        <label class="field-label leftmost">Test repo</label>
        <div class="input-group input-group-sm">
          <input type="text" name="tests-repo" style="width: 100%;"
                class="form-control"
                value="${args.get('tests_repo', tests_repo)}" ${'readonly' if is_rerun else ''}
                placeholder="https://github.com/username/Stockfish">
        </div>
      </div>

      <div class="flex-row input-group input-group-sm">
        <label class="field-label leftmost">Test branch</label>
        <input type="text" name="test-branch"
              id="test-branch" class="form-control"
              value="${args.get('new_tag', '')}" ${'readonly' if is_rerun else ''}
              placeholder="Your test branch name">

        <label class="field-label">Base branch</label>
        <input type="text" name="base-branch"
              id="base-branch" class="form-control"
              value="${args.get('base_tag', 'master')}" ${'readonly' if is_rerun else ''}>
      </div>

      <div class="flex-row input-group input-group-sm">
        <label class="field-label leftmost">Test signature</label>
        <input type="number" name="test-signature"
              id="test-signature" class="no-arrows form-control" onwheel="this.blur()"
              placeholder="Defaults to last commit message"
              value="${args.get('new_signature', '')}" ${'readonly' if is_rerun else ''}>

        <label class="field-label">Base signature</label>
        <input type="number" name="base-signature"
              id="base-signature" class="no-arrows form-control" onwheel="this.blur()"
              value="${args.get('base_signature', bench)}" ${'readonly' if is_rerun else ''}>
      </div>

      <div class="flex-row input-group input-group-sm">
        <label class="field-label leftmost">Test options</label>
        <input type="text" name="new-options"
              class="form-control"
              value="${args.get('new_options', 'Hash=16 Use NNUE=true')}">

        <label class="field-label">Base options</label>
        <input type="text" name="base-options"
              class="form-control"
              value="${args.get('base_options', 'Hash=16 Use NNUE=true')}">
      </div>

      <div class="flex-row">
        <label class="field-label leftmost">Info</label>
        <div class="input-group input-group-sm">
          <textarea name="run-info" placeholder="Defaults to commit message"
                    class="form-control"
                    rows="3">${args.get('info', '')}</textarea>
        </div>
      </div>
    </section>

    <section id="stop-rule" style="min-height: 100px">
      <div class="flex-row">
        <label class="field-label leftmost">Stop rule</label>
        <div class="btn-group btn-group-sm">
          <div class="btn btn-info border" data-stop-rule="sprt" style="width: 94px">SPRT</div>
          <div class="btn border" data-stop-rule="numgames" style="width: 100px">Num games</div>
          <div class="btn border" data-stop-rule="spsa" style="width: 94px">SPSA</div>
        </div>
        <input type="hidden" name="stop_rule" id="stop_rule_field" value="sprt" />

        <div class="rightmost"
            style="display: flex; align-items: center">
          <label class="field-label stop_rule spsa numgames"
                style="${'display: none' if (args.get('sprt') or not is_rerun) else ''}"># games</label>
          <div class="input-group input-group-sm" style="width: 115px">
            <input type="number" name="num-games" min="1000" step="1000"
                  class="stop_rule spsa numgames third-size no-arrows form-control"
                  value="${args.get('num_games', 60000)}"
                  style="${'display: none' if (args.get('sprt') or not is_rerun) else ''}" />
          </div>
        </div>
      </div>

      <div class="flex-row stop_rule sprt">
        <input type="hidden" name="elo_model" id="elo_model_field" value=${elo_model} />
        <label class="field-label leftmost stop_rule sprt">SPRT bounds</label>

        <div class="input-group input-group-sm">
          <select name="bounds" class="form-select stop_rule sprt" style="width: 246px">
            <option value="standard STC">Standard STC ${fb(0.0, 2.0)}</option>
            <option value="standard LTC">Standard LTC ${fb(0.5, 2.5)}</option>
            <option value="regression STC">Non-regression STC ${fb(-1.75, 0.25)}</option>
            <option value="regression LTC">Non-regression LTC ${fb(-1.75, 0.25)}</option>
            <option value="custom" ${is_rerun and 'selected'}>Custom bounds...</option>
          </select>
        </div>

        <label class="field-label sprt custom_bounds"
              style="${args.get('sprt') or 'display: none'}">SPRT Elo0</label>
        <input type="number" step="0.05" name="sprt_elo0"
              class="sprt custom_bounds no-arrows form-control"
              ## The bounds handling should be cleaned up...
              value="${args.get('sprt', {'elo0': 0.0})['elo0']}"
              style="width: 90px; ${args.get('sprt') or 'display: none'}" />

        <label class="field-label sprt custom_bounds rightmost"
              style="${args.get('sprt') or 'display: none'}">SPRT Elo1</label>
        <input type="number" step="0.05" name="sprt_elo1"
              class="sprt custom_bounds no-arrows form-control"
              value="${args.get('sprt', {'elo1': 2.0})['elo1']}"
              style="width: 90px; ${args.get('sprt') or 'display: none'}" />
      </div>

      <div class="flex-row input-group input-group-sm stop_rule spsa"
          style="${args.get('spsa') or 'display: none'}">
        <label class="field-label leftmost">SPSA A ratio</label>
        <input type="number" min="0" max="1" step="0.001" name="spsa_A"
              class="third-size no-arrows form-control"
              value="${args.get('spsa', {'A': '0.1'})['A']}" />

        <label class="field-label rightmost">SPSA Alpha</label>
        <input type="number" min="0" step="0.001" name="spsa_alpha"
              class="third-size no-arrows form-control"
              value="${args.get('spsa', {'alpha': '0.602'})['alpha']}" />

        <label class="field-label" style="margin-left: 7px">SPSA Gamma</label>
        <input type="number" min="0" step="0.001" name="spsa_gamma"
              class="third-size no-arrows form-control"
              value="${args.get('spsa', {'gamma': '0.101'})['gamma']}" />
      </div>

      <div class="flex-row stop_rule spsa"
          style="${args.get('spsa') or 'display: none'}">
        <label class="field-label leftmost">SPSA parameters</label>
        <div class="input-group input-group-sm">
          <textarea name="spsa_raw_params"
                    class="form-control"
                    rows="2">${args.get('spsa', {'raw_params': ''})['raw_params']}</textarea>
        </div>
      </div>
      <div class="flex-row stop_rule spsa"
          style="${args.get('spsa') or 'display: none'}">
        <label class="field-label leftmost">Autoselect</label>
        <input type="checkbox" id="enable" class="form-check-input" />

        &nbsp; &nbsp;
        <input type="button" class="btn btn-info btn-sm" 
        data-bs-toggle="collapse" href="#info_display" role="button"
        aria-expanded="false" aria-controls="info_display" id="info" value="Info"/>
      </div>
      <div class="flex-row stop_rule spsa">
        <label class="field-label leftmost"></label>
        <div id="info_display" class="collapse collapse-horizontal" style="border-style:solid;">
          <i>
          Checking this option will rewrite the hyperparameters furnished by
          the tuning code in Stockfish in such a way that the SPSA tune will finish
          within 0.5 Elo from the optimum (with 95% probability) assuming
          the function <span style="white-space:
          nowrap;">'parameters-&gt;Elo'</span> is quadratic and varies 2 Elo
          per parameter over each specified parameter interval. The
          hyperparameters are relatively conservative and their performance
          will degrade gracefully if the actual variation is different.  The
          theoretical basis for choosing the hyperparameters is given in
          this document:
          <a href=https://github.com/vdbergh/spsa_simul/blob/master/doc/theoretical_basis.pdf target=_blank>
          https://github.com/vdbergh/spsa_simul/blob/master/doc/theoretical_basis.pdf</a>. The
          formulas can be checked by simulation which is done here:
          <a href=https://github.com/vdbergh/spsa_simul target=_blank>
          https://github.com/vdbergh/spsa_simul</a>.
          Currently this option
          should be used with the book 'UHO_XXL_+0.90_+1.19.epd'
          and in addition the option should not be used with nodestime or with more than one thread.
          </i>
        </div>
      </div>
    </section>

    <section id="worker-and-queue-options">
      <div class="flex-row input-group input-group-sm">
        <label class="field-label leftmost">Threads</label>
        <input type="number" min="1" name="threads"
              class="quarter-size no-arrows form-control" style="max-width: 40px"
              value="${args.get('threads', 1)}" />

        <label class="field-label" name="tc_label"
              style="width: 50px; margin-left: 10px">TC</label>
        <input type="text" name="tc" class="quarter-size form-control"
              style="min-width: 70px"
              value="${args.get('tc', '10+0.1')}" />
        <label class="field-label" name="new_tc_label"
              style="width: 70px; padding-right: 5px; display: none">Test&nbsp;TC</label>
        <input type="text" name="new_tc"
              class="quarter-size form-control"
              style="min-width: 70px; display: none"
              value="${args.get('new_tc', '10+0.1')}" />
        <label class="field-label"
              style="width: 50px; margin-left: 10px; padding-right: 5px">Priority</label>
        <input type="number" name="priority"
              class="quarter-size no-arrows form-control" style="max-width: 40px"
              value="${args.get('priority', 0)}" />

        <label class="field-label" style="width: 70px; margin-left: 10px">Throughput</label>
        <select name="throughput" class="quarter-size form-select form-select-sm">
          <option value="10">10%</option>
          <option value="25">25%</option>
          <option value="50">50%</option>
          <option selected="selected" value="100">100%</option>
          <option style="color:red" value="200">200%</option>
        </select>
      </div>
      <div class="flex-row input-group input-group-sm">
        <label class="field-label leftmost">Book</label>
        <input type="text" name="book"
              id="book" class="form-control" style="width: 229px"
              value="${args.get('book', 'UHO_XXL_+0.90_+1.19.epd')}" />

        <label class="field-label book-depth"
              style="width: 87px; display: none">Book depth</label>
        <input type="number" min="1" name="book-depth"
              class="quarter-size no-arrows book-depth"
              style="display: none"
              value="${args.get('book_depth', 8)}" />
      </div>

      <div class="flex-row">
        <label class="field-label leftmost">Advanced</label>

        <input type="checkbox" name="auto-purge"
              id="checkbox-auto-purge" class="form-check-input"
              value="False" />
        <label style="margin-left: 10px; margin-right: 10px"
              for="checkbox-auto-purge">Auto-purge</label>

        <input type="checkbox" name="odds"
              id="checkbox-time-odds" class="form-check-input" style="margin-left: 27px"
              ${'checked' if is_odds else ''}>
        <label style="margin-left: 10px"
              for="checkbox-time-odds">Time odds</label>
        <input type="checkbox" name="adjudication"
              id="checkbox-adjudication" class="form-check-input" style="margin-left: 27px"
              ${'checked' if not args.get("adjudication", True) else ''}>
        <label style="margin-left: 10px"
              for="checkbox-adjudication">Disable adjudication</label>
      </div>
    </section>

    % if 'resolved_base' in args:
        <input type="hidden" name="resolved_base" value="${args['resolved_base']}">
        <input type="hidden" name="resolved_new" value="${args['resolved_new']}">
        <input type="hidden" name="msg_base" value="${args.get('msg_base', '')}">
        <input type="hidden" name="msg_new" value="${args.get('msg_new', '')}">
    % endif

    % if is_rerun:
        <input type="hidden" name="rescheduled_from" value="${rescheduled_from}">
    % endif
  </form>
</div>

<script>
  let form_submitted = false;
  window.onpageshow = function() {
    // If pressing the 'back' button to get back to this page, make sure
    // the submit test button is enabled again.
    // make sure form_submitted is set back to false
    form_submitted = false;
    document.querySelector('#submit-test').removeAttribute('disabled');
    document.querySelector('#submit-test').innerText = 'Submit test';
    // Also make sure that the odds TC fields have the right visibility.
    update_odds(document.querySelector('#checkbox-time-odds'));
  };

  const preset_bounds = {
    'standard STC': [ 0.0, 2.0],
    'standard LTC': [ 0.5, 2.5],
    'regression STC': [-1.75, 0.25],
    'regression LTC': [-1.75, 0.25],
  };

  function update_sprt_bounds(selected_bounds_name) {
    if (selected_bounds_name === "custom") {
      document
        .querySelectorAll(".custom_bounds")
        .forEach((bound) => (bound.style.display = ""));
    } else {
      document
        .querySelectorAll(".custom_bounds")
        .forEach((bound) => (bound.style.display = "none"));
      const bounds = preset_bounds[selected_bounds_name];
      document.querySelector("input[name=sprt_elo0]").value = bounds[0];
      document.querySelector("input[name=sprt_elo1]").value = bounds[1];
    }
  }

  function update_book_depth_visibility(book) {
    if (book.match('\.pgn$')) {
      document.querySelector('.book-depth').style.display = "";
    } else {
      document.querySelector('.book-depth').style.display = "none";
    }
  }

  document
    .querySelector("select[name=bounds]")
    .addEventListener("change", function () {
      update_sprt_bounds(this.value);
    });

  let initial_base_branch = document.querySelector("#base-branch").value;
  let initial_base_signature = document.querySelector("#base-signature").value;
  let spsa_do_not_save = false;

  document.querySelectorAll(".btn-group .btn").forEach((btn) =>
    btn.addEventListener("click", function () {
      if (!spsa_do_not_save) {
        initial_base_branch = document.querySelector("#base-branch").value;
        initial_base_signature = document.querySelector("#base-signature").value;
      }
      const btn = this;
      this.parentElement
        .querySelectorAll(".btn")
        .forEach((btn) => btn.classList.remove("btn-info"));
      this.classList.add("btn-info");

      // choose test type - STC, LTC - sets preset values
      let stopRule = null;
      let testOptions = null;
      if (btn.dataset.stopRule) stopRule = btn.dataset.stopRule;
      if (btn.dataset.options) testOptions = btn.dataset.options;

      if (testOptions) {
        const { tc, new_tc, threads, options, bounds } = JSON.parse(testOptions);
        document.querySelector("input[name=tc]").value = tc;
        document.querySelector("input[name=new_tc]").value = new_tc;
        document.querySelector("input[name=threads]").value = threads;
        document.querySelector("input[name=new-options]").value = (
          options.replace(" Use NNUE=true", "") +
          " " +
          document
            .querySelector("input[name=new-options]")
            .value.replace(/Hash=[0-9]+ ?/, "")
        ).replace(/ $/, "");
        document.querySelector("input[name=base-options]").value = (
          options.replace(" Use NNUE=true", "") +
          " " +
          document
            .querySelector("input[name=base-options]")
            .value.replace(/Hash=[0-9]+ ?/, "")
        ).replace(/ $/, "");
        document.querySelector("select[name=bounds]").value = bounds;
        update_sprt_bounds(bounds);
        do_spsa_work();
      }

      // stop-rule buttons - SPRT, Num games, SPSA - toggles stop-rule fields
      if (stopRule) {
        const testBranchHandler = () =>
          (document.querySelector("#base-branch").value =
            document.querySelector("#test-branch").value);
        const testSignatureHandler = () =>
          (document.querySelector("#base-signature").value =
            document.querySelector("#base-branch").value);
        document
          .querySelectorAll(".stop_rule")
          .forEach((el) => (el.style.display = "none"));
        document.querySelector("#stop_rule_field").value = stopRule;
        document
          .querySelectorAll("." + stopRule)
          .forEach((el) => (el.style.display = ""));
        % if not is_rerun:
            if (stopRule === "spsa") {
              // base branch and test branch should be the same for SPSA tests
              document.querySelector("#base-branch").setAttribute("readonly", "true");
              document.querySelector("#base-branch").value =
                document.querySelector("#test-branch").value;
              document
                .querySelector("#test-branch")
                .addEventListener("input", testBranchHandler);
              document
                .querySelector("#base-signature")
                .setAttribute("readonly", "true");
              document.querySelector("#base-signature").value =
                document.querySelector("#test-signature").value;
              document
                .querySelector("#test-signature")
                .addEventListener("input", testSignatureHandler);
              spsa_do_not_save = true;
            } else {
              document.querySelector("#base-branch").removeAttribute("readonly");
              document.querySelector("#base-branch").value = initial_base_branch;
              document.querySelector("#base-signature").removeAttribute("readonly");
              document.querySelector("#base-signature").value =
                initial_base_signature;
              document
                .querySelector("#test-branch")
                .removeEventListener("input", testBranchHandler);
              document
                .querySelector("#test-signature")
                .removeEventListener("input", testSignatureHandler);
              spsa_do_not_save = false;
            }
        % endif
        if (stopRule === "sprt") {
          update_sprt_bounds(document.querySelector("select[name=bounds]").value);
        }
      }
    })
  );

  // Only .pgn book types have a book_depth field
  update_book_depth_visibility(document.querySelector("#book").value);
  document.querySelector("#book").addEventListener("input", function () {
    update_book_depth_visibility(this.value);
  });

  document
    .querySelector("#create-new-test")
    .addEventListener("submit", function (e) {
      const ret = do_spsa_work(); // Last check that all spsa data are consistent.
      if (!ret) {
        return false;
      }
      if (form_submitted) {
        // Don't allow submitting the form more than once
        e.preventDefault();
        return;
      }
      form_submitted = true;
      document.querySelector("#submit-test").setAttribute("disabled", true);
      document.querySelector("#submit-test").innerText = "Submitting test...";
    });

  const is_rerun = ${'true' if is_rerun else 'false'};
  if (is_rerun) {
    // Select the correct fields by default for re-runs
    const tc = '${args.get('tc')}';
    if (tc === "10+0.1") {
      document
        .querySelectorAll(".choose-test-type .btn")
        .forEach((el) => el.classList.remove("btn-info"));
      document.querySelector(".btn#fast_test").classList.add("btn-info");
    } else if (tc === "60+0.6") {
      document
        .querySelectorAll(".choose-test-type .btn")
        .forEach((el) => el.classList.remove("btn-info"));
      document.querySelector(".btn#slow_test").classList.add("btn-info");
    } else if (tc === "5+0.05") {
      document
        .querySelectorAll(".choose-test-type .btn")
        .forEach((el) => el.classList.remove("btn-info"));
      document.querySelector(".btn#fast_smp_test").classList.add("btn-info");
    } else if (tc === "20+0.2") {
      document
        .querySelectorAll(".choose-test-type .btn")
        .forEach((el) => el.classList.remove("btn-info"));
      document.querySelector(".btn#slow_smp_test").classList.add("btn-info");
    }
    % if args.get('spsa'):
        document.querySelector('.btn[data-stop-rule="spsa"]').click();
    % elif not args.get('sprt'):
        document.querySelector('.btn[data-stop-rule="numgames"]').click();
    % endif
  } else {
    // short STC test by default for new tests
    document.querySelector('.btn#fast_test').classList.add('btn-info');
    // Focus the "Test branch" field on page load for new tests
    document.querySelector('#test-branch').focus();
  }

  function update_odds(elt) {
    if (elt.checked) {
      document.querySelector('input[name=new_tc]').style.display = "block";
      document.querySelector('label[name=new_tc_label]').style.display = "block";
      document.querySelector('label[name=tc_label]').innerHTML = "Base&nbsp;TC";
    } else {
      document.querySelector('input[name=new_tc]').style.display = "none";
      document.querySelector('label[name=new_tc_label]').style.display = "none";
      document.querySelector('input[name=new_tc]').value = document.querySelector('input[name=tc]').value;
      document.querySelector('label[name=tc_label]').innerHTML = "TC";
    }
  }

  document.querySelector('#checkbox-time-odds').addEventListener("change", function() {
    update_odds(this);
  });
</script>

<script src="/js/spsa_new.js?5&?v=${cache_busters['js/spsa_new.js']}"
        integrity="sha384-${cache_busters['js/spsa_new.js']}"
        crossorigin="anonymous"></script>
<script>
  function do_spsa_work() {
    /* parsing/computing */
    if (!document.querySelector('#enable').checked) {
      return true;
    }
    const params = document.querySelector("textarea[name='spsa_raw_params']").value;
    let s = fishtest_to_spsa(params);
    if (s === null) {
      alert("Unable to parse spsa parameters.");
      return false;
    }
    /* estimate the draw ratio */
    const tc = document.querySelector("input[name='tc']").value;
    const dr = draw_ratio(tc);
    if (dr === null) {
      alert("Unable to parse time control.");
      return false;
    }
    s.draw_ratio = dr;
    s = spsa_compute(s);
    const fs = spsa_to_fishtest(s);
    /* Let's go */
    document.querySelector("input[name='spsa_A']").value = 0;
    document.querySelector("input[name='spsa_alpha']").value = 0.0;
    document.querySelector("input[name='spsa_gamma']").value = 0.0;
    document.querySelector("input[name='num-games']").value = 1000 * Math.round(s.num_games / 1000);
    document.querySelector("textarea[name='spsa_raw_params']").value = fs.trim();
    return true;
  }
  let saved_A = null;
  let saved_alpha = null;
  let saved_gamma = null;
  let saved_games = null;
  let saved_params = null;
  function do_spsa_events() {
    if (document.querySelector('#enable')["checked"]) {
      /* save old stuff */
      saved_A = document.querySelector("input[name='spsa_A']").value;
      saved_alpha = document.querySelector("input[name='spsa_alpha']").value;
      saved_gamma = document.querySelector("input[name='spsa_gamma']").value;
      saved_games = document.querySelector("input[name='num-games']").value;
      saved_params = document.querySelector("textarea[name='spsa_raw_params']").value;
      const ret = do_spsa_work();
      if (!ret) {
        document.querySelector('#enable').checked = false;
      }
    } else {
      document.querySelector("input[name='spsa_A']").value = saved_A;
      document.querySelector("input[name='spsa_alpha']").value = saved_alpha;
      document.querySelector("input[name='spsa_gamma']").value = saved_gamma;
      document.querySelector("input[name='num-games']").value = saved_games;
      document.querySelector("textarea[name='spsa_raw_params']").value = saved_params;
    }
  }
  document.querySelector('#info').addEventListener("click", function() {
    if (document.querySelector('#info').value === "Info") {
      document.querySelector('#info').value = "Hide";
    } else {
      document.querySelector('#info').value = "Info";
    }
  });
  document.querySelector('#enable').addEventListener("change", do_spsa_events);
  document.querySelector("input[name='tc']").addEventListener("input", function() {
    if (!document.querySelector('#enable').checked) {
      return;
    }
    const tc = document.querySelector("input[name='tc']").value;
    const tc_seconds = tc_to_seconds(tc);
    if (tc_seconds !== null) {
      do_spsa_work();
    }
  });
</script>
