<%inherit file="base.mak"/>

<%!
  import json
%>

<%namespace name="base" file="base.mak"/>

<script
  src="https://cdnjs.cloudflare.com/ajax/libs/jsdiff/5.2.0/diff.js"
  integrity="sha512-Ubw08LwzeoACkP9I1L0LqwnhiVs6Vg9LWeTFDj0leZIVp5XG28xcxK0lrlFvaL8ZqR8oMOBnFdZLo6agy5+SgQ=="
  crossorigin="anonymous"
  referrerpolicy="no-referrer"
></script>

% if show_task >= 0:
  <script>
    document.documentElement.style="scroll-behavior:auto; overflow:hidden;";
    function scroll_to(task_id) {
      const task_offset = document.getElementById("task" + task_id).offsetTop;
      const tasks_head_height = document.getElementById("tasks-head").offsetHeight;
      const tasks_div = document.getElementById("tasks");
      tasks_div.scrollIntoView();
      tasks_div.scrollTop = task_offset - tasks_head_height;
    }
  </script>
% endif

% if follow == 1:
  <script>
    (async () => {
      await DOMContentLoaded();
      await followRun("${run['_id']}");
      setNotificationStatus("${run['_id']}");
    })();
  </script>
% else:
  <script>
    (async () => {
      await DOMContentLoaded();
      setNotificationStatus_("${run['_id']}");
    })();
  </script>
% endif

% if 'spsa' in run['args']:
  <script src="https://www.gstatic.com/charts/loader.js"></script>
  <script>
    const spsaData = ${json.dumps(run["args"]["spsa"])|n};
  </script>

  <script
    src="/js/spsa.js?v=${cache_busters['js/spsa.js']}"
    integrity="sha384-${cache_busters['js/spsa.js']}"
    crossorigin="anonymous"
  ></script>

  <script>
    const spsaPromise = handleSPSA();
  </script>
% else:
  <script>
    const spsaPromise = Promise.resolve();
  </script>
% endif

<div id="enclosure"${' style="visibility:hidden;"' if show_task >= 0 else "" |n}>

  <h2>
    <span>${page_title}</span>
    <a href="${h.diff_url(run)}" target="_blank" rel="noopener">diff</a>
  </h2>

  <div class="elo-results-top">
    <%include file="elo_results.mak" args="run=run" />
  </div>

  <div class="row">
    <div class="col-12 col-lg-9">
      <div id="diff-section">
        <h4>
          <button id="diff-toggle" class="btn btn-sm btn-light border mb-2">Show</button>
          Diff
          <span id="diff-num-comments">(0 comments)</span>
          <a
            href="${h.diff_url(run)}"
            class="btn btn-primary bg-light-primary border-0 mb-2"
            target="_blank" rel="noopener"
          >
            View on GitHub
          </a>

          <a
            href="javascript:"
            id="copy-diff"
            class="btn btn-secondary bg-light-secondary border-0 mb-2"
            style="display: none"
          >
            Copy apply-diff command
          </a>

          <a
            href="javascript:" 
            id="master_vs_official_master" class="btn btn-danger  border-0 mb-2"
            title="Compares master to official-master at the time of submission"
            style="display: none">
            <i class="fa-solid fa-triangle-exclamation"></i>
              <span> master vs official</span>
            </a>

          <span class="text-success copied text-nowrap" style="display: none">Copied!</span>
        </h4>
        <pre id="diff-contents" style="display: none;"><code class="diff"></code></pre>
      </div>
      <div>
        <h4 style="margin-top: 9px;">Details</h4>
        <div class="table-responsive">
          <table class="table table-striped table-sm">
            <thead></thead>
            <tbody>
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
                        ${arg[1][0]}<br>
                        <table class="table table-sm">
                          <thead>
                            <tr>
                              <th>param</th>
                              <th>value</th>
                              <th>start</th>
                              <th>min</th>
                              <th>max</th>
                              <th>c</th>
                              <th>c_end</th>
                              <th>r</th>
                              <th>r_end</th>
                            </tr>
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
                    % elif arg[0] == 'itp':
                      <td>${f"{float(arg[1]):.2f}"}</td>
                    % else:
                      <td ${'class="run-info"' if arg[0]=="info" else ""|n}>
                        ${arg[1].replace('\n', '<br>')|n}
                      </td>
                    % endif
                  </tr>
                % else:
                  <tr>
                    <td>${arg[0]}</td>
                    <td>
                      <a href="${arg[2]}" target="_blank" rel="noopener">
                        ${arg[1]|n}
                      </a>
                    </td>
                  </tr>
                % endif
              % endfor
              <tr>
                <td>events</td>
                <td><a href="/actions?run_id=${str(run['_id'])}">/actions?run_id=${run['_id']}</a></td>
              </tr>
              % if 'spsa' not in run['args']:
                <tr>
                  <td>raw statistics</td>
                  <td><a href="/tests/stats/${str(run['_id'])}">/tests/stats/${run['_id']}</a></td>
                </tr>
              % endif
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="col-12 col-lg-3">
      <h4>Actions</h4>
      <div class="row g-2 mb-2">
        % if can_modify_run:
          % if not run['finished']:
            <div class="col-12 col-sm">
              <form
                action="/tests/stop"
                method="POST"
                onsubmit="handleStopDeleteButton('${run['_id']}'); return true;"
              >
                <input type="hidden" name="run-id" value="${run['_id']}">
                <button type="submit" class="btn btn-danger w-100">
                  Stop
                </button>
              </form>
            </div>

            % if not run.get('approved', False) and not same_user:
              <div class="col-12 col-sm">
                <form action="/tests/approve" method="POST">
                  <input type="hidden" name="run-id" value="${run['_id']}">
                  <button type="submit" id="approve-btn"
                          class="btn ${'btn-success' if run['base_same_as_master'] or 'spsa' in run['args'] else 'btn-warning'} w-100">
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
        % endif

        <div class="col-12 col-sm">
          <a class="btn btn-light border w-100" href="/tests/run?id=${run['_id']}">Reschedule</a>
        </div>
      </div>

      % if run.get('base_same_as_master') is not None:
        % if run['base_same_as_master']:
          <div id="master-diff" class="alert alert-success">
            Base branch same as Stockfish master
          </div>
        % elif 'spsa' not in run['args']:
          <div id="master-diff" class="alert alert-danger mb-2">
            Base branch not same as Stockfish master
          </div>
        % endif
      % endif
      
      % if 'spsa' not in run['args'] and run['args']['base_signature'] == run['args']['new_signature']:
        <div class="alert alert-info mb-2">
          Note: The new signature is the same as base signature.
        </div>
      % endif

      % if 'spsa' not in run['args'] and not run.get('base_same_as_master'):
        <div class="alert alert-warning">
          <a class="alert-link" href="${h.master_diff_url(run)}" target="_blank" rel="noopener">Master diff</a>
        </div>
      % endif

      <hr>

      % if can_modify_run:
        <form class="form" action="/tests/modify" method="POST">
          <div class="mb-3">
            <label class="form-label" for="modify-num-games">Number of games</label>
            <input
              type="number"
              class="form-control"
              name="num-games"
              id="modify-num-games"
              min="0"
              step="1000"
              value="${run['args']['num_games']}"
            >
          </div>

          <div class="mb-3">
            <label class="form-label" for="modify-priority">Priority (higher is more urgent)</label>
            <input
              type="number"
              class="form-control"
              name="priority"
              id="modify-priority"
              value="${run['args']['priority']}"
            >
          </div>

          <label class="form-label" for="modify-throughput">Throughput</label>
          <div class="mb-3 input-group">
            <input
              type="number"
              class="form-control"
              name="throughput"
              id="modify-throughput"
              min="0"
              value="${run['args'].get('throughput', 1000)}"
            >
            <span class="input-group-text">%</span>
          </div>

          % if same_user:
            <div class="mb-3">
              <label for="info" class="form-label">
                Info
              </label>
              <textarea
                id="modify-info"
                name="info"
                placeholder="Defaults to submitted message."
                class="form-control"
                rows="4"
                style="height: 149px;"
              ></textarea>
            </div>
          % endif

          <div class="mb-3 form-check">
            <input
              type="checkbox"
              class="form-check-input"
              id="auto-purge"
              name="auto_purge" ${'checked' if run['args'].get('auto_purge') else ''}
            >
            <label class="form-check-label" for="auto-purge">Auto-purge</label>
          </div>

          <input type="hidden" name="run" value="${run['_id']}">
          <button type="submit" class="btn btn-primary col-12 col-md-auto">Modify</button>
        </form>
      % endif

      % if 'spsa' not in run['args']:
        <hr>

        <h4>Stats</h4>
        <table class="table table-striped table-sm">
          <thead></thead>
          <tbody>
            <tr><td>chi^2</td><td>${f"{chi2['chi2']:.2f}"}</td></tr>
            <tr><td>dof</td><td>${chi2['dof']}</td></tr>
            <tr><td>p-value</td><td>${f"{chi2['p']:.2%}"}</td></tr>
          </tbody>
        </table>
      % endif

      <hr>

      <h4>Time</h4>
      <table class="table table-striped table-sm">
        <thead></thead>
        <tbody>
          <tr><td>start time</td><td>${run['start_time'].strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
          <tr><td>last updated</td><td>${run['last_updated'].strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
        </tbody>
      </table>

      <hr>
      % if not run['finished']:
        <h4>Notifications</h4>
        <button 
          id="follow_button_${run['_id']}"
          class="btn btn-primary col-12 col-md-auto"
          onclick="handleFollowButton(this)"
          style="display:none; margin-top:0.2em;"></button>
        <hr style="visibility:hidden;">
      % endif
    </div>
  </div>

  % if 'spsa' in run['args']:
    <div id="spsa_preload" class="col-lg-3">
      <div class="pt-1 text-center">
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
        <button
          id="btn_view_individual"
          type="button"
          class="btn btn-default dropdown-toggle" data-bs-toggle="dropdown"
        >
          View Individual Parameter<span class="caret"></span>
        </button>
        <ul class="dropdown-menu" role="menu" id="dropdown_individual"></ul>
      </div>

      <button id="btn_view_all" class="btn">View All</button>
    </div>
    <div class="overflow-auto">
      <div id="spsa_history_plot"></div>
    </div>
  % endif

  <h4>
      <a
        id="tasks-button" class="btn btn-sm btn-light border"
        data-bs-toggle="collapse" href="#tasks" role="button" aria-expanded="false"
        aria-controls="tasks"
      >
        ${'Hide' if tasks_shown else 'Show'}
      </a>
    Tasks ${totals}
  </h4>
  <section id="tasks"
       class="overflow-auto ${'collapse show' if tasks_shown else 'collapse'}">
    <table class='table table-striped table-sm'>
      <thead id="tasks-head" class="sticky-top">
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
      <tbody id="tasks-body"></tbody>
    </table>
  </div>
## End of enclosing div to be able to make things invisible.
</div>


<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"
        integrity="sha512-rdhY3cbXURo13l/WU9VlaRyaIYeJ/KBakckXIvJNAQde8DgpOmE+eZf7ha4vdqVjTtwQt69bD2wH2LXob/LB7Q=="
        crossorigin="anonymous"
        referrerpolicy="no-referrer"
></script>

<script>
  let cookieTheme = getCookie("theme");
  const currentTime = new Date().getTime();
  const oneDayAgo = currentTime - (24 * 60 * 60 * 1000); // 24 hours ago in milliseconds

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
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/github-dark.min.css";
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
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/github.min.css";
      link["integrity"] =
        "sha512-0aPQyyeZrWj9sCA46UlmWgKOP0mUipLQ6OZXu8l4IcAmD2u31EPEy9VcIMvl7SoAaKe8bLXZhYoMaE/in+gcgA==";
    }
    document.head.append(link);
  };

  if (!cookieTheme) {
    setHighlightTheme(mediaTheme());
  } else {
    setHighlightTheme(cookieTheme);
  }

  try {
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", () => setHighlightTheme(mediaTheme()));
  } catch (e) {
    console.error(e);
  }

  document
    .getElementById("sun")
    .addEventListener("click", () => setHighlightTheme("light"));

  document
    .getElementById("moon")
    .addEventListener("click", () => setHighlightTheme("dark"));
</script>

<script>
  document.title = "${page_title} | Stockfish Testing";

  let fetchedTasksBefore = false;
  async function handleRenderTasks(){
    await DOMContentLoaded();
    const tasksButton = document.getElementById("tasks-button");
    tasksButton?.addEventListener("click", async () => {
      await toggleTasks();
    })
     if (${str(tasks_shown).lower()})
       await renderTasks();
  }

  async function renderTasks() {
    await DOMContentLoaded();
    if (fetchedTasksBefore)
      return Promise.resolve();
    const tasksBody = document.getElementById("tasks-body");
    try {
      const html = await fetchText(`/tests/tasks/${str(run['_id'])}?show_task=${show_task}`);
      tasksBody.innerHTML = html;
      fetchedTasksBefore = true;
    } catch (error) {
      console.log("Request failed: " + error);
    }
  }

  async function toggleTasks() {
    const button = document.getElementById("tasks-button");
    const active = button.textContent.trim() === "Hide";
    if (active){
      button.textContent = "Show";
    }
    else {
      await renderTasks();
      button.textContent = "Hide";
    }

    document.cookie =
      "tasks_state" + "=" + button.textContent.trim() + "; max-age=${60 * 60}; SameSite=Lax";
  }

  function addDiff (diffText, text) {
    diffText.textContent = text;
  }

  function showDiff(diffContents, diffText, numLines, copyDiffBtn, toggleBtn) {
    // Hide large diffs by default
    if (numLines < 50) {
      diffContents.style.display = "";
      if (copyDiffBtn) copyDiffBtn.style.display = "";
      setTimeout(() => {
        toggleBtn.textContent = "Hide";
      }, 350);
    } else {
      diffContents.style.display = "none";
      if (copyDiffBtn) copyDiffBtn.style.display = "none";
      setTimeout(() => {
        toggleBtn.textContent = "Show";
      }, 350);
    }
  }

  async function getFileContentFromUrl(url) {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        if (response.status === 404) {
          return "";
        } else {
          throw new Error(
            "Failed to fetch " + url + ": " + response.status + " " + response.statusText
          );
        }
      }
      return await response.text();
    } catch (error) {
        throw new Error(
          "Failed to fetch file: " + error
        );
    }
  }

  async function getFilesInBranch(apiUrl, branch) {
    try {
      const url = apiUrl + "/git/trees/" + branch + "?recursive=1";
      const response = await fetch(url);
      if (!response.ok) {
          return null;
      }
      const data = await response.json();
      return data.tree
        .filter((entry) => entry.type === "blob")
        .map((entry) => entry.path);
    } catch (error) {
      console.error("Error fetching files in branch " +  branch + ": ", error);
      return null;
    }
  }

  async function fetchDiffThreeDots(diffApiUrl) {
    try {
      const text = await fetchText(diffApiUrl, {
        headers: {
          Accept: "application/vnd.github.diff",
        },
      });
      return {text: text, count: text?.split("\n")?.length || 0};
    } catch(e) {
      console.log("Error fetching diff: " + e);
      return {text: "", count: 0};
    }
  }

  async function fetchDiffTwoDots(rawContentUrlNew, rawContentUrlBase, apiUrlNew, apiUrlBase, diffNew, diffBase) {
    const [files1, files2] = await Promise.all([
      getFilesInBranch(apiUrlBase, diffBase),
      getFilesInBranch(apiUrlNew, diffNew),
    ]);

    if (files1 === null || files2 === null) {
        throw new Error("Failed to fetch files from branches");
    }

    const allFiles = Array.from(new Set([...files1, ...files2]));
    let diffs = await Promise.all(
      allFiles.map(async (filePath) => {
        const [content1, content2] = await Promise.all([
          getFileContentFromUrl(
            rawContentUrlNew + "/" + diffBase + "/" + filePath
          ),
          getFileContentFromUrl(
            rawContentUrlBase + "/" + diffNew + "/" + filePath
          ),
        ]);

        const diff = Diff.createPatch(filePath, content1, content2);
        if (diff.trim() !== "" && diff.trim().split("\n").length >= 5) {
          return diff;
        }
      })
    );

    diffs = diffs.filter((diff) => diff);
    if (diffs.length) {
      return { text: diffs.join("\n"), count: diffs.length };
    } else {
      return { text: "", count: 0 };
    }
  }

  async function fetchComments(diffApiUrl) {
    // Fetch amount of comments
    try {
      const json = await fetchJson(diffApiUrl);
      let numComments = 0;
      json.commits.forEach(function (row) {
        numComments += row.commit.comment_count;
      });
        document.getElementById("diff-num-comments").textContent =
          "(" + numComments + " comments)";
        document.getElementById("diff-num-comments").style.display = "";
    } catch(e) {
      console.log("Error fetching comments: "+e);
    }
  }

  async function handleDiff() {
    await DOMContentLoaded();
    let copyDiffBtn = document.getElementById("copy-diff");
    if (
      document.queryCommandSupported &&
      document.queryCommandSupported("copy")
    ) {
      copyDiffBtn.addEventListener("click", () => {
        const textarea = document.createElement("textarea");
        textarea.style.position = "fixed";
        textarea.textContent = "curl -s ${h.diff_url(run)}.diff | git apply";
        document.body.append(textarea);
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

    const diffApiUrl = "${h.diff_url(run)}".replace(
      "//github.com/",
      "//api.github.com/repos/"
    );
    
    let dots = 2;

    const testRepo = "${h.tests_repo(run)}";
    const rawContentUrlNew = testRepo.replace(
      "//github.com/",
      "//raw.githubusercontent.com/"
    );
    const apiUrlNew = testRepo.replace(
      "//github.com/",
      "//api.github.com/repos/"
    );

    const diffNew  = "${run["args"]["resolved_new"][:10]}";
    const rawOfficialMaster = "https://raw.githubusercontent.com/official-stockfish/Stockfish";
    const apiOfficialMaster = "https://api.github.com/repos/official-stockfish/Stockfish";
    const baseOfficialMaster = "${run["args"]["official_master_sha"][:10] if run["args"].get("official_master_sha") else ""}";

    % if run["args"].get("spsa"):
      const rawContentUrlBase = rawOfficialMaster;
      const apiUrlBase = apiOfficialMaster;
      % if run["args"].get("official_master_sha"):
          const diffBase = baseOfficialMaster;
      % else: # old tests before this field
          const diffBase = "master";
          dots = 3; // fall back to the three dot diff request as the diff will be rebased
      % endif
    % else:
      const rawContentUrlBase = rawContentUrlNew;
      const apiUrlBase = apiUrlNew;
      const diffBase = "${run["args"]["resolved_base"][:10]}";
    % endif

    // Check if the diff is already in localStorage and use it if it is
    let localStorageDiffs = JSON.parse(localStorage.getItem("localStorageDiffs")) || [];
    localStorageDiffs = localStorageDiffs.filter(diff => diff?.timeStamp >= oneDayAgo);

    let run = localStorageDiffs.find(diff => diff["id"] === "${run['_id']}" && !diff["masterVsBase"]);
    let text = run?.text;
    let count = run?.lines || 0;

    try {
      if (!text) {
        if (dots === 2)
          diffs = await fetchDiffTwoDots(rawContentUrlNew, rawContentUrlBase, apiUrlNew, apiUrlBase, diffNew, diffBase);
        else if (dots === 3)
          diffs = await fetchDiffThreeDots(diffApiUrl);

        text = diffs.text || "No diff available";
        count = diffs.count || 0;

        // Try to save the diff in localStorage
        // It can throw an exception if there is not enough space
        try {
          localStorageDiffs.push({id:"${run['_id']}", text: text, lines: count, masterVsBase: false, timeStamp: currentTime});
          localStorage.setItem("localStorageDiffs", JSON.stringify(localStorageDiffs));
        } catch (e) {
          console.warn("Could not save diff in localStorage");
        }
      }
      fetchComments(diffApiUrl);
    }
    catch {
      text = "API limit rate exceeded, please try 'View on GitHub'";
    }

    const diffContents = document.getElementById("diff-contents");
    const diffText = diffContents.querySelector("code");
    addDiff(diffText, text);
    const toggleBtn = document.getElementById("diff-toggle");
    showDiff(diffContents, diffText, count, copyDiffBtn, toggleBtn);
    hljs.highlightElement(diffText);
    toggleBtn.addEventListener("click", function () {
        diffContents.style.display =
          diffContents.style.display === "none" ? "" : "none";
        if (copyDiffBtn)
          copyDiffBtn.style.display =
            copyDiffBtn.style.display === "none" ? "" : "none";
        if (toggleBtn.textContent === "Hide") toggleBtn.textContent = "Show";
        else toggleBtn.textContent = "Hide";
      });
    document.getElementById("diff-section").style.display = "";

    % if run["args"]["base_tag"] == "master":
      if (baseOfficialMaster) {
        // Check if the diff is already in localStorage and use it if it is
        let run = localStorageDiffs.find(diff => diff["id"] === "${run['_id']}" && diff["masterVsBase"] === true);
        let text = run?.text;

        if (!text) {
           const masterVsOfficialMaster =
             await fetchDiffTwoDots(rawContentUrlBase, rawOfficialMaster, apiUrlBase, apiOfficialMaster, diffBase, baseOfficialMaster);
           text = masterVsOfficialMaster.text;
        }
        
        if (text) {
          document.getElementById("master_vs_official_master").style.display = "";
          const diffContents = document.getElementById("diff-contents");
          const diffText = diffContents.querySelector("code");
          document.getElementById("master_vs_official_master").addEventListener("click", (e) => {
            // Check if the diff is already in localStorage and use it if it is
            let localStorageDiffs = JSON.parse(localStorage.getItem("localStorageDiffs")) || [];
            localStorageDiffs = localStorageDiffs.filter(diff => diff?.timeStamp >= oneDayAgo);
            e.currentTarget.classList.toggle("active");
            if (e.currentTarget.classList.contains("active")) {
                e.currentTarget.querySelector("span").textContent = "base vs master";
                addDiff(diffText, text);
                hljs.highlightElement(diffText);
            }
            else {
              e.currentTarget.querySelector("span").textContent = "master vs base";
              // Check if the diff is already in localStorage and use it if it is
              let run = localStorageDiffs.find(diff => diff["id"] === "${run['_id']}" && diff["masterVsBase"] === false);
              const originalDiffText = run.text;
              const originalDiffCount = run.lines || 0;
              addDiff(diffText, originalDiffText);
              showDiff(diffContents, diffText, originalDiffCount, copyDiffBtn, toggleBtn);
              hljs.highlightElement(diffText);
            }
          });

          // Try to save the diff in localStorage
          // It can throw an exception if there is not enough space
          try {
            localStorageDiffs.push({id:"${run['_id']}", text: text, lines: count, masterVsBase: true, timeStamp: currentTime});
            localStorage.setItem("localStorageDiffs", JSON.stringify(localStorageDiffs));
          } catch (e) {
            console.warn("Could not save diff in localStorage");
          }
        }
      }
    % endif
  }

  const diffPromise = handleDiff();
  const tasksPromise = handleRenderTasks();

  Promise.all([spsaPromise, diffPromise, tasksPromise])
    .then(() => {
    % if show_task >= 0:
      scroll_to(${show_task});
      document.getElementById("enclosure").style="visibility:visible;";
      document.documentElement.style="overflow:scroll;";
    % endif
    });
</script>
