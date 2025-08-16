"use strict";

// TODO: Uncomment the following lines and comment out the test configuration below when deploying to production.

// const pullRequestDstUser = "official-stockfish";
// const pullRequestDstRepo = "Stockfish";

// For testing
const pullRequestDstUser = "vdbergh";
const pullRequestDstRepo = "Stockfish";

let pullRequestServerURL;
try {
  pullRequestServerURL = `${window.location.protocol}//${window.location.hostname}`;
} catch (e) {
  pullRequestServerURL = "https://tests.stockfishchess.org";
}

const apiTimeout = 3000;

async function renderMarkDownAPI(text, token, timeout) {
  const url = `https://api.github.com/markdown`;
  const payload = {
    text: text,
    mode: "gfm",
    context: `${pullRequestDstUser}/${pullRequestDstRepo}`,
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

async function getCommitAPI(user, repo, branch, token, timeout) {
  const url = `https://api.github.com/repos/${user}/${repo}/commits/${branch}?per_page=1`;
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

function renderResults(run) {
  const llr = run.args.sprt.llr.toFixed(2);
  const lower_bound = run.args.sprt.lower_bound.toFixed(2);
  const upper_bound = run.args.sprt.upper_bound.toFixed(2);
  const elo0 = run.args.sprt.elo0.toFixed(2);
  const elo1 = run.args.sprt.elo1.toFixed(2);
  const wins = run.results.wins;
  const draws = run.results.draws;
  const losses = run.results.losses;
  const total = wins + draws + losses;
  const [p0, p1, p2, p3, p4] = run.results.pentanomial;
  const state = run.args.sprt.state;
  const threads = run.args.threads;
  const tc = run.args.tc;
  const m = tc.match(String.raw`^(\d+(\.\d+)?)`);
  let tc_base;
  if (m) {
    tc_base = Number(m[1]);
  }
  let results = "";
  // TODO: incorporate increment
  const duration = threads * tc_base;
  if (duration < 10) {
    results += `VSTC (${tc} th${threads}) was ${state}:\n`;
  } else if (duration >= 10 && duration < 60) {
    results += `STC (${tc} th${threads}) was ${state}:\n`;
  } else if (duration >= 60 && duration < 180) {
    results += `LTC (${tc} th${threads}) was ${state}:\n`;
  } else if (duration >= 180 && duration < 8 * 60) {
    results += `VLTC (${tc} th${threads}) was ${state}:\n`;
  } else if (duration > 8 * 60) {
    results += `VVLTC (${tc} th${threads}) was ${state}:\n`;
  }
  const url = `${pullRequestServerURL}/tests/view/${run._id}`;
  results += `LLR: ${llr} (${lower_bound},${upper_bound}) <${elo0},${elo1}>\n`;
  results += `Total: ${total} W: ${wins} L: ${losses} D: ${draws}\n`;
  results += `Ptnml(0-2): ${p0}, ${p1}, ${p2}, ${p3}, ${p4}\n`;
  results += `<a href="${url}">${url}</a>\n`;
  return results;
}

class PullRequest {
  constructor() {
    this._title = "";
    this._body = "";
    this.runIdCache = {};
    this.commitCache = {};
    this.numberCache = {};
    this.renderedBodyCache = null;
    this.timeout = apiTimeout;
  }

  set body(body) {
    if (body != this.body) {
      this.renderedBodyCache = null;
    }
    this._body = body;
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
    let o = { title: this.title, body: this.body };
    saveObject("pull_request", o);
  }

  load() {
    this.clear();
    const o = loadObject("pull_request");
    if (o) {
      this.title = o.title;
      this.body = o.body;
    }
  }

  clear() {
    this.title = "";
    this.body = "";
  }

  add(runId) {
    this.body += `\n#${runId}\n`;
    this.body = this.body.trim() + "\n";
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
    body = body.trim() + "\n";
    this.body = body;
  }

  async getRun(runId) {
    if (!this.runIdCache[runId]) {
      const url = `/api/get_run/${runId}`;
      console.log(`getRun (${url})`);
      const run = await fetchJson(url);
      run.start_time = Date.parse(run.start_time);
      run.last_updated = Date.parse(run.last_updated);
      if (!run.args.sprt) {
        throw new Error("Pull requests can only contain SPRT tests");
      }
      if (run.args.sprt.elo_model != "normalized") {
        throw new Error(
          "Pull requests can only contain tests using normalized Elo",
        );
      }
      if (!run.args.sprt.state) {
        throw new Error("Pull requests can only contain finished tests");
      }
      if (run.args.new_tc && run.args.tc != run.args.new_tc) {
        throw new Error("Pull requests cannot contain time odds tests");
      }
      this.runIdCache[runId] = run;
    }
    return this.runIdCache[runId];
  }

  getRunIds() {
    const lines = this.body.split("\n");
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
    if (runs.length === 0) {
      throw new Error("A pull request must contain at least one test result");
    }
    let latest = null;
    let bench;
    let tests_repo;
    let branch = null;
    let noFunctionalChange = true;
    for (const run of runs) {
      if (branch && branch != run.args.new_tag) {
        throw new Error("Tests in pull request do not use the same branch");
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
    let user, repo;
    [user, repo] = parseRepo(tests_repo);

    return {
      bench: bench,
      user: user,
      repo: repo,
      branch: branch,
      noFunctionalChange: noFunctionalChange,
    };
  }

  async renderTitle(token) {
    if (this.title) {
      return escapeHtml(this.title);
    } else {
      const userData = await this.getUserData();
      let commit;
      // TODO: incorporate user
      if (this.commitCache[userData.branch]) {
        commit = this.commitCache[userData.branch];
      } else {
        commit = await getCommitAPI(
          userData.user,
          userData.repo,
          userData.branch,
          token,
          this.timeout,
        );
        this.commitCache[userData.branch] = commit;
      }
      const lines = commit["commit"]["message"].split("\n");
      return escapeHtml(lines[0]);
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
    if (this.commitCache[userData.branch]) {
      commit = this.commitCache[userData.branch];
    } else {
      commit = await getCommitAPI(
        userData.user,
        userData.repo,
        userData.branch,
        token,
        this.timeout,
      );
      this.commitCache[userData.branch] = commit;
    }
    const benchRe = /(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)/;
    const lines1 = commit["commit"]["message"].split("\n").reverse();
    if (userData.noFunctionalChange) {
      body += `\nNo functional change\n`;
    } else {
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
        // TODO: add warning
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
    const markDown = await renderMarkDownAPI(text, token, this.timeout);
    this.renderedBodyCache = markDown;
    return markDown;
  }

  async getNumber(token) {
    const runs = await this.getRuns();
    if (runs.length === 0) {
      return false;
    }
    const userData = await this.getUserData();
    // TODO: user
    if (this.numberCache[userData.branch]) {
      return this.numberCache[userData.branch];
    }
    const options = {
      state: "all",
      timeout: this.timeout,
      dst_user: pullRequestDstUser,
      dst_repo: pullRequestDstRepo,
      src_user: userData.user,
      src_ref: userData.branch,
      token: token,
    };
    const PR = await getPullRequestByRefAPI(options);
    if (PR) {
      this.numberCache[userData.branch] = PR.number;
    }
    return PR ? PR.number : null;
  }

  async submit(token) {
    const userData = await this.getUserData();
    const options = {
      src_user: userData.user,
      src_repo: userData.repo,
      src_ref: userData.branch,
      dst_user: pullRequestDstUser,
      dst_repo: pullRequestDstRepo,
      dst_ref: "master",
      token: token,
      timeout: this.timeout,
    };
    let body;
    body = await this.renderBodyText(token);
    options.title = await this.renderTitle(token);
    options.body = body;
    // TODO Incorporate user
    if (this.numberCache[userData.branch]) {
      options.number = this.numberCache[userData.branch];
    }
    const number = await handlePullRequest(options);
    this.numberCache[userData.branch] = number;
    return number;
  }
}
