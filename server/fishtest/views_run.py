"""Validate and prepare run creation and modification requests.

Resolve SHAs, discover nets, validate forms, parse SPSA parameters, and manage
run-lifecycle helper behavior.
"""

from __future__ import annotations

import copy
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import regex

import fishtest.github_api as gh
import fishtest.stats.stat_util
from fishtest.util import (
    format_bounds,
    get_hash,
    get_tc_ratio,
    supported_arches,
    tests_repo,
)
from fishtest.views_helpers import _host_url

logger = logging.getLogger(__name__)

_SPSA_PARAM_FIELDS = 6
_RUN_MODIFY_MAX_AGE_DAYS = 30

if TYPE_CHECKING:
    from starlette.responses import RedirectResponse


def get_master_info(  # noqa: C901
    user: str = "official-stockfish",
    repo: str = "Stockfish",
    ignore_rate_limit: bool = False,  # noqa: FBT001, FBT002
) -> dict[str, Any]:
    """Return bench, message, and date for the latest master commit."""
    default_info = {"bench": None, "message": "", "date": ""}

    try:
        commits = gh.get_commits(
            user=user,
            repo=repo,
            ignore_rate_limit=ignore_rate_limit,
        )
    except Exception as e:  # noqa: BLE001
        # Most common production failure: ConnectionError/RemoteDisconnected.
        logger.warning("Exception getting commits:\n%s", e)
        return default_info

    if not isinstance(commits, list) or not commits:
        # GitHub can occasionally return an unexpected JSON shape.
        logger.warning(
            "Unexpected GitHub commits payload; expected non-empty list.",
        )
        return default_info

    bench_search = re.compile(r"(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)")
    latest_bench_match = None

    try:
        message = commits[0]["commit"]["message"].strip().split("\n")[0].strip()
        date_str = commits[0]["commit"]["committer"]["date"]
        date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except Exception as e:  # noqa: BLE001
        logger.warning("Unexpected commit payload shape: %s", e)
        return default_info

    for commit in commits:
        try:
            raw_message = commit["commit"]["message"]
        except KeyError, TypeError:
            # Be tolerant to partial payload corruption in later entries.
            continue
        if not isinstance(raw_message, str):
            continue

        message_lines = raw_message.strip().split("\n")
        for line in reversed(message_lines):
            bench = bench_search.search(line.strip())
            if bench:
                latest_bench_match = {
                    "bench": bench.group(2),
                    "message": message,
                    "date": date.strftime("%b %d"),
                }
                break
        if latest_bench_match:
            break

    if latest_bench_match is None:
        # Keep message/date for PT info text, but leave bench unset.
        return {"bench": None, "message": message, "date": date.strftime("%b %d")}

    return latest_bench_match


def get_sha(branch: str, repo_url: str) -> tuple[str, str]:
    """Resolve a git branch to its SHA commit."""
    user, repo = gh.parse_repo(repo_url)
    try:
        commit = gh.get_commit(user=user, repo=repo, branch=branch)
    except Exception as e:
        msg = f"Unable to access developer repository {repo_url}: {e!s}"
        raise ValueError(msg) from e

    if not isinstance(commit, dict):
        return "", ""

    sha = commit.get("sha")
    if not isinstance(sha, str) or sha == "":
        return "", ""

    message = ""
    commit_data = commit.get("commit")
    if isinstance(commit_data, dict):
        raw_message = commit_data.get("message", "")
        if isinstance(raw_message, str):
            message = raw_message.split("\n", 1)[0]

    return sha, message


def get_nets(commit_sha: str, repo_url: str) -> list[str]:  # noqa: C901
    """Retrieve net filenames from evaluate.h or ucioption.cpp."""
    try:
        nets = []
        pattern = re.compile("nn-[a-f0-9]{12}.nnue")

        user, repo = gh.parse_repo(repo_url)
        options = gh.download_from_github(
            "/src/evaluate.h",
            user=user,
            repo=repo,
            branch=commit_sha,
            method="raw",
        ).decode()
        for line in options.splitlines():
            if "EvalFileDefaultName" in line and "define" in line:
                m = pattern.search(line)
                if m:
                    net = m.group(0)
                    if net not in nets:
                        nets.append(net)

        if nets:
            return nets

        options = gh.download_from_github(
            "/src/ucioption.cpp",
            user=user,
            repo=repo,
            branch=commit_sha,
            method="raw",
        ).decode()
        for line in options.splitlines():
            if "EvalFile" in line and "Option" in line:
                m = pattern.search(line)
                if m:
                    net = m.group(0)
                    if net not in nets:
                        nets.append(net)
    except Exception as e:
        msg = f"Unable to access developer repository {repo_url}: {e!s}"
        raise ValueError(msg) from e
    else:
        return nets


def parse_spsa_params(spsa: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse raw SPSA parameter strings into structured dicts."""
    raw = spsa["raw_params"]
    params = []
    for line in raw.split("\n"):
        chunks = line.strip().split(",")
        if len(chunks) == 1 and chunks[0] == "":  # blank line
            continue
        if len(chunks) != _SPSA_PARAM_FIELDS:
            msg = f"the line {chunks} does not have {_SPSA_PARAM_FIELDS} entries"
            raise ValueError(msg)
        param = {
            "name": chunks[0],
            "start": float(chunks[1]),
            "min": float(chunks[2]),
            "max": float(chunks[3]),
            "c_end": float(chunks[4]),
            "r_end": float(chunks[5]),
        }
        param["c"] = param["c_end"] * spsa["num_iter"] ** spsa["gamma"]
        param["a_end"] = param["r_end"] * param["c_end"] ** 2
        param["a"] = param["a_end"] * (spsa["A"] + spsa["num_iter"]) ** spsa["alpha"]
        param["theta"] = param["start"]
        params.append(param)
    return params


def validate_modify(  # noqa: PLR0911
    request: Any,  # noqa: ANN401
    run: dict[str, Any],
) -> RedirectResponse | None:
    """Return None on success, or a RedirectResponse on validation failure."""
    from starlette.responses import RedirectResponse  # noqa: PLC0415

    now = datetime.now(UTC)
    if (
        "start_time" not in run
        or (now - run["start_time"]).days > _RUN_MODIFY_MAX_AGE_DAYS
    ):
        request.session.flash("Run too old to be modified", "error")
        return RedirectResponse(url="/tests", status_code=302)

    if "num-games" not in request.POST:
        request.session.flash("Unable to modify with no number of games!", "error")
        return RedirectResponse(url="/tests", status_code=302)

    bad_values = not all(
        value is not None and value.replace("-", "").isdigit()
        for value in [
            request.POST["priority"],
            request.POST["num-games"],
            request.POST["throughput"],
        ]
    )

    if bad_values:
        request.session.flash("Bad values!", "error")
        return RedirectResponse(url="/tests", status_code=302)

    num_games = int(request.POST["num-games"])
    if (
        num_games > run["args"]["num_games"]
        and "sprt" not in run["args"]
        and "spsa" not in run["args"]
    ):
        request.session.flash(
            "Unable to modify number of games in a fixed game test!",
            "error",
        )
        return RedirectResponse(url="/tests", status_code=302)

    if "spsa" in run["args"] and num_games != run["args"]["num_games"]:
        request.session.flash(
            "Unable to modify number of games for SPSA"
            " tests, SPSA hyperparams are based off"
            " the initial number of games",
            "error",
        )
        return RedirectResponse(url="/tests", status_code=302)

    max_games = 3200000
    if num_games > max_games:
        request.session.flash("Number of games must be <= " + str(max_games), "error")
        return RedirectResponse(url="/tests", status_code=302)

    return None


def sanitize_options(options: str) -> str:
    """Validate and normalize UCI option key=value pairs."""
    try:
        options.encode("ascii")
    except UnicodeEncodeError:
        msg = "Options must contain only ASCII characters"
        raise ValueError(msg) from None

    tokens = options.split()
    token_regex = re.compile(r"^[^\s=]+=[^\s=]+$", flags=re.ASCII)
    for token in tokens:
        if not token_regex.fullmatch(token):
            msg = (
                "Each option must be a 'key=value' pair"
                " with no extra spaces"
                " and exactly one '='"
            )
            raise ValueError(msg)
    return " ".join(tokens)


def validate_form(request: Any) -> dict[str, Any]:  # noqa: ANN401, C901, PLR0912, PLR0915
    """Extract and validate run-creation form fields."""
    data = {
        "base_tag": request.POST["base-branch"],
        "new_tag": request.POST["test-branch"],
        "tc": request.POST["tc"],
        "new_tc": request.POST["new_tc"],
        "book": request.POST["book"],
        "book_depth": request.POST["book-depth"],
        "base_signature": request.POST["base-signature"],
        "new_signature": request.POST["test-signature"],
        "base_options": sanitize_options(request.POST["base-options"]),
        "new_options": sanitize_options(request.POST["new-options"]),
        "username": request.authenticated_userid,
        "tests_repo": request.POST["tests-repo"],
        "info": request.POST["run-info"],
        "arch_filter": request.POST["arch-filter"],
        "compiler": request.POST["compiler"],
    }
    try:
        # Deal with people that have changed their GitHub username
        # but still use the old repo url
        data["tests_repo"] = gh.normalize_repo(data["tests_repo"])
    except Exception as e:
        msg = f"Unable to access developer repository {data['tests_repo']}: {e!s}"
        raise ValueError(msg) from e

    user, repo = gh.parse_repo(data["tests_repo"])
    username = request.authenticated_userid
    u = request.userdb.get_user(username)

    # Deal with people that have forked from "mcostalba/Stockfish" instead
    # of from "official-stockfish/Stockfish".
    official_repo = "https://github.com/official-stockfish/Stockfish"
    master_repo = official_repo
    try:
        master_repo = gh.get_master_repo(user, repo, ignore_rate_limit=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Unable to determine master repo for %s: %s",
            data["tests_repo"],
            e,
        )
    else:
        if master_repo != official_repo:
            data["master_repo"] = master_repo
            message = (
                f"It seems that your repo {data['tests_repo']} has been forked from "
                f"{master_repo} and not from {official_repo} "
                "as recommended in the wiki. As such,"
                " some functionality may be broken. "
            )
            suffix_soft = (
                "Please consider replacing your repo with one forked from the official "
                "Stockfish repo!"
            )
            suffix_hard = (
                "Please replace your repo with one forked from the official "
                "Stockfish repo!"
            )
            if u["registration_time"] >= datetime(2025, 7, 1, tzinfo=UTC):
                raise ValueError(message + " " + suffix_hard)
            request.session.flash(
                message + " " + suffix_soft,
                "warning",
            )
    odds = request.POST.get("odds", "off")  # off checkboxes are not posted
    if odds == "off":
        data["new_tc"] = data["tc"]

    checkbox_compiler = request.POST.get(
        "checkbox-compiler",
        "off",
    )  # off checkboxes are not posted
    if checkbox_compiler == "off":
        del data["compiler"]

    checkbox_arch_filter = request.POST.get(
        "checkbox-arch-filter",
        "off",
    )  # off checkboxes are not posted
    if checkbox_arch_filter == "off":
        data["arch_filter"] = ""

    if data["arch_filter"] == "":
        del data["arch_filter"]

    # check if arch filter is a valid regular expression
    try:
        if "arch_filter" in data:
            regex.compile(data["arch_filter"])
    except regex.error as e:
        msg = f"Invalid arch filter: {e}"
        raise ValueError(msg) from e

    # check if there are any remaining arches
    if "arch_filter" in data:
        filtered_arches = filter(
            lambda x: (
                regex.search(
                    data["arch_filter"],
                    x,
                )
                is not None
            ),
            supported_arches,
        )
        if list(filtered_arches) == []:
            msg = f"filter {data['arch_filter']} has no compatible arches"
            raise ValueError(msg)

    from vtjson import validate  # noqa: PLC0415

    from fishtest.schemas import tc as tc_schema  # noqa: PLC0415

    validate(tc_schema, data["tc"], "data['tc']")
    validate(tc_schema, data["new_tc"], "data['new_tc']")

    if request.POST.get("rescheduled_from"):
        data["rescheduled_from"] = request.POST["rescheduled_from"]

    def strip_message(m: str) -> str:
        lines = m.strip().split("\n")
        bench_search = re.compile(r"(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)")
        for i, line in enumerate(reversed(lines)):
            new_line, n = bench_search.subn("", line)
            if n:
                lines[-i - 1] = new_line
                break
        s = "\n".join(lines)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n+", r"\n", s)
        return s.rstrip()

    # Fill new_signature/info from commit info if left blank
    if len(data["new_signature"]) == 0 or len(data["info"]) == 0:
        try:
            c = gh.get_commit(
                user=user,
                repo=repo,
                branch=data["new_tag"],
                ignore_rate_limit=True,
            )
        except Exception as e:
            msg = f"Unable to access developer repository {data['tests_repo']}: {e!s}"
            raise ValueError(msg) from e
        if "commit" not in c:
            msg = f"Cannot find branch {data['new_tag']} in developer repository"
            raise ValueError(msg)
        if len(data["new_signature"]) == 0:
            bench_search = re.compile(r"(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)")
            lines = c["commit"]["message"].split("\n")
            for line in reversed(lines):  # Iterate in reverse to find the last match
                m = bench_search.search(line)
                if m:
                    data["new_signature"] = m.group(2)
                    break
            else:
                msg = "This commit has no signature: please supply it manually."
                raise ValueError(msg)
        if len(data["info"]) == 0:
            data["info"] = strip_message(c["commit"]["message"])

    if request.POST["stop_rule"] == "spsa":
        data["base_signature"] = data["new_signature"]

    for k, v in data.items():
        if len(v) == 0:
            msg = f"Missing required option: {k}"
            raise ValueError(msg)

    # Handle boolean options
    data["auto_purge"] = request.POST.get("auto-purge") is not None
    # checkbox is to _disable_ adjudication
    data["adjudication"] = request.POST.get("adjudication") is None

    # In case of reschedule use old data,
    # otherwise resolve sha and update user's tests_repo
    if "resolved_base" in request.POST:
        data["resolved_base"] = request.POST["resolved_base"]
        data["resolved_new"] = request.POST["resolved_new"]
        data["msg_base"] = request.POST["msg_base"]
        data["msg_new"] = request.POST["msg_new"]
    else:
        data["resolved_base"], data["msg_base"] = get_sha(
            data["base_tag"],
            data["tests_repo"],
        )
        data["resolved_new"], data["msg_new"] = get_sha(
            data["new_tag"],
            data["tests_repo"],
        )
        u = request.userdb.get_user(data["username"])
        if u.get("tests_repo", "") != data["tests_repo"]:
            u["tests_repo"] = data["tests_repo"]
            request.userdb.save_user(u)

    if len(data["resolved_base"]) == 0 or len(data["resolved_new"]) == 0:
        msg = "Unable to find branch!"
        raise ValueError(msg)

    # Check entered bench
    if data["base_tag"] == "master":
        master_info = get_master_info(user=user, repo=repo, ignore_rate_limit=True)
        master_bench = (
            master_info.get("bench") if isinstance(master_info, dict) else None
        )
        if master_bench is None:
            # GitHub is transiently unavailable; skip strict verification.
            logger.warning(
                "Unable to verify master bench signature (GitHub API unavailable).",
            )
        elif master_bench != data["base_signature"]:
            msg = (
                "Bench signature of Base master does not match, "
                'please "git pull upstream master" !'
            )
            raise ValueError(msg)

    stop_rule = request.POST["stop_rule"]

    # Store nets info
    data["base_nets"] = get_nets(data["resolved_base"], data["tests_repo"])
    data["new_nets"] = get_nets(data["resolved_new"], data["tests_repo"])

    # Test existence of nets
    missing_nets = []
    for net_name in set(data["base_nets"]) | set(data["new_nets"]):
        net = request.rundb.get_nn(net_name)
        if net is None:
            missing_nets.append(net_name)
    if missing_nets:
        msg = "Missing net(s). Please upload to: {} the following net(s): {}".format(
            _host_url(request),
            ", ".join(missing_nets),
        )
        raise ValueError(msg)

    # Integer parameters
    data["threads"] = int(request.POST["threads"])
    data["priority"] = int(request.POST["priority"])
    data["throughput"] = int(request.POST["throughput"])

    if data["threads"] <= 0:
        msg = "Threads must be >= 1"
        raise ValueError(msg)

    if stop_rule == "sprt":
        # Too small a number results in many API calls,
        # especially with highly concurrent workers.
        # This expression results in 32 games per batch for single threaded STC games.
        # This means a batch with be completed in roughly 2 minutes on a 8 core worker.
        # This expression adjusts the batch size for
        # threads and TC, to keep timings somewhat similar.
        sprt_batch_size_games = 2 * max(
            1,
            int(0.5 + 16 / get_tc_ratio(data["tc"], data["threads"])),
        )
        assert sprt_batch_size_games % 2 == 0  # noqa: S101
        elo_model = request.POST["elo_model"]
        if elo_model not in ["BayesElo", "logistic", "normalized"]:
            msg = "Unknown Elo model"
            raise ValueError(msg)
        data["sprt"] = fishtest.stats.stat_util.SPRT(
            alpha=0.05,
            beta=0.05,
            elo0=float(request.POST["sprt_elo0"]),
            elo1=float(request.POST["sprt_elo1"]),
            elo_model=elo_model,
            batch_size=sprt_batch_size_games // 2,
        )  # game pairs
        # Limit on number of games played.
        data["num_games"] = 800000
    elif stop_rule == "spsa":
        data["num_games"] = int(request.POST["num-games"])
        if data["num_games"] <= 0:
            msg = "Number of games must be >= 0"
            raise ValueError(msg)

        data["spsa"] = {
            "A": int(float(request.POST["spsa_A"]) * data["num_games"] / 2),
            "alpha": float(request.POST["spsa_alpha"]),
            "gamma": float(request.POST["spsa_gamma"]),
            "raw_params": request.POST["spsa_raw_params"],
            "iter": 0,
            "num_iter": int(data["num_games"] / 2),
        }
        data["spsa"]["params"] = parse_spsa_params(data["spsa"])
        if len(data["spsa"]["params"]) == 0:
            msg = "Number of params must be > 0"
            raise ValueError(msg)
    else:
        data["num_games"] = int(request.POST["num-games"])
        if data["num_games"] <= 0:
            msg = "Number of games must be >= 0"
            raise ValueError(msg)

    max_games = 3200000
    if data["num_games"] > max_games:
        msg = "Number of games must be <= " + str(max_games)
        raise ValueError(msg)

    return data


def del_tasks(run: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of a run dict with the tasks key removed."""
    run = copy.copy(run)
    run.pop("tasks", None)
    return copy.deepcopy(run)


def update_nets(request: Any, run: dict[str, Any]) -> None:  # noqa: ANN401, C901
    """Update net metadata timestamps for a run."""
    run_id = str(run["_id"])
    data = run["args"]
    base_nets, new_nets, missing_nets = [], [], []
    for net_name in set(data["base_nets"]) | set(data["new_nets"]):
        net = request.rundb.get_nn(net_name)
        if net is None:
            # This should never happen
            missing_nets.append(net_name)
        else:
            if net_name in data["base_nets"]:
                base_nets.append(net)
            if net_name in data["new_nets"]:
                new_nets.append(net)
    if missing_nets:
        msg = "Missing net(s). Please upload to {} the following net(s): {}".format(
            _host_url(request),
            ", ".join(missing_nets),
        )
        raise ValueError(msg)

    tests_repo_ = tests_repo(run)
    _user, _repo = gh.parse_repo(tests_repo_)
    try:
        if gh.is_master(
            run["args"]["resolved_base"],
        ):
            for net in base_nets:
                if "is_master" not in net:
                    net["is_master"] = True
                    request.rundb.update_nn(net)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Unable to evaluate is_master(%s): %s",
            run["args"]["resolved_base"],
            e,
        )

    for net in new_nets:
        if "first_test" not in net:
            net["first_test"] = {"id": run_id, "date": datetime.now(UTC)}
        net["last_test"] = {"id": run_id, "date": datetime.now(UTC)}
        request.rundb.update_nn(net)


def new_run_message(request: Any, run: dict[str, Any]) -> str:  # noqa: ANN401
    """Build the summary message string for a new run."""
    if "sprt" in run["args"]:
        sprt = run["args"]["sprt"]
        elo_model = sprt.get("elo_model")
        ret = f"SPRT{format_bounds(elo_model, sprt['elo0'], sprt['elo1'])}"
    elif "spsa" in run["args"]:
        ret = f"SPSA[{run['args']['num_games']}]"
    else:
        ret = f"NumGames[{run['args']['num_games']}]"
        if run["args"]["resolved_base"] == request.rundb.pt_info["pt_branch"]:
            ret += f"(PT:{request.rundb.pt_info['pt_version']})"
    ret += f" TC:{run['args']['tc']}"
    ret += (
        f"[{run['args']['new_tc']}]"
        if run["args"]["new_tc"] != run["args"]["tc"]
        else ""
    )
    ret += "(LTC)" if run["tc_base"] >= request.rundb.ltc_lower_bound else ""
    ret += f" Book:{run['args']['book']}"
    ret += f" Threads:{run['args']['threads']}"
    ret += "(SMP)" if run["args"]["threads"] > 1 else ""
    base_hash = get_hash(run["args"]["base_options"])
    new_hash = get_hash(run["args"]["new_options"])
    ret += f" Hash:{base_hash}/{new_hash}"
    return ret


def is_same_user(request: Any, run: dict[str, Any]) -> bool:  # noqa: ANN401
    """Check whether the authenticated user owns the run."""
    return run["args"]["username"] == request.authenticated_userid


def can_modify_run(request: Any, run: dict[str, Any]) -> bool:  # noqa: ANN401
    """Check whether the user may modify the run."""
    return is_same_user(request, run) or request.has_permission("approve_run")
