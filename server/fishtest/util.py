import smtplib
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText

import fishtest.stats.stat_util
import numpy
import scipy.stats
from zxcvbn import zxcvbn


FISH_URL = "https://tests.stockfishchess.org/tests/view/"


def unique_key(worker_info):
    if unique_key in worker_info:
        return worker_info["unique_key"]
    else:
        # provide a mock unique key for very old tests
        # which did not have a unique_key
        return worker_name(worker_info)


def worker_name(worker_info):
    # A user friendly name for the worker.
    username = worker_info.get("username", "")
    cores = str(worker_info["concurrency"])
    uuid = worker_info.get("unique_key", "")
    name = "%s-%scores" % (username, cores)
    if len(uuid) != 0:
        name += "-" + uuid.split("-")[0]
    return name


def get_chi2(tasks, bad_users):
    """Perform chi^2 test on the stats from each worker"""

    default_results = {
        "chi2": float("nan"),
        "dof": 0,
        "p": float("nan"),
        "residual": {},
    }

    # Aggregate results by worker
    users = {}
    has_pentanomial = None
    for task in tasks:
        if "worker_info" not in task:
            continue
        key = unique_key(task["worker_info"])
        if key in bad_users:
            continue
        stats = task.get("stats", {})
        if has_pentanomial is None:
            has_pentanomial = "pentanomial" in stats
        if not has_pentanomial:
            wld = [
                float(stats.get("wins", 0)),
                float(stats.get("losses", 0)),
                float(stats.get("draws", 0)),
            ]
        else:
            p = stats.get("pentanomial", 5 * [0])  # there was a small window
            # in time where we could have both trinomial and pentanomial
            # workers

            # The ww and ll frequencies will typically be too small for
            # the full pentanomial chi2 test to be valid. See e.g. the last page of
            # https://www.open.ac.uk/socialsciences/spsstutorial/files/tutorials/chi-square.pdf.
            # So we combine the ww and ll frequencies with the wd and ld frequencies.
            wld = [float(p[4] + p[3]), float(p[0] + p[1]), float(p[2])]
        if key in users:
            for idx in range(len(wld)):
                users[key][idx] += wld[idx]
        else:
            users[key] = wld

    # We filter out the workers whose expected frequences are <= 5 as
    # they break the chi2 test.
    filtering_done = False
    while not filtering_done:
        # Wheneve less than two qualifying workers are left,
        # we bail out and just return "something".
        if len(users) <= 1:
            return default_results
        # Now do the matrix computations with numpy.
        observed = numpy.array(list(users.values()))
        rows, columns = observed.shape
        column_sums = numpy.sum(observed, axis=0)
        row_sums = numpy.sum(observed, axis=1)
        grand_total = numpy.sum(column_sums)
        # if no games have been received, we cannot continue
        if grand_total == 0:
            return default_results
        expected = numpy.outer(row_sums, column_sums) / grand_total
        keys = list(users)
        filtering_done = True
        for idx in range(len(keys)):
            if min(expected[idx]) <= 5:
                del users[keys[idx]]
                filtering_done = False

    # Now we do the basic chi2 computation.
    df = (rows - 1) * (columns - 1)
    raw_residual = observed - expected
    chi2 = numpy.sum(raw_residual * raw_residual / expected)
    p_value = 1 - scipy.stats.chi2.cdf(chi2, df)

    # Finally we also compute for each qualifying worker two residuals
    # indicating how badly it deviates from the norm.

    res_draw = fishtest.stats.stat_util.residuals(numpy.array([0, 0, 1]), observed)
    res_elo = fishtest.stats.stat_util.residuals(numpy.array([1, -1, 0]), observed)

    for idx in range(len(keys)):
        users[keys[idx]] = {"res_draw": res_draw[idx], "res_elo": res_elo[idx]}

    return {"chi2": chi2, "dof": df, "p": p_value, "residual": users}


def calculate_residuals(run):
    bad_users = set()
    chi2 = get_chi2(run["tasks"], bad_users)
    residuals = chi2["residual"]

    # Limit bad users to 1 for now
    for _ in range(1):
        worst_user = {}
        for task in run["tasks"]:
            if "worker_info" not in task:
                continue
            if unique_key(task["worker_info"]) in bad_users:
                continue
            task["residual"] = residuals.get(
                unique_key(task["worker_info"]),
                {"res_draw": float("inf"), "res_elo": float("inf")},
            )

            # Special case crashes or time losses
            stats = task.get("stats", {})
            crashes = stats.get("crashes", 0)
            if crashes > 3:
                task["residual"]["res_draw"] = 8.0
                task["residual"]["res_elo"] = 8.0

            task["residual_color"] = {}
            for res in ("res_draw", "res_elo"):
                if abs(task["residual"][res]) < 2.0:
                    task["residual_color"][res] = "#44EB44"
                elif abs(task["residual"][res]) < 2.7:
                    task["residual_color"][res] = "yellow"
                else:
                    task["residual_color"][res] = "#FF6A6A"

            if chi2["p"] < 0.05 or abs(task["residual"]["res_elo"]) > 3.0:
                if len(worst_user) == 0 or (
                    abs(task["residual"]["res_elo"])
                    > abs(worst_user["residual"]["res_elo"])
                    and task["residual"]["res_elo"] != float("inf")
                ):
                    worst_user["unique_key"] = unique_key(task["worker_info"])
                    worst_user["residual"] = task["residual"]

        if len(worst_user) == 0:
            break
        bad_users.add(worst_user["unique_key"])
        residuals = get_chi2(run["tasks"], bad_users)["residual"]

    chi2["bad_users"] = bad_users
    return chi2


def format_bounds(elo_model, elo0, elo1):
    seps = {"BayesElo": r"[]", "logistic": r"{}", "normalized": r"<>"}
    return "%s%.2f,%.2f%s" % (seps[elo_model][0], elo0, elo1, seps[elo_model][1])


def format_results(run_results, run):
    result = {"style": "", "info": []}

    # win/loss/draw count
    WLD = [run_results["wins"], run_results["losses"], run_results["draws"]]

    if "spsa" in run["args"]:
        result["info"].append(
            "%d/%d iterations"
            % (run["args"]["spsa"]["iter"], run["args"]["spsa"]["num_iter"])
        )
        result["info"].append(
            "%d/%d games played" % (WLD[0] + WLD[1] + WLD[2], run["args"]["num_games"])
        )
        return result

    # If the score is 0% or 100% the formulas will crash
    # anyway the statistics are only asymptotic
    if WLD[0] == 0 or WLD[1] == 0:
        result["info"].append("Pending...")
        return result

    state = "unknown"
    if "sprt" in run["args"]:
        sprt = run["args"]["sprt"]
        state = sprt.get("state", "")
        elo_model = sprt.get("elo_model", "BayesElo")
        if "llr" not in sprt:  # legacy
            fishtest.stats.stat_util.update_SPRT(run_results, sprt)
        result["info"].append(
            "LLR: %.2f (%.2lf,%.2lf) %s"
            % (
                sprt["llr"],
                sprt["lower_bound"],
                sprt["upper_bound"],
                format_bounds(elo_model, sprt["elo0"], sprt["elo1"]),
            )
        )
    else:
        if "pentanomial" in run_results.keys():
            elo, elo95, los = fishtest.stats.stat_util.get_elo(
                run_results["pentanomial"]
            )
        else:
            elo, elo95, los = fishtest.stats.stat_util.get_elo([WLD[1], WLD[2], WLD[0]])

        # Display the results
        eloInfo = "ELO: %.2f +-%.1f (95%%)" % (elo, elo95)
        losInfo = "LOS: %.1f%%" % (los * 100)

        result["info"].append(eloInfo + " " + losInfo)

        if los < 0.05:
            state = "rejected"
        elif los > 0.95:
            state = "accepted"

    result["info"].append(
        "Total: %d W: %d L: %d D: %d" % (sum(WLD), WLD[0], WLD[1], WLD[2])
    )
    if "pentanomial" in run_results.keys():
        result["info"].append(
            "Ptnml(0-2): "
            + ", ".join(str(run_results["pentanomial"][i]) for i in range(0, 5))
        )

    if state == "rejected":
        if WLD[0] > WLD[1]:
            result["style"] = "yellow"
        else:
            result["style"] = "#FF6A6A"
    elif state == "accepted":
        if "sprt" in run["args"] and (float(sprt["elo0"]) + float(sprt["elo1"])) < 0.0:
            result["style"] = "#66CCFF"
        else:
            result["style"] = "#44EB44"
    return result


def estimate_game_duration(tc):
    # Total time for a game is assumed to be the double of tc for each player
    # reduced for 92% because on average a game is stopped earlier (LTC fishtest result).
    scale = 2 * 0.92
    # estimated number of moves per game (LTC fishtest result)
    game_moves = 68

    chunks = tc.split("+")
    increment = 0.0
    if len(chunks) == 2:
        increment = float(chunks[1])

    chunks = chunks[0].split("/")
    num_moves = 0
    if len(chunks) == 2:
        num_moves = int(chunks[0])

    time_tc = chunks[-1]
    chunks = time_tc.split(":")
    if len(chunks) == 2:
        time_tc = float(chunks[0]) * 60 + float(chunks[1])
    else:
        time_tc = float(chunks[0])

    if num_moves > 0:
        time_tc = time_tc * (game_moves / num_moves)

    return (time_tc + (increment * game_moves)) * scale


def remaining_hours(run):
    r = run["results"]
    if "sprt" in run["args"]:
        # current average number of games. Regularly update / have server guess?
        expected_games = 53000
        # checking randomly, half the expected games needs still to be done
        remaining_games = expected_games / 2
    else:
        expected_games = run["args"]["num_games"]
        remaining_games = max(0, expected_games - r["wins"] - r["losses"] - r["draws"])
    game_secs = estimate_game_duration(run["args"]["tc"])
    return game_secs * remaining_games * int(run["args"].get("threads", 1)) / (60 * 60)


def post_in_fishcooking_results(run):
    """Posts the results of the run to the fishcooking forum:
    https://groups.google.com/forum/?fromgroups=#!forum/fishcooking
    """
    title = run["args"]["new_tag"][:23]

    if "username" in run["args"]:
        title += "  (" + run["args"]["username"] + ")"

    body = FISH_URL + "%s\n\n" % (str(run["_id"]))

    body += run["start_time"].strftime("%d-%m-%y") + " from "
    body += run["args"].get("username", "") + "\n\n"

    body += run["args"]["new_tag"] + ": " + run["args"].get("msg_new", "") + "\n"
    body += run["args"]["base_tag"] + ": " + run["args"].get("msg_base", "") + "\n\n"

    body += (
        "TC: " + run["args"]["tc"] + " th " + str(run["args"].get("threads", 1)) + "\n"
    )
    body += "\n".join(run["results_info"]["info"]) + "\n\n"

    body += run["args"].get("info", "") + "\n\n"

    msg = MIMEText(body)
    msg["Subject"] = title
    msg["From"] = "fishtest@noreply.stockfishchess.org"
    msg["To"] = "fishcooking-results@googlegroups.com"

    try:
        s = smtplib.SMTP("localhost")
        s.sendmail(msg["From"], [msg["To"]], msg.as_string())
        s.quit()
    except ConnectionRefusedError:
        print("Unable to post results to fishcooking forum")


def diff_date(date):
    if date != datetime.min:
        diff = datetime.utcnow() - date
    else:
        diff = timedelta.max
    return diff


def delta_date(diff):
    if diff == timedelta.max:
        delta = "Never"
    elif diff.days != 0:
        delta = "%d days ago" % (diff.days)
    elif diff.seconds / 3600 > 1:
        delta = "%d hours ago" % (diff.seconds / 3600)
    elif diff.seconds / 60 > 1:
        delta = "%d minutes ago" % (diff.seconds / 60)
    else:
        delta = "seconds ago"
    return delta


def password_strength(password, *args):
    if len(password) > 0:
        # add given username and email to user_inputs
        # such that the chosen password isn't similar to either
        password_analysis = zxcvbn(password, user_inputs=[i for i in args])
        # strength scale: [0-weakest <-> 4-strongest]
        # values below 3 will give suggestions and an (optional) warning
        if password_analysis["score"] > 2:
            return True, ""
        else:
            suggestions = password_analysis["feedback"]["suggestions"][0]
            warning = password_analysis["feedback"]["warning"]
            return False, suggestions + " " + warning
    else:
        return False, "Non-empty password required"
