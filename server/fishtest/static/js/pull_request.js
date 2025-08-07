"use strict";

let pullRequestServerURL;
try {
  pullRequestServerURL = `${window.location.protocol}//${window.location.hostname}`;
} catch (e) {
  pullRequestServerURL = "https://tests.stockfishchess.org";
}

const apiTimeout = 3000;

async function getOAutScopesAPI(token, timeout) {
  if (!isClassicPAT(token)) {
    throw new Error("X-OAuth-Scopes are only defined for classic PATs");
  }
  if (!timeout) {
    timeout = apiTimeout;
  }
  const url = "https://api.github.com/rate_limit";
  const options = {
    method: "GET",
    signal: abortTimeout(timeout),
    headers: {
      Accept: "application/vnd.github+json",
      ...(token && { Authorization: `Bearer ${token}` }),
    },
  };
  console.log(`rateLimitAPI (${url}): ` + JSON.stringify(options));
  const response = await fetch(url, options);
  raiseForStatus(response);
  const headers = response.headers;
  const headers_ = headers.get("X-OAuth-Scopes").split(",");
  const headers__ = [];
  for (const header of headers_) {
    headers__.push(header.trim());
  }
  return headers__;
}

async function renderMarkDownAPI(text, dstUser, dstRepo, token, timeout) {
  if (!timeout) {
    timeout = apiTimeout;
  }
  const url = `https://api.github.com/markdown`;
  const payload = {
    text: text,
    mode: "gfm",
    context: `${dstUser}/${dstRepo}`,
  };
  const options = {
    method: "POST",
    signal: abortTimeout(timeout),
    headers: {
      Accept: "application/vnd.github+json",
      ...(token && { Authorization: `Bearer ${token}` }),
    },
    body: JSON.stringify(payload),
  };
  console.log(`renderMarkDownAPI (${url}): ${JSON.stringify(options)}`);
  return await fetchText(url, options);
}

async function renderMarkDownRawAPI(text, token, timeout) {
  if (!timeout) {
    timeout = apiTimeout;
  }
  const url = `https://api.github.com/markdown/raw`;
  const payload = {
    text: text,
    mode: "markdown",
  };
  const options = {
    method: "POST",
    signal: abortTimeout(timeout),
    headers: {
      Accept: "text/html",
      "Content-Type": "text/plain",
      ...(token && { Authorization: `Bearer ${token}` }),
    },
    body: text,
  };
  console.log(`renderMarkDownRawAPI (${url}): ${JSON.stringify(options)}`);
  return await fetchText(url, options);
}

async function getCommitAPI(user, repo, branch, token, timeout) {
  if (!timeout) {
    timeout = apiTimeout;
  }
  const url = `https://api.github.com/repos/${user}/${repo}/commits/${branch}`;
  const options = {
    method: "GET",
    signal: abortTimeout(timeout),
    headers: {
      Accept: "application/vnd.github+json",
      ...(token && { Authorization: `Bearer ${token}` }),
    },
  };
  console.log(`getCommitAPI (${url}): ` + JSON.stringify(options));

  const json = await fetchJson(url, options);
  return json;
}

async function getCommitsAPI(user, repo, branch, number, token, timeout) {
  if (!timeout) {
    timeout = apiTimeout;
  }
  const url = `https://api.github.com/repos/${user}/${repo}/commits?ref=${branch}&per_page=${number}`;
  const options = {
    method: "GET",
    signal: abortTimeout(timeout),
    headers: {
      Accept: "application/vnd.github+json",
      ...(token && { Authorization: `Bearer ${token}` }),
    },
  };
  console.log(`getCommitAPI (${url}): ` + JSON.stringify(options));

  const json = await fetchJson(url, options);
  return json;
}

/*
  vtjson schema for options:
  {
        "title?": src,
        "body?": src,
        "number?": int,
        "src_user?": src,
        "src_repo?": src,
        "src_ref?": src,
        "dst_user?": src,
        "dst_repo?": src,
        "dst_ref?": src,
        "token?": src,
        "state?": union("open", "closed"),
        "timeout?": int,
        "number?": int,
  }
*/

async function submitPullRequestAPI(options) {
  const url = `https://api.github.com/repos/${options.dst_user}/${options.dst_repo}/pulls`;
  if (!options.title) {
    throw new Error("A pull request cannot have an empty title");
  }
  const payload = {
    title: options.title,
    body: options.body,
    head: `${options.src_user}:${options.src_ref}`,
    head_repo: `${options.src_repo}`,
    base: options.dst_ref,
  };
  const options_ = {
    method: "POST",
    signal: abortTimeout(options.timeout),
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${options.token}`,
    },
    body: JSON.stringify(payload),
  };
  console.log(`submitPullRequestAPI (${url}): ` + JSON.stringify(options_));
  const json = await fetchJson(url, options_);
  return json;
}

async function updatePullRequestAPI(options) {
  if (!options.number) {
    throw new Error("Missing number in update request");
  }
  if (!options.title) {
    throw new Error("A pull request cannot have an empty title");
  }
  const url = `https://api.github.com/repos/${options.dst_user}/${options.dst_repo}/pulls/${options.number}`;
  const payload = {
    title: options.title,
    body: options.body,
    state: options.state,
  };
  const options_ = {
    method: "PATCH",
    signal: abortTimeout(options.timeout),
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${options.token}`,
    },
    body: JSON.stringify(payload),
  };
  console.log(`updatePullRequestAPI (${url}): ` + JSON.stringify(options_));
  const json = await fetchJson(url, options_);
  return json;
}

async function getPullRequestByNumberAPI(options) {
  if (!options.number) {
    throw new Error("Missing number when getting pull request by number");
  }
  const url = `https://api.github.com/repos/${options.dst_user}/${options.dst_repo}/pulls/${options.number}`;
  const options_ = {
    method: "GET",
    signal: abortTimeout(options.timeout),
    headers: {
      Accept: "application/vnd.github+json",
      ...(options.token && { Authorization: `Bearer ${options.token}` }),
    },
  };
  console.log(
    `getPullRequestByNumberAPI (${url}): ` + JSON.stringify(options_),
  );
  const json = await fetchJson(url, options_);
  return json;
}

// Unfortunately this only seems to work with some delay after creating/closing a PR
async function getPullRequestByRefAPI(options) {
  let url;
  url = `https://api.github.com/repos/${options.dst_user}/${options.dst_repo}/pulls?per_page=1&head=${options.src_user}:${options.src_ref}`;
  if (options.state) {
    url += `&state=${options.state}`;
  }
  const options_ = {
    method: "GET",
    signal: abortTimeout(options.timeout),
    headers: {
      Accept: "application/vnd.github+json",
      ...(options.token && { Authorization: `Bearer ${options.token}` }),
    },
  };
  console.log(`getPullRequestByRefAPI (${url}): ` + JSON.stringify(options_));
  const json = await fetchJson(url, options_);
  if (json.length === 0) {
    return null;
  }
  return json[0];
}

async function handlePullRequest(options) {
  let options_ = {};
  Object.assign(options_, options);
  if (!options_.timeout) {
    options_.timeout = apiTimeout;
  }
  let PR;
  if (options_.number) {
    PR = await getPullRequestByNumberAPI(options_);
    if (PR && !PR.merged) {
      options_.state = "open";
      PR = await updatePullRequestAPI(options_);
      return PR.number;
    }
  }
  options_.state = "all";
  PR = await getPullRequestByRefAPI(options_);
  if (PR && !PR.merged_at) {
    options_.number = PR.number;
    options_.state = "open";
    PR = await updatePullRequestAPI(options_);
  } else {
    PR = await submitPullRequestAPI(options_);
  }
  return PR.number;
}

async function validateToken(token, timeout) {
  const noTokenMessage = `You have to install a <a href=https://github.com/settings/tokens>
                          classic GitHub personal access token</a> with <strong>repo scope</strong>
                          in your <a href=/user>profile</a>`;

  if (!timeout) {
    timeout = apiTimeout;
  }
  if (token.trim() === "") {
    throw new Error("You haven't installed a token<br>" + noTokenMessage);
  }
  if (isFineGrainedPAT(token)) {
    throw new Error("A fine-grained token does not work<br>" + noTokenMessage);
  }
  if (isClassicPAT(token)) {
    const scopes = await getOAutScopesAPI(token, timeout);
    if (scopes.indexOf("repo") == -1) {
      throw new Error(
        "Your token does not have repo scope<br>" + noTokenMessage,
      );
    }
  } else {
    throw new Error("Unknown token type<br>" + noTokenMessage);
  }
}

function normalizeText(text) {
  // Removes initial blank lines.
  // Remove final blank lines.
  // Collapses consecutive blank lines.
  // Removes white space on right of lines.
  // Makes sure that string ends with \n
  const lines = text.split("\n");
  let out = "";
  let state = "start"; // start, reading, skipblank
  for (const line of lines) {
    if (state === "start") {
      if (line.trim() != "") {
        out += line.trimEnd() + "\n";
        state = "reading";
      }
    } else if (state === "reading") {
      if (line.trim() == "") {
        state = "skipblank";
      } else {
        out += line.trimEnd() + "\n";
      }
    } else if (state === "skipblank") {
      if (line.trim() != "") {
        out += "\n" + line.trimEnd() + "\n";
        state = "reading";
      }
    }
  }
  return out;
}

function removeBlankLines(text) {
  // Removes blank lines.
  // Strips lines
  // Makes sure that string ends with \n
  const lines = text.split("\n");
  let out = "";
  for (const line of lines) {
    if (line.trim() != "") {
      out += line.trim() + "\n";
    }
  }
  return out;
}

function renderResults(run) {
  let results = "";
  const tcString = run.pullState.tc_string;
  const tc = run.args.tc;
  const threads = run.args.threads;
  if (run.args.sprt) {
    const state = run.args.sprt.state;
    if (run.pullState.non_regression) {
      results += "Non-regression ";
    }
    results += `${tcString} (${tc} th${threads}) was ${state}:\n`;
  } else if (run.args.spsa) {
    results += "SPSA:\n";
  } else {
    // Must be num_games
    results += `${tcString} (${tc} th${threads}) elo measurement:\n`;
  }
  const info = run.pullState.info;
  results += info;
  const url = `${pullRequestServerURL}/tests/view/${run._id}`;
  results += `<a href="${url}">${url}</a>\n`;
  const messages = run.pullState.messages;
  for (const message of messages) {
    results += `Note: ${message.toLowerCase()}\n`;
  }
  return results;
}

function getRunIds(body) {
  const lines = body.split("\n");
  const runIdMarker = /#([0-9a-f]{24})/;
  let runs = [];
  for (let line of lines) {
    line = line.trim();
    const m = line.match(runIdMarker);
    if (m) {
      runs.push(m[1]);
    }
  }
  return runs;
}

class PullRequest {
  constructor() {
    this.saveName = "pull-request-v1";
    this._title = "";
    this._body = "";
    this.srcUser = "";
    this.srcRepo = "";
    this.srcBranch = "";
    this.dstUser = "";
    this.dstRepo = "";
    this.runIdCache = {};
    this.pullStateCache = {};
    this.commitCache = {};
    this.numberCache = {};
    this.renderedBodyCache = null;
    this.masterCache = null;
    this.timeout = apiTimeout;
  }

  set body(body) {
    if (body != this._body) {
      this.renderedBodyCache = null;
    }
    const saved_body = this._body;
    this._body = normalizeText(body);
    if (
      JSON.stringify(getRunIds(body)) != JSON.stringify(getRunIds(saved_body))
    ) {
      const runIdsChangeEvent = new CustomEvent("runidschange", {
        detail: { PR: this },
      });
      document.dispatchEvent(runIdsChangeEvent);
    }
  }

  get body() {
    return this._body;
  }

  set title(title) {
    this._title = title;
  }

  get title() {
    return this._title;
  }

  save() {
    let o = {
      title: this.title,
      body: this.body,
      srcUser: this.srcUser,
      srcRepo: this.srcRepo,
      srcBranch: this.srcBranch,
      dstUser: this.dstUser,
      dstRepo: this.dstRepo,
    };
    saveObject(this.saveName, o);
  }

  load() {
    const o = loadObject(this.saveName);
    if (o) {
      this.title = o.title;
      this.body = o.body;
      // For backward compatibility
      this.srcUser = o.srcUser ?? "";
      this.srcRepo = o.srcRepo ?? "";
      this.srcBranch = o.srcBranch ?? "";
      this.dstUser = o.dstUser ?? "";
      this.dstRepo = o.dstRepo ?? "";
    } else {
      this.title = "";
      this.body = "";
      this.srcUser = "";
      this.srcRepo = "";
      this.srcBranch = "";
      this.dstUser = "";
      this.dstRepo = "";
    }
  }

  clear() {
    this.title = "";
    this.body = "";
  }

  add(runId) {
    this.body += `\n#${runId}\n`;
  }

  remove(runId) {
    let lines = this.body.split("\n");
    let body = "";
    const runIdMarker = /#([0-9a-f]{24})/;
    for (const line of lines) {
      const m = line.match(runIdMarker);
      if (m && m[1] === runId) {
        continue;
      }
      body += line + "\n";
    }
    this.body = body;
  }

  async pullState(runId) {
    if (this.pullStateCache[runId] != undefined) {
      return this.pullStateCache[runId];
    }
    const url = `/api/pull_state/${runId}`;
    console.log(`pullState (${url})`);
    const pullState = await fetchJson(url);
    this.pullStateCache[runId] = pullState;
    return this.pullStateCache[runId];
  }

  async getRun(runId) {
    if (!this.runIdCache[runId]) {
      const url = `/api/get_run/${runId}`;
      console.log(`getRun (${url})`);
      const run = await fetchJson(url);
      run.start_time = Date.parse(run.start_time);
      run.last_updated = Date.parse(run.last_updated);

      const pullState = await this.pullState(runId);
      run["pullState"] = pullState;
      this.runIdCache[runId] = run;
    }
    return this.runIdCache[runId];
  }

  getRunIds() {
    return getRunIds(this.body);
  }

  contains(runId) {
    const runIds = this.getRunIds();
    if (runIds.indexOf(runId) != -1) {
      return true;
    } else {
      return false;
    }
  }

  async getRuns() {
    const runIds = this.getRunIds();
    let runs = [];
    for (const runId of runIds) {
      const run = await this.getRun(runId);
      runs.push(run);
    }
    return runs;
  }

  async getUserData() {
    const runs = await this.getRuns();
    let latest = null;
    let bench;
    let tests_repo;
    let branch = null;
    let noFunctionalChange = true;
    // TODO: replace by "branchList"
    let nonUniqueBranch = false;
    for (const run of runs) {
      if (branch && branch != run.args.new_tag) {
        nonUniqueBranch = true;
      }
      branch = run.args.new_tag;
      if (!latest || run.start_time > latest) {
        bench = Number(run.args.new_signature);
        tests_repo = run.args.tests_repo;
        if (run.args.new_signature != run.args.base_signature) {
          noFunctionalChange = false;
        }
        latest = run.start_time;
      }
    }
    let user = "",
      repo = "";
    if (tests_repo) {
      [user, repo] = parseRepo(tests_repo);
    }
    user = this.srcUser || user;
    repo = this.srcRepo || repo;
    if (this.srcBranch) {
      nonUniqueBranch = false;
      branch = this.srcBranch;
    }

    const userBranchKey = `${user}:${branch}`;

    return {
      bench: bench,
      user: user,
      repo: repo,
      branch: branch,
      userBranchKey: userBranchKey,
      nonUniqueBranch: nonUniqueBranch,
      noFunctionalChange: noFunctionalChange,
      runCount: runs.length,
    };
  }

  async getCommit(token) {
    const userData = await this.getUserData();
    let commit;
    if (this.commitCache[userData.userBranchKey]) {
      commit = this.commitCache[userData.userBranchKey];
    } else {
      commit = await getCommitAPI(
        userData.user,
        userData.repo,
        userData.branch,
        token,
        this.timeout,
      );
      this.commitCache[userData.userBranchKey] = commit;
    }
    return commit;
  }

  async branchLink() {
    const userData = await this.getUserData();
    const url = `https://github.com/${userData.user}/${userData.repo}/commits/${userData.branch}`;
    const link = `<a href="${url}" target="github">${userData.userBranchKey}</a>`;
    return link;
  }

  async getMaster(token) {
    if (this.masterCache) {
      return this.masterCache;
    }
    this.masterCache = await getCommitAPI(
      "official-stockfish",
      "Stockfish",
      "master",
      token,
      this.timeout,
    );
    return this.masterCache;
  }

  async branchIsRebasedAndSquashed(token) {
    const master = await this.getMaster(token);
    const head = await this.getCommit(token);
    const headParents = head.parents;
    if (headParents.length != 1) {
      return false;
    }
    const masterSha = master.sha;
    const headParentsSha = headParents[0].sha;
    return masterSha === headParentsSha;
  }

  async renderTitle(token) {
    if (this.title) {
      return escapeHtml(this.title);
    } else {
      const userData = await this.getUserData();
      if (userData.branch) {
        const commit = await this.getCommit(token);
        const lines = commit["commit"]["message"].split("\n");
        return escapeHtml(lines[0]);
      }
      return "";
    }
  }

  async renderBodyText(token) {
    const lines = this.body.split("\n");
    const runIdMarker = /#([0-9a-f]{24})/;
    const userData = await this.getUserData();
    let body = "";
    for (let line of lines) {
      const line1 = line.trim();
      const m = line1.match(runIdMarker);
      if (m) {
        const run = await this.getRun(m[1]);
        body += renderResults(run);
      } else {
        body += line + "\n";
      }
    }
    let commit;
    if (userData.branch) {
      if (this.commitCache[userData.userBranchKey]) {
        commit = this.commitCache[userData.userBranchKey];
      } else {
        commit = await getCommitAPI(
          userData.user,
          userData.repo,
          userData.branch,
          token,
          this.timeout,
        );
        this.commitCache[userData.userBranchKey] = commit;
      }
    }
    const benchRe = /(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)/;
    if (!userData.runCount) {
      body += `\nNo functional change\n`;
    } else if (userData.noFunctionalChange) {
      body += `\nNo functional change\n`;
    } else {
      const lines1 = commit["commit"]["message"].split("\n").reverse();
      let bench = null;
      for (const line of lines1) {
        const n = line.match(benchRe);
        if (n) {
          bench = Number(n[2]);
        }
      }
      if (bench != null) {
        body += `\nBench: ${bench}\n`;
      } else {
        body += `\nBench: ${userData.bench}\n`;
      }
    }
    return body;
  }

  async renderBody(token) {
    if (this.renderedBodyCache) {
      return this.renderedBodyCache;
    }
    const text = await this.renderBodyText(token);
    const markDown = await renderMarkDownAPI(
      text,
      this.dstUser,
      this.dstRepo,
      token,
      this.timeout,
    );
    this.renderedBodyCache = markDown;
    return markDown;
  }

  async getNumber(token) {
    const runs = await this.getRuns();
    if (runs.length === 0) {
      return false;
    }
    const userData = await this.getUserData();
    if (this.numberCache[userData.userBranchKey]) {
      return this.numberCache[userData.userBranchKey];
    }
    const options = {
      state: "all",
      timeout: this.timeout,
      dst_user: this.dstUser,
      dst_repo: this.dstRepo,
      src_user: userData.user,
      src_ref: userData.branch,
      token: token,
    };
    const PR = await getPullRequestByRefAPI(options);
    if (PR) {
      this.numberCache[userData.userBranchKey] = PR.number;
    }
    return PR ? PR.number : null;
  }

  async submit(token) {
    const userData = await this.getUserData();
    const options = {
      src_user: userData.user,
      src_repo: userData.repo,
      src_ref: userData.branch,
      dst_user: this.dstUser,
      dst_repo: this.dstRepo,
      dst_ref: "master",
      token: token,
      timeout: this.timeout,
    };
    let body;
    body = await this.renderBodyText(token);
    options.title = await this.renderTitle(token);
    options.body = body;
    if (this.numberCache[userData.userBranchKey]) {
      options.number = this.numberCache[userData.userBranchKey];
    }
    const number = await handlePullRequest(options);
    this.numberCache[userData.userBranchKey] = number;
    return number;
  }
}
