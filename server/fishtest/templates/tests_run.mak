<%inherit file="base.mak"/>

<%
  from fishtest.util import format_bounds
  elo_model = "normalized"
  fb = lambda e0,e1:format_bounds(elo_model, e0, e1)

  base_branch = args.get('base_tag', 'master')
  latest_bench = args.get('base_signature', master_info["bench"])

  pt_version = "SF 15"
  pt_branch = "e6e324eb28fd49c1fc44b3b65784f85a773ec61c"
  pt_signature = 8129754

  tc = args.get('tc', '10+0.1')
  new_tc = args.get('new_tc', tc)

  test_book = "UHO_XXL_+0.90_+1.19.epd"
  pt_book = "8moves_v3.pgn"

  default_book = args.get('book', test_book)

  if new_tc != tc:
    is_odds = True
  else:
    is_odds = False
%>

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

<form id="create-new-test" action="${request.url}" method="POST">
  <div class="container mt-4 mb-2">
    <div class="row">
      <div class="mb-2 container d-flex justify-content-center">
        <button type="submit" class="btn btn-primary col-12 col-md-4" id="submit-test">Submit test</button>
      </div>

      <div><hr></div>

      <div>
        <div class="row">
          <div class="col-12 col-md-6 mb-2">
            <div class="row gx-1">
              <div class="mb-2">
                <label class="form-label">Test type <i class="fa-solid fa-ellipsis" role="button" data-bs-toggle="collapse" data-bs-target=".collapse-type" title="Toggle more tests"></i></label>
                <div class="list-group list-group-checkable flex-row row row-cols-2 row-cols-xl-4 g-1 text-center">
                  <div class="col">
                    <input class="list-group-item-check pe-none" type="radio" name="test-type" id="fast_test"
                      data-options='{
                        "name": "STC",
                        "tc": "10+0.1",
                        "new_tc": "10+0.1",
                        "threads": 1,
                        "options": "Hash=16 Use NNUE=true",
                        "book": "${test_book}",
                        "stop_rule": "stop-rule-sprt",
                        "bounds": "standard STC",
                        "base_branch": "${base_branch}",
                        "base_signature": ${latest_bench}
                      }'
                      checked>
                    <label class="list-group-item rounded-3" for="fast_test" title="Short time control | Single-threaded">
                      STC
                    </label>
                  </div>

                  <div class="col">
                    <input class="list-group-item-check pe-none" type="radio" name="test-type" id="slow_test"
                      data-options='{
                        "name": "LTC",
                        "tc": "60+0.6",
                        "new_tc": "60+0.6",
                        "threads": 1,
                        "options": "Hash=64 Use NNUE=true",
                        "book": "${test_book}",
                        "stop_rule": "stop-rule-sprt",
                        "bounds": "standard LTC",
                        "base_branch": "${base_branch}",
                        "base_signature": ${latest_bench}
                      }'>
                    <label class="list-group-item rounded-3" for="slow_test" title="Long time control | Single-threaded">
                      LTC
                    </label>
                  </div>

                  <div class="col">
                    <input class="list-group-item-check pe-none" type="radio" name="test-type" id="fast_smp_test"
                      data-options='{
                        "name": "STC SMP",
                        "tc": "5+0.05",
                        "new_tc": "5+0.05",
                        "threads": 8,
                        "options": "Hash=64 Use NNUE=true",
                        "book": "${test_book}",
                        "stop_rule": "stop-rule-sprt",
                        "bounds": "standard STC",
                        "base_branch": "${base_branch}",
                        "base_signature": ${latest_bench}
                      }'>
                    <label class="list-group-item rounded-3" for="fast_smp_test" title="Short time control | Multi-threaded">
                      STC SMP
                    </label>
                  </div>

                  <div class="col">
                    <input class="list-group-item-check pe-none" type="radio" name="test-type" id="slow_smp_test"
                      data-options='{
                        "name": "LTC SMP",
                        "tc": "20+0.2",
                        "new_tc": "20+0.2",
                        "threads": 8,
                        "options": "Hash=256 Use NNUE=true",
                        "book": "${test_book}",
                        "stop_rule": "stop-rule-sprt",
                        "bounds": "standard LTC",
                        "base_branch": "${base_branch}",
                        "base_signature": ${latest_bench}
                      }'>
                    <label class="list-group-item rounded-3" for="slow_smp_test" title="Long time control | Multi-threaded">
                      LTC SMP
                    </label>
                  </div>

                  <div class="col collapse collapse-type">
                    <input class="list-group-item-check pe-none" type="radio" name="test-type" id="pt_test"
                      data-options='{
                        "name": "PT",
                        "tc": "60+0.6",
                        "new_tc": "60+0.6",
                        "threads": 1,
                        "options": "Hash=64 Use NNUE=true",
                        "book": "${pt_book}",
                        "stop_rule": "stop-rule-games",
                        "games": 60000,
                        "test_branch": "master",
                        "base_branch": "${pt_branch}",
                        "test_signature": ${latest_bench},
                        "base_signature": ${pt_signature}
                      }'>
                    <label class="list-group-item rounded-3" for="pt_test" title="Progression test | Single-threaded">
                      PT
                    </label>
                  </div>

                  <div class="col collapse collapse-type">
                    <input class="list-group-item-check pe-none" type="radio" name="test-type" id="pt_smp_test"
                      data-options='{
                        "name": "PT SMP",
                        "tc": "30+0.3",
                        "new_tc": "30+0.3",
                        "threads": 8,
                        "options": "Hash=256 Use NNUE=true",
                        "book": "${pt_book}",
                        "stop_rule": "stop-rule-games",
                        "games": 40000,
                        "test_branch": "master",
                        "base_branch": "${pt_branch}",
                        "test_signature": ${latest_bench},
                        "base_signature": ${pt_signature}
                      }'>
                    <label class="list-group-item rounded-3" for="pt_smp_test" title="Progression test | Multi-threaded">
                      PT SMP
                    </label>
                  </div>
                </div>
              </div>

              <div class="mb-2">
                <label for="tests-repo" class="form-label">Test repository</label>
                <input type="url" name="tests-repo" id="tests-repo" class="form-control"
                  value="${args.get('tests_repo', tests_repo)}" ${'readonly' if is_rerun else ''}
                  placeholder="https://github.com/username/Stockfish">
              </div>

              <div class="mb-2 col-6">
                <label for="test-branch" class="form-label">Test Branch</label>
                <input type="text" name="test-branch" id="test-branch" class="form-control" value="${args.get('new_tag', '')}" ${'readonly' if is_rerun else ''}
                  placeholder="Your test branch name">
              </div>

              <div class="mb-2 col-6">
                <label for="base-branch" class="form-label">Base Branch</label>
                <input type="text" name="base-branch" id="base-branch" class="form-control" value="${base_branch}" ${'readonly' if is_rerun else ''}>
              </div>

              <div class="mb-2 col-6">
                <label for="test-signature" class="form-label">Test Signature</label>
                <input type="number" name="test-signature" id="test-signature" min="0" class="form-control no-arrows" onwheel="this.blur()"
                  placeholder="Defaults to last commit message" value="${args.get('new_signature', '')}" ${'readonly' if is_rerun else ''}>
              </div>

              <div class="mb-2 col-6">
                <label for="base-signature" class="form-label">Base Signature</label>
                <input type="number" name="base-signature" id="base-signature" min="0" class="form-control no-arrows" onwheel="this.blur()"
                  value="${latest_bench}" ${'readonly' if is_rerun else ''}>
              </div>

              <div class="mb-2 col-6">
                <label for="new-options" class="form-label">Test Options</label>
                <input type="text" name="new-options" id="new-options" class="form-control" value="${args.get('new_options', 'Hash=16 Use NNUE=true')}">
              </div>

              <div class="mb-2 col-6">
                <label for="base-options" class="form-label">Base Options</label>
                <input type="text" name="base-options" id="base-options" class="form-control" value="${args.get('base_options', 'Hash=16 Use NNUE=true')}">
              </div>

              <div>
                <label for="run-info" class="form-label">Info</label>
                <textarea name="run-info" placeholder="Defaults to commit message" id="run-info" class="form-control" rows="4"
                  >${args.get('info', '')}</textarea>
              </div>
            </div>
          </div>

          <div class="d-block d-md-none"><hr></div>

          <div class="col-12 col-md-6 mb-2">
            <div class="mb-2">
              <input type="hidden" name="stop_rule" id="stop_rule_field" value="sprt" />
              <label class="form-label">Stop rule</label>
              <div class="list-group list-group-checkable flex-row row row-cols-3 g-1 text-center">
                <div class="col">
                  <input class="list-group-item-check pe-none" type="radio" name="stop-rule" id="stop-rule-sprt"
                    value="stop-rule-sprt" checked>
                  <label class="list-group-item rounded-3" for="stop-rule-sprt" title="Sequential probability ratio test">
                    SPRT
                  </label>
                </div>

                <div class="col">
                  <input class="list-group-item-check pe-none" type="radio" name="stop-rule" id="stop-rule-games"
                    value="stop-rule-games">
                  <label class="list-group-item rounded-3" for="stop-rule-games" title="Fixed amount of games">
                    Games
                  </label>
                </div>

                <div class="col">
                  <input class="list-group-item-check pe-none" type="radio" name="stop-rule" id="stop-rule-spsa"
                    value="stop-rule-spsa">
                  <label class="list-group-item rounded-3" for="stop-rule-spsa" title="Simultaneous perturbation stochastic approximation">
                    SPSA
                  </label>
                </div>
              </div>
            </div>

            ## This only appears when games or spsa is selected
            <div class="mb-2 stop-rule stop-rule-games stop-rule-spsa" style="${'display: none' if (args.get('sprt') or not is_rerun) else ''}">
              <label for="num-games" class="form-label">Amount of games</label>
              <input type="number" name="num-games" min="1000" step="1000" id="num-games" class="form-control" value="${args.get('num_games', 60000)}">
            </div>

            ## This only appears when sprt is selected
            <div class="mb-2 stop-rule stop-rule-sprt">
              <input type="hidden" name="elo_model" id="elo_model_field" value=${elo_model} />
              <div class="row gx-1">
                <div class="col-12 col-md">
                  <label for="bounds" class="form-label">SPRT Bounds</label>
                  <select class="form-select" id="bounds" name="bounds">
                    <option value="standard STC">Standard STC ${fb(0.0, 2.0)}</option>
                    <option value="standard LTC">Standard LTC ${fb(0.5, 2.5)}</option>
                    <option value="regression STC">Non-regression STC ${fb(-1.75, 0.25)}</option>
                    <option value="regression LTC">Non-regression LTC ${fb(-1.75, 0.25)}</option>
                    <option value="custom" ${is_rerun and 'selected'}>Custom bounds...</option>
                  </select>
                </div>
                ## This only appears when custom bounds are selected
                <div class="col-6 col-md-4 col-lg-3 mt-2 mt-md-0 custom-bounds" style="${args.get('sprt') or 'display: none'}">
                  <label for="sprt_elo0" class="form-label">SPRT&nbsp;Elo0</label>
                  <input type="number" step="0.05" name="sprt_elo0" id="sprt_elo0" class="form-control" value="${args.get('sprt', {'elo0': 0.0})['elo0']}">
                </div>
                <div class="col-6 col-md-4 col-lg-3 mt-2 mt-md-0 custom-bounds" style="${args.get('sprt') or 'display: none'}">
                  <label for="sprt_elo1" class="form-label">SPRT&nbsp;Elo1</label>
                  <input type="number" step="0.05" name="sprt_elo1" id="sprt_elo1" class="form-control" value="${args.get('sprt', {'elo1': 2.0})['elo1']}">
                </div>
              </div>
            </div>

            ## This only appears when spsa is selected
            <div class="mb-2 stop-rule stop-rule-spsa" style="${args.get('spsa') or 'display: none'}">
              <div class="row gx-1">
                <div class="col-4">
                  <div class="mb-2">
                    <label for="spsa_A" class="form-label">SPSA&nbsp;A&nbsp;ratio</label>
                    <input type="number" min="0" max="1" step="0.001" name="spsa_A" id="spsa_A" class="form-control" value="${args.get('spsa', {'A': '0.1'})['A']}">
                  </div>
                </div>
                <div class="col-4">
                  <div class="mb-2">
                    <label for="spsa_alpha" class="form-label">SPSA&nbsp;Alpha</label>
                    <input type="number" min="0" step="0.001" name="spsa_alpha" id="spsa_alpha" class="form-control" value="${args.get('spsa', {'alpha': '0.602'})['alpha']}">
                  </div>
                </div>
                <div class="col-4">
                  <div class="mb-2">
                    <label for="spsa_gamma" class="form-label">SPSA&nbsp;Gamma</label>
                    <input type="number" min="0" step="0.001" name="spsa_gamma" id="spsa_gamma" class="form-control" value="${args.get('spsa', {'gamma': '0.101'})['gamma']}">
                  </div>
                </div>
              </div>

              <div class="mb-2">
                <label for="spsa_raw_params" class="form-label">SPSA&nbsp;parameters</label>
                <textarea name="spsa_raw_params" id="spsa_raw_params" class="form-control"
                  >${args.get('spsa', {'raw_params': ''})['raw_params']}</textarea>
              </div>

              <div class="mb-2 form-check">
                <label class="form-check-label" for="autoselect">Autoselect</label>
                <input
                  type="checkbox"
                  class="form-check-input"
                  id="autoselect"
                />

                <i class="fa-solid fa-circle-info" role="button" data-bs-toggle="modal" data-bs-target="#autoselect-modal"></i>
                <div class="modal fade" id="autoselect-modal" tabindex="-1" aria-hidden="true">
                  <div class="modal-dialog modal-dialog-scrollable">
                    <div class="modal-content">
                      <div class="modal-header">
                        <h5 class="modal-title">Autoselect information</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                      </div>
                      <div class="modal-body text-break">
                        Checking this option will rewrite the hyperparameters furnished by the tuning
                        code in Stockfish in such a way that the SPSA tune will finish within 0.5 Elo
                        from the optimum (with 95% probability) assuming the function
                        <span class="text-nowrap">'parameters-&gt;Elo'</span> is quadratic and varies
                        2 Elo per parameter over each specified parameter interval. The
                        hyperparameters are relatively conservative and their performance will degrade
                        gracefully if the actual variation is different. The theoretical basis for
                        choosing the hyperparameters is given in this document:
                        <a
                          href="https://github.com/vdbergh/spsa_simul/blob/master/doc/theoretical_basis.pdf"
                          target="_blank"
                        >
                          https://github.com/vdbergh/spsa_simul/blob/master/doc/theoretical_basis.pdf</a
                        >. The formulas can be checked by simulation which is done here:
                        <a href="https://github.com/vdbergh/spsa_simul" target="_blank">
                          https://github.com/vdbergh/spsa_simul</a
                        >. Currently this option should be used with the book
                        'UHO_XXL_+0.90_+1.19.epd' and in addition the option should not be used with
                        nodestime or with more than one thread.
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div><hr></div>

            <div>
              <div class="row gx-1">
                <div class="col mb-2">
                  <label for="threads" class="form-label">Threads</label>
                  <input type="number" min="1" name="threads" id="threads" class="form-control" value="${args.get('threads', 1)}">
                </div>
                <div class="col mb-2">
                  <label for="tc" class="form-label" title="Time control">TC</label>
                  <input type="text" name="tc" id="tc" class="form-control" value="${args.get('tc', '10+0.1')}">
                </div>
                <div class="col mb-2 new_tc" style="display: none;">
                  <label for="new_tc" class="form-label">Test&nbsp;TC</label>
                  <input type="text" name="new_tc" id="new_tc" class="form-control" value="${args.get('new_tc', '10+0.1')}">
                </div>
                <div class="col mb-2">
                  <label for="priority" class="form-label">Priority</label>
                  <input type="number" name="priority" id="priority" class="form-control" value="${args.get('priority', 0)}">
                </div>
                <div class="col mb-2">
                  <label for="throughput" class="form-label">Throughput</label>
                  <select class="form-select" id="throughput" name="throughput">
                    <option value="10">10%</option>
                    <option value="25">25%</option>
                    <option value="50">50%</option>
                    <option value="100" selected>100%</option>
                    <option value="200" class="text-bg-danger">200%</option>
                  </select>
                </div>
              </div>
            </div>

            <div id="test-book" class="mb-2" style="display: none;">
              <div class="row gx-1">
                <div class="col">
                  <label for="book" class="form-label">Book</label>
                  <select name="book" id="book" class="form-select">
                    % for book in valid_books:
                      <option value="${book}" ${"selected" if default_book == book else ""}>${book}</option>
                    % endfor
                  </select>
                </div>
                <div class="col-12 col-md-4 mt-2 mt-md-0 book-depth">
                  <label for="book-depth" class="form-label">Book depth</label>
                  <input type="number" min="1" name="book-depth" id="book-depth" class="form-control" value="${args.get('book_depth', 8)}">
                </div>
              </div>
            </div>

            <div><hr></div>

            <div class="mb-2">
              <div class="row">
                <div class="col text-nowrap">
                  <div class="mb-2 form-check">
                    <label class="form-check-label" for="checkbox-auto-purge">Auto-purge</label>
                    <input
                      type="checkbox"
                      class="form-check-input"
                      id="checkbox-auto-purge"
                      name="auto-purge"
                    />
                  </div>
                </div>
                <div class="col text-nowrap">
                  <div class="mb-2 form-check">
                    <label class="form-check-label" for="checkbox-time-odds">Time odds</label>
                    <input
                      type="checkbox"
                      class="form-check-input"
                      id="checkbox-time-odds"
                      name="odds"
                      ${'checked' if is_odds else ''}
                    />
                  </div>
                </div>
                <div class="col text-nowrap">
                  <div class="mb-2 form-check">
                    <label class="form-check-label" for="checkbox-book-visibility">Custom book</label>
                    <input
                      type="checkbox"
                      class="form-check-input"
                      id="checkbox-book-visibility"
                      ${'checked' if default_book != test_book else ''}
                    />
                  </div>
                </div>
                <div class="col text-nowrap">
                  <div class="mb-2 form-check">
                    <label class="form-check-label" for="checkbox-adjudication">Disable adjudication</label>
                    <input
                      type="checkbox"
                      class="form-check-input"
                      id="checkbox-adjudication"
                      name="adjudication"
                      ${'checked' if not args.get("adjudication", True) else ''}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      % if 'resolved_base' in args:
          <input type="hidden" name="resolved_base" value="${args['resolved_base']}">
          <input type="hidden" name="resolved_new" value="${args['resolved_new']}">
          <input type="hidden" name="msg_base" value="${args.get('msg_base', '')}">
          <input type="hidden" name="msg_new" value="${args.get('msg_new', '')}">
      % endif

      % if is_rerun:
          <input type="hidden" name="rescheduled_from" value="${rescheduled_from}">
      % endif
    </div>
  </div>
</form>

<script>
  let form_submitted = false;
  window.addEventListener("pageshow", () => {
    // make sure form_submitted is set back to false
    form_submitted = false;
    
    // make sure the submit test button is enabled again and has the correct text.
    document.getElementById('submit-test').disabled = false;
    document.getElementById('submit-test').innerText = 'Submit test';
    
    // Also make sure that the fields have the right visibility.
    update_odds(document.getElementById('checkbox-time-odds'));
    update_book_visibility(document.getElementById('checkbox-book-visibility'));
  });

  const preset_bounds = {
    'standard STC': [ 0.0, 2.0],
    'standard LTC': [ 0.5, 2.5],
    'regression STC': [-1.75, 0.25],
    'regression LTC': [-1.75, 0.25],
  };

  const is_rerun = ${'true' if is_rerun else 'false'};

  function update_sprt_bounds(selected_bounds_name) {
    if (selected_bounds_name === "custom") {
      document
        .querySelectorAll(".custom-bounds")
        .forEach((bound) => (bound.style.display = ""));
    } else {
      document
        .querySelectorAll(".custom-bounds")
        .forEach((bound) => (bound.style.display = "none"));
      const bounds = preset_bounds[selected_bounds_name];
      document.getElementById("sprt_elo0").value = bounds[0];
      document.getElementById("sprt_elo1").value = bounds[1];
    }
  }

  function update_book_depth_visibility(book) {
    if (book.match('\\.pgn$')) {
      document.querySelector('.book-depth').style.display = "";
    } else {
      document.querySelector('.book-depth').style.display = "none";
    }
  }

  document
    .getElementById("bounds")
    .addEventListener("change", function () {
      update_sprt_bounds(this.value);
    });

  let initial_base_branch = document.getElementById("base-branch").value;
  let initial_base_signature = document.getElementById("base-signature").value;
  let spsa_do_not_save = false;

  // Test type is changed
  document.querySelectorAll("[name=test-type]").forEach((btn) =>
    btn.addEventListener("click", function () {
      if (!spsa_do_not_save) {
        initial_base_branch = document.getElementById("base-branch").value;
        initial_base_signature = document.getElementById("base-signature").value;
      }
      const btn = this;

      // choose test type - STC, LTC - sets preset values
      let testOptions = null;
      if (btn.dataset.options) testOptions = btn.dataset.options;

      if (testOptions) {
        const { name, tc, new_tc, threads, options, book, stop_rule, bounds, games, test_branch, base_branch, test_signature, base_signature } = JSON.parse(testOptions);
        document.getElementById("tc").value = tc;
        document.getElementById("new_tc").value = new_tc;
        document.getElementById("threads").value = threads;
        document.getElementById("new-options").value = (
          options.replace(" Use NNUE=true", "") +
          " " +
          document
            .getElementById("new-options")
            .value.replace(/Hash=[0-9]+ ?/, "")
        ).replace(/ $/, "");
        document.getElementById("base-options").value = (
          options.replace(" Use NNUE=true", "") +
          " " +
          document
            .getElementById("base-options")
            .value.replace(/Hash=[0-9]+ ?/, "")
        ).replace(/ $/, "");

        document.getElementById("book").value = book;
        update_book_depth_visibility(book);

        document.getElementById("checkbox-book-visibility").checked = (book != "${test_book}") ? true : false;
        update_book_visibility(document.getElementById("checkbox-book-visibility"));

        document.getElementById(stop_rule).click();

        if (bounds) {
          document.getElementById("bounds").value = bounds;
          update_sprt_bounds(bounds);
        }

        if (games) {
          document.getElementById("num-games").value = games;
        }

        if (!is_rerun) {
          if (test_branch) {
            document.getElementById("test-branch").value = test_branch;
          }
          if (test_signature) {
            document.getElementById("test-signature").value = test_signature;
          }
          document.getElementById("base-branch").value = base_branch;
          document.getElementById("base-signature").value = base_signature;
        }

        if (name === "PT" || name === "PT SMP") {
          let info = (name === "PT SMP") ? "SMP " : "";
          info += 'Progression test of "${master_info["message"]}" of ${master_info["date"]} vs ${pt_version}.';
          document.getElementById("run-info").value = info;
        }

        do_spsa_work();
      }
    })
  );

  // Stop rule is changed
  document.querySelectorAll("[name=stop-rule]").forEach((btn) =>
    btn.addEventListener("click", function () {
      let stopRule = null;
      stopRule = btn.value;

      if (stopRule) {
        const testBranchHandler = () =>
          (document.getElementById("base-branch").value =
            document.getElementById("test-branch").value);
        const testSignatureHandler = () =>
          (document.getElementById("base-signature").value =
            document.getElementById("base-branch").value);

        // Hide all elements that have the class "stop-rule"
        document
          .querySelectorAll(".stop-rule")
          .forEach((el) => (el.style.display = "none"));

        document.getElementById("stop_rule_field").value = stopRule.substring(10);

        // Show all elements that have the class with the same name as the selected stop rule
        document
          .querySelectorAll("." + stopRule)
          .forEach((el) => (el.style.display = ""));

        if (!is_rerun) {
          if (stopRule === "stop-rule-spsa") {
            // base branch and test branch should be the same for SPSA tests
            document.getElementById("base-branch").readOnly = true;
            document.getElementById("base-branch").value = document.getElementById("test-branch").value;
            document
              .getElementById("test-branch")
              .addEventListener("input", testBranchHandler);
            document.getElementById("base-signature").readOnly = true;
            document.getElementById("base-signature").value = document.getElementById("test-signature").value;
            document
              .getElementById("test-signature")
              .addEventListener("input", testSignatureHandler);
            spsa_do_not_save = true;
          } else {
            document.getElementById("base-branch").removeAttribute("readonly");
            document.getElementById("base-branch").value = initial_base_branch;
            document.getElementById("base-signature").removeAttribute("readonly");
            document.getElementById("base-signature").value = initial_base_signature;
            document
              .getElementById("test-branch")
              .removeEventListener("input", testBranchHandler);
            document
              .getElementById("test-signature")
              .removeEventListener("input", testSignatureHandler);
            spsa_do_not_save = false;
          }
        }
        if (stopRule === "stop-rule-sprt") {
          update_sprt_bounds(document.getElementById("bounds").value);
        }
      }
    })
  );

  // Only .pgn book types have a book_depth field
  update_book_depth_visibility(document.getElementById("book").value);
  document.getElementById("book").addEventListener("input", function () {
    update_book_depth_visibility(this.value);
  });

  document
    .getElementById("create-new-test")
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
      document.getElementById("submit-test").disabled = true;
      document.getElementById("submit-test").innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> Submitting...';
    });

  // If the test is a reschedule
  if (is_rerun) {
    // Select the correct fields by default for re-runs
    const tc = '${args.get('tc')}';
    if (tc === "10+0.1") {
      document.getElementById("fast_test").checked = true;
    } else if (tc === "60+0.6") {
      document.getElementById("slow_test").checked = true;
    } else if (tc === "5+0.05") {
      document.getElementById("fast_smp_test").checked = true;
    } else if (tc === "20+0.2") {
      document.getElementById("slow_smp_test").checked = true;
    }

    % if args.get('spsa'):
      document.getElementById('stop-rule-spsa').click();
    % elif not args.get('sprt'):
      document.getElementById('stop-rule-games').click();
    % endif
  } else {
    // Focus the "Test branch" field on page load for new tests
    document.getElementById('test-branch').focus();
  }

  function update_odds(checkbox) {
    if (checkbox.checked) {
      document.querySelector('.new_tc').style.display = "";
      document.querySelector('[for=tc]').innerHTML = "Base&nbsp;TC";
    } else {
      document.querySelector('.new_tc').style.display = "none";
      document.getElementById('new_tc').value = document.getElementById('tc').value;
      document.querySelector('[for=tc]').innerHTML = "TC";
    }
  }

  document.getElementById('checkbox-time-odds').addEventListener("change", function() {
    update_odds(this);
  });

  function update_book_visibility(checkbox) {
    if (checkbox.checked) {
      document.getElementById('test-book').style.display = "";
    } else {
      document.getElementById('test-book').style.display = "none";
      document.getElementById('book').value = "${test_book}";
      update_book_depth_visibility(document.getElementById('book').value);
    }
  }

  document.getElementById('checkbox-book-visibility').addEventListener("change", function() {
    update_book_visibility(this);
  });
</script>

<script src="/js/spsa_new.js?5&?v=${cache_busters['js/spsa_new.js']}"
        integrity="sha384-${cache_busters['js/spsa_new.js']}"
        crossorigin="anonymous"></script>

<script>
  function do_spsa_work() {
    /* parsing/computing */
    if (!document.getElementById('autoselect').checked) {
      return true;
    }
    const params = document.getElementById('spsa_raw_params').value;
    let s = fishtest_to_spsa(params);
    if (s === null) {
      alert("Unable to parse spsa parameters.");
      return false;
    }
    /* estimate the draw ratio */
    const tc = document.getElementById('tc').value;
    const dr = draw_ratio(tc);
    if (dr === null) {
      alert("Unable to parse time control.");
      return false;
    }
    s.draw_ratio = dr;
    s = spsa_compute(s);
    const fs = spsa_to_fishtest(s);
    /* Let's go */
    document.getElementById("spsa_A").value = 0;
    document.getElementById("spsa_alpha").value = 0.0;
    document.getElementById("spsa_gamma").value = 0.0;
    document.getElementById("num-games").value = 1000 * Math.round(s.num_games / 1000);
    document.getElementById("spsa_raw_params").value = fs.trim();
    return true;
  }

  let saved_A = null;
  let saved_alpha = null;
  let saved_gamma = null;
  let saved_games = null;
  let saved_params = null;

  function do_spsa_events() {
    if (document.getElementById('autoselect')["checked"]) {
      /* save old stuff */
      saved_A = document.getElementById("spsa_A").value;
      saved_alpha = document.getElementById("spsa_alpha").value;
      saved_gamma = document.getElementById("spsa_gamma").value;
      saved_games = document.getElementById("num-games").value;
      saved_params = document.getElementById("spsa_raw_params").value;
      const ret = do_spsa_work();
      if (!ret) {
        document.getElementById('autoselect').checked = false;
      }
    } else {
      document.getElementById("spsa_A").value = saved_A;
      document.getElementById("spsa_alpha").value = saved_alpha;
      document.getElementById("spsa_gamma").value = saved_gamma;
      document.getElementById("num-games").value = saved_games;
      document.getElementById("spsa_raw_params").value = saved_params;
    }
  }

  document.getElementById('autoselect').addEventListener("change", do_spsa_events);

  document.getElementById('tc').addEventListener("input", function() {
    if (!document.getElementById('autoselect').checked) {
      return;
    }
    const tc = document.getElementById('tc').value;
    const tc_seconds = tc_to_seconds(tc);
    if (tc_seconds !== null) {
      do_spsa_work();
    }
  });
</script>
