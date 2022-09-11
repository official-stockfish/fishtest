<%inherit file="base.mak"/>

<%
from fishtest.util import worker_name

if 'spsa' in run['args']:
  import json
  spsa_data = json.dumps(run["args"]["spsa"])
%>

<%namespace name="base" file="base.mak"/>

% if 'spsa' in run['args']:
    <script src="https://www.gstatic.com/charts/loader.js"></script>
    <script>
      const spsa_data = ${spsa_data | n};
    </script>
    <script src="/js/spsa.js?v=${cache_busters['js/spsa.js']}"
            integrity="sha384-${cache_busters['js/spsa.js']}"
            crossorigin="anonymous"></script>
% endif

<h2>
  <span>${page_title}</span>
  <a href="${h.diff_url(run)}" target="_blank" rel="noopener">diff</a>
</h2>

<div class="elo-results-top">
  <%include file="elo_results.mak" args="run=run" />
</div>

<div class="row">
  <div class="col-12 col-lg-9">
    <h4>Details</h4>

    <%!
      import markupsafe
    %>

    <div class="table-responsive-lg">
      <table class="table table-striped table-sm">
        % for arg in run_args:
            % if len(arg[2]) == 0:
                <tr>
                  <td>${arg[0]}</td>
                  % if arg[0] == 'username':
                      <td>
                        <a href="/tests/user/${arg[1]}">${arg[1]}</a>
                        % if approver:
                            (<a href="/user/${arg[1]}">user admin</a>)
                        % endif
                      </td>
                  % elif arg[0] == 'spsa':
                      <td>
                        ${arg[1][0]}<br />
                        <table class="table table-sm">
                          <thead>
                            <th>param</th>
                            <th>value</th>
                            <th>start</th>
                            <th>min</th>
                            <th>max</th>
                            <th>c</th>
                            <th>c_end</th>
                            <th>r</th>
                            <th>r_end</th>
                          </thead>
                          <tbody>
                            % for row in arg[1][1:]:
                                <tr class="spsa-param-row">
                                  % for element in row:
                                      <td>${element}</td>
                                  % endfor
                                </tr>
                            % endfor
                          </tbody>
                        </table>
                      </td>
                  % elif arg[0] in ['resolved_new', 'resolved_base']:
                      <td>${arg[1][:10]}</td>
                  % elif arg[0] == 'rescheduled_from':
                      <td><a href="/tests/view/${arg[1]}">${arg[1]}</a></td>
                  % else:
                      <td ${'class="run-info"' if arg[0]=="info" else "" | n}>
                          ${str(markupsafe.Markup(arg[1])).replace('\n', '<br>') | n}
                      </td>
                  % endif
                </tr>
            % else:
                <tr>
                  <td>${arg[0]}</td>
                  <td>
                    <a href="${arg[2]}" target="_blank" rel="noopener">
                      ${str(markupsafe.Markup(arg[1]))}
                    </a>
                  </td>
                </tr>
            % endif
        % endfor
        % if 'spsa' not in run['args']:
            <tr>
              <td>raw statistics</td>
              <td><a href="/tests/stats/${str(run['_id'])}">/tests/stats/${run['_id']}</a></td>
            </tr>
        % endif
      </table>
    </div>
  </div>

  <div class="col-12 col-lg-3">
    <h4>Actions</h4>
    <div class="row g-2 mb-2">
      % if not run['finished']:
        <div class="col-12 col-sm">
          <form action="/tests/stop" method="POST">
            <input type="hidden" name="run-id" value="${run['_id']}">
            <button type="submit" class="btn btn-danger w-100">
              Stop
            </button>
          </form>
        </div>

        % if not run.get('approved', False):
          <div class="col-12 col-sm">
            <form action="/tests/approve" method="POST">
              <input type="hidden" name="run-id" value="${run['_id']}">
              <button type="submit" id="approve-btn"
                      class="btn ${'btn-success' if run['base_same_as_master'] else 'btn-warning'} w-100">
                Approve
              </button>
            </form>
          </div>
        % endif
      % else:
        <div class="col-12 col-sm">
          <form action="/tests/purge" method="POST">
            <input type="hidden" name="run-id" value="${run['_id']}">
            <button type="submit" class="btn btn-danger w-100">Purge</button>
          </form>
        </div>
      % endif
      <div class="col-12 col-sm">
        <a class="btn btn-light border w-100" href="/tests/run?id=${run['_id']}">Reschedule</a>
      </div>
    </div>

    % if run.get('base_same_as_master') is not None:
        % if run['base_same_as_master']:
            <div id="master-diff" class="alert alert-success">
              Base branch same as Stockfish master
        % else:
            <div id="master-diff" class="alert alert-danger mb-2">
              Base branch not same as Stockfish master
        % endif
            </div>
    % endif

    % if not run.get('base_same_as_master'):
        <div class="alert alert-warning">
          <a class="alert-link" href="${h.master_diff_url(run)}" target="_blank" rel="noopener">Master diff</a>
        </div>
    % endif

    <hr>

    <form class="form" action="/tests/modify" method="POST">
      <div class="mb-3">
        <label class="form-label" for="modify-num-games">Number of games</label>
        <input type="number" class="form-control" name="num-games" id="modify-num-games" min="0" step="1000" value="${run['args']['num_games']}">
      </div>

      <div class="mb-3">
        <label class="form-label" for="modify-priority">Priority (higher is more urgent)</label>
        <input type="number" class="form-control" name="priority" id="modify-priority" value="${run['args']['priority']}">
      </div>

      <label class="form-label" for="modify-throughput">Throughput</label>
      <div class="mb-3 input-group">
        <input type="number" class="form-control" name="throughput" id="modify-throughput" min="0" value="${run['args'].get('throughput', 1000)}">
        <span class="input-group-text">%</span>
      </div>

      <div class="mb-3 form-check">
        <input type="checkbox" class="form-check-input" id="auto-purge" name="auto_purge"
               ${'checked' if run['args'].get('auto_purge') else ''} />
        <label class="form-check-label" for="auto-purge">Auto-purge</label>
      </div>

      <input type="hidden" name="run" value="${run['_id']}" />
      <button type="submit" class="btn btn-primary col-12 col-md-auto">Modify</button>
    </form>

    % if 'spsa' not in run['args']:
        <hr>

        <h4>Stats</h4>
        <table class="table table-striped table-sm">
          <tr><td>chi^2</td><td>${f"{chi2['chi2']:.2f}"}</td></tr>
          <tr><td>dof</td><td>${chi2['dof']}</td></tr>
          <tr><td>p-value</td><td>${f"{chi2['p']:.2%}"}</td></tr>
        </table>
    % endif

    <hr>

    <h4>Time</h4>
    <table class="table table-striped table-sm">
      <tr><td>start time</td><td>${run['start_time'].strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
      <tr><td>last updated</td><td>${run['last_updated'].strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
    </table>
  </div>
</div>

% if 'spsa' in run['args']:
    <div id="div_spsa_preload" style="background-image:url('/img/preload.gif'); width: 256px; height: 32px; display: none;">
      <div style="height: 100%; width: 100%; text-align: center; padding-top: 5px;">
      Loading graph...
      </div>
    </div>

    <div id="chart_toolbar" style="display: none">
      Gaussian Kernel Smoother&nbsp;&nbsp;
      <div class="btn-group">
        <button id="btn_smooth_plus" class="btn">&nbsp;&nbsp;&nbsp;+&nbsp;&nbsp;&nbsp;</button>
        <button id="btn_smooth_minus" class="btn">&nbsp;&nbsp;&nbsp;−&nbsp;&nbsp;&nbsp;</button>
      </div>

      <div class="btn-group">
        <button id="btn_view_individual" type="button" class="btn btn-default dropdown-toggle" data-bs-toggle="dropdown">
          View Individual Parameter<span class="caret"></span>
        </button>
        <ul class="dropdown-menu" role="menu" id="dropdown_individual"></ul>
      </div>

      <button id="btn_view_all" class="btn">View All</button>
    </div>
    <div class="overflow-auto">
      <div id="div_spsa_history_plot"></div>
    </div>
% endif

<section id="diff-section" style="display: none">
  <h4>
    <button id="diff-toggle" class="btn btn-sm btn-light border mb-2">Show</button>
    Diff
    <span id="diff-num-comments" style="display: none"></span>
    <a href="${h.diff_url(run)}" class="btn btn-primary bg-light-primary border-0 mb-2" target="_blank" rel="noopener">View on Github</a>
    <a href="javascript:" id="copy-diff" class="btn btn-secondary bg-light-secondary border-0 mb-2" style="display: none">Copy apply-diff command</a>
    <span class="text-success copied text-nowrap" style="display: none">Copied!</span>
  </h4>
  <pre id="diff-contents"><code class="diff"></code></pre>
</section>

<script>
    function toggle_tasks() {
      const button = document.querySelector("#tasks-button");
      const div = document.querySelector("#tasks");
      const active = button.innerText.trim() === 'Hide';
      button.innerText = active ? 'Show' : 'Hide';
      document.cookie = 'tasks_state' + '=' + button.innerText.trim() + ";max-age=315360000;SameSite=Lax;";
    }
</script>

<h4>
    <button id="tasks-button" class="btn btn-sm btn-light border" 
    data-bs-toggle="collapse" href="#tasks" role="button" aria-expanded="false"
    aria-controls="tasks" onclick="toggle_tasks()">
    ${'Hide' if tasks_shown else 'Show'}
    </button>
  Tasks ${totals}
</h4>
<div id="tasks"
     class="overflow-auto ${'collapse show' if tasks_shown else 'collapse'}">
  <table class='table table-striped table-sm'>
    <thead class="sticky-top">
      <tr>
        <th>Idx</th>
        <th>Worker</th>
        <th>Info</th>
        <th>Last Updated</th>
        <th>Played</th>
        % if 'pentanomial' not in run['results']:
            <th>Wins</th>
            <th>Losses</th>
            <th>Draws</th>
        % else:
            <th>Pentanomial&nbsp;[0&#8209;2]</th>
        % endif
        <th>Crashes</th>
        <th>Time</th>

        % if 'spsa' not in run['args']:
            <th>Residual</th>
        % endif
      </tr>
    </thead>
    <tbody>
      % for idx, task in enumerate(run['tasks'] + run.get('bad_tasks', [])):
          <%
            stats = task.get('stats', {})
            if 'stats' in task:
              total = stats['wins'] + stats['losses'] + stats['draws']
            else:
              continue

            if task['active']:
              active_style = 'info'
            else:
              active_style = ''
          %>
          <tr class="${active_style}">
            <td><a href=${f"/api/pgn/{run['_id']}-{idx:d}.pgn"}>${idx}</a></td>
            % if 'bad' in task:
                <td style="text-decoration:line-through; background-color:#ffebeb">
            % else:
                <td>
            % endif
            % if approver and task['worker_info']['username'] != "Unknown_worker":
                <a href="/user/${task['worker_info']['username']}">${worker_name(task['worker_info'])}</a>
            % elif 'worker_info' in task:
                ${worker_name(task["worker_info"])}
            % else:
                -
            % endif
            </td>
            <td>
            <%
               gcc_version = ".".join([str(m) for m in task['worker_info']['gcc_version']])
               compiler = task['worker_info'].get('compiler', 'g++')
               python_version = ".".join([str(m) for m in task['worker_info']['python_version']])
               version = task['worker_info']['version']
               ARCH = task['worker_info']['ARCH']
            %>
               os: ${task['worker_info']['uname']};
               ram: ${task['worker_info']['max_memory']}MiB;
               compiler: ${compiler} ${gcc_version};
               python: ${python_version};
               worker: ${version};
               arch: ${ARCH}
            </td>
            <td>${str(task.get('last_updated', '-')).split('.')[0]}</td>
            <td>${f"{total:03d} / {task['num_games']:03d}"}</td>
            % if 'pentanomial' not in run['results']:
                <td>${stats.get('wins', '-')}</td>
                <td>${stats.get('losses', '-')}</td>
                <td>${stats.get('draws', '-')}</td>
            % else:
                <%
                  p=stats.get('pentanomial',5*[0])
                %>
                <td>[${p[0]},&nbsp;${p[1]},&nbsp;${p[2]},&nbsp;${p[3]},&nbsp;${p[4]}]</td>
            % endif
            <td>${stats.get('crashes', '-')}</td>
            <td>${stats.get('time_losses', '-')}</td>

            % if 'spsa' not in run['args']:
                % if 'residual' in task and task['residual']!=float("inf"):
                    <td style="background-color:${task['residual_color']}">${f"{task['residual']:.3f}"}</td>
                % else:
                    <td>-</td>
                % endif
            % endif
          </tr>
      % endfor
    </tbody>
  </table>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.1/highlight.min.js"
        integrity="sha512-yUUc0qWm2rhM7X0EFe82LNnv2moqArj5nro/w1bi05A09hRVeIZbN6jlMoyu0+4I/Bu4Ck/85JQIU82T82M28w=="
        crossorigin="anonymous"
        referrerpolicy="no-referrer"></script>

<script>
  const match = document.cookie.match(
    new RegExp("(^| )" + "theme" + "=([^;]+)")
  );

  const setHighlightTheme = (theme) => {
    const link = document.createElement("link");
    if (theme === "dark") {
      document.head
        .querySelector('link[href*="styles/github.min.css"]')
        ?.remove();
      link["rel"] = "stylesheet";
      link["crossOrigin"] = "anonymous";
      link["referrerPolicy"] = "no-referrer";
      link["href"] =
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.1/styles/github-dark.min.css";
      link["integrity"] =
        "sha512-rO+olRTkcf304DQBxSWxln8JXCzTHlKnIdnMUwYvQa9/Jd4cQaNkItIUj6Z4nvW1dqK0SKXLbn9h4KwZTNtAyw==";
    } else {
      document.head
        .querySelector('link[href*="styles/github-dark.min.css"]')
        ?.remove();
      link["rel"] = "stylesheet";
      link["crossOrigin"] = "anonymous";
      link["referrerPolicy"] = "no-referrer";
      link["href"] =
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.1/styles/github.min.css";
      link["integrity"] =
        "sha512-0aPQyyeZrWj9sCA46UlmWgKOP0mUipLQ6OZXu8l4IcAmD2u31EPEy9VcIMvl7SoAaKe8bLXZhYoMaE/in+gcgA==";
    }
    document.head.appendChild(link);
  };

  const getPreferredTheme = () => {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  };

  if (!match) {
    setHighlightTheme(getPreferredTheme());
  } else {
    setHighlightTheme(match[2]);
  }

  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => setHighlightTheme(getPreferredTheme()));

  document
    .getElementById("sun")
    .addEventListener("click", () => setHighlightTheme("light"));

  document
    .getElementById("moon")
    .addEventListener("click", () => setHighlightTheme("dark"));
</script>

<script>
  document.title = "${page_title} | Stockfish Testing";

  document.addEventListener("DOMContentLoaded", function () {
    let copyDiffBtn = document.querySelector("#copy-diff");
    if (
      document.queryCommandSupported &&
      document.queryCommandSupported("copy")
    ) {
      copyDiffBtn.addEventListener("click", () => {
        const textarea = document.createElement("textarea");
        textarea.style.position = "fixed";
        textarea.textContent = "curl -s ${h.diff_url(run)}.diff | git apply";
        document.body.appendChild(textarea);
        textarea.select();
        try {
          document.execCommand("copy");
          document.querySelector(".copied").style.display = "";
        } catch (ex) {
          console.warn("Copy to clipboard failed.", ex);
        } finally {
          document.body.removeChild(textarea);
        }
      });
    } else {
      copyDiffBtn = null;
    }

    // Fetch the diff and decide whether to show it on the page
    const diffApiUrl = "${h.diff_url(run)}".replace(
      "//github.com/",
      "//api.github.com/repos/"
    );

    // Check if the diff is already in sessionStorage and use it if it is
    const diffId = sessionStorage.getItem("${run['_id']}");
    if (!diffId) {
      fetchDiff();
    } else {
      showDiff(diffId);
    }

    function fetchDiff() {
      fetch(diffApiUrl, {
        headers: {
          Accept: "application/vnd.github.v3.diff",
        },
      })
        .then((response) => {
          if (response.ok) return response.text();
        })
        .then((text) => {
          if (!text) return;
          showDiff(text);
        });
    }

    function showDiff(text) {
      const numLines = text.split("\n").length;
      const toggleBtn = document.querySelector("#diff-toggle");
      const diffContents = document.querySelector("#diff-contents");
      const diffText = diffContents.querySelector("code");
      diffText.textContent = text;

      // Try to save the diff in sessionStorage
      // It can throw an exception if there is not enough space
      try {
        sessionStorage.setItem("${run['_id']}", text);
      } catch (e) {
        console.warn("Could not save diff in sessionStorage");
      }

      toggleBtn.addEventListener("click", function () {
        diffContents.style.display =
          diffContents.style.display === "none" ? "" : "none";
        if (copyDiffBtn)
          copyDiffBtn.style.display =
            copyDiffBtn.style.display === "none" ? "" : "none";
        if (toggleBtn.innerText === "Hide") toggleBtn.innerText = "Show";
        else toggleBtn.innerText = "Hide";
      });

      // Hide large diffs by default
      if (numLines < 50) {
        diffContents.style.display = "";
        if (copyDiffBtn) copyDiffBtn.style.display = "";
        toggleBtn.innerText = "Hide";
      } else {
        diffContents.style.display = "none";
        if (copyDiffBtn) copyDiffBtn.style.display = "none";
        toggleBtn.innerText = "Show";
      }
      document.querySelector("#diff-section").style.display = "";
      hljs.highlightElement(diffText);

      // Fetch amount of comments
      fetch(diffApiUrl)
        .then((response) => {
          if (response.ok) return response.json();
        })
        .then((json) => {
          if (!json) return;
          let numComments = 0;
          json.commits.forEach(function (row) {
            numComments += row.commit.comment_count;
          });
          document.querySelector("#diff-num-comments").innerText =
            "(" + numComments + " comments)";
          document.querySelector("#diff-num-comments").style.display = "";
        });
    }
  });
</script>
