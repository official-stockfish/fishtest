import hashlib
import math
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import cache

import fishtest.stats.stat_util
import numpy
import scipy.stats
from email_validator import EmailNotValidError, caching_resolver, validate_email
from zxcvbn import zxcvbn

FISH_URL = "https://tests.stockfishchess.org/tests/view/"


def hex_print(s):
    return hashlib.md5(str(s).encode("utf-8")).digest().hex()


def worker_name(worker_info):
    # A user friendly name for the worker.
    username = worker_info["username"]
    cores = str(worker_info["concurrency"])
    uuid = worker_info["unique_key"]
    modified = worker_info.get("modified", False)
    name = "{}-{}cores".format(username, cores)
    if len(uuid) != 0:
        uuid_split = uuid.split("-")
        if len(uuid_split) >= 1:
            name += "-" + uuid_split[0]
        if len(uuid_split) >= 2:
            name += "-" + uuid_split[1]
    if modified:
        name += "*"
    return name


def get_chi2(tasks, exclude_workers=set()):
    """Perform chi^2 test on the stats from each worker"""

    default_results = {
        "chi2": float("nan"),
        "dof": 0,
        "p": float("nan"),
        "residual": {},
        "z_95": float("nan"),
        "z_99": float("nan"),
    }

    # Aggregate results by worker
    users = {}
    has_pentanomial = None
    for task in tasks:
        if "bad" in task:
            continue
        if "worker_info" not in task:
            continue
        key = task["worker_info"]["unique_key"]
        if key in exclude_workers:
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
        # Whenever less than two qualifying workers are left,
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
    ratio = raw_residual ** 2 / expected
    row_chi2 = numpy.sum(ratio, axis=1)
    chi2 = numpy.sum(row_chi2)
    p_value = 1 - scipy.stats.chi2.cdf(chi2, df)

    # Finally we also compute for each qualifying worker a "residual"
    # indicating how badly it deviates from the average worker.

    # The entries of adj_row_chi2 below associate with each row the
    # chi2 value of the 2xcolumns table obtained by collapsing
    # all other rows. This can be checked by a simple algebraic
    # manipulation.
    # As such, under the null hypothesis that all rows are drawn
    # from the same distribution, these "adjusted chi2 values"
    # follow a chi2 distribution with columns-1 degrees of freedom.
    adj_row_chi2 = row_chi2 / (1 - row_sums / grand_total)

    # Most people will not be familiar with the chi2 distribution,
    # so we convert the adjusted chi2 values to standard normal
    # values. As a cosmetic tweak we use isf/sf rather than ppf/cdf
    # in order to be able to deal accurately with very low p-values.
    res_z = scipy.stats.norm.isf(scipy.stats.chi2.sf(adj_row_chi2, columns - 1))

    for idx in range(len(keys)):
        # We cap the standard normal "residuals" at zero since negative values
        # do not look very nice and moreover they do not convey any
        # information.
        users[keys[idx]] = max(0, res_z[idx])

    # We compute 95% and 99% thresholds using the Bonferroni correction.
    # Under the null hypothesis, yellow and red residuals should appear
    # in approximately 4% and 1% of the tests.
    z_95, z_99 = [scipy.stats.norm.ppf(1 - p / rows) for p in (0.05, 0.01)]

    return {
        "chi2": chi2,
        "dof": df,
        "p": p_value,
        "residual": users,
        "z_95": z_95,
        "z_99": z_99,
    }


def crash_or_time(task):
    stats = task.get("stats", {})
    total = stats.get("wins", 0) + stats.get("losses", 0) + stats.get("draws", 0)
    crashes = stats.get("crashes", 0)
    time_losses = stats.get("time_losses", 0)
    return crashes > 3 or (total > 20 and time_losses / total > 0.1)


def get_bad_workers(tasks, cached_chi2=None, p=0.001, res=7.0, iters=1):
    # If we have an up-to-date result of get_chi2() we can pass
    # it as cached_chi2 to avoid needless recomputation.
    bad_workers = set()
    for _ in range(iters):
        if cached_chi2 is None:
            chi2 = get_chi2(tasks, exclude_workers=bad_workers)
        else:
            chi2 = cached_chi2
            cached_chi2 = None
        worst_user = {}
        residuals = chi2["residual"]
        for worker_key in residuals:
            if worker_key in bad_workers:
                continue
            if chi2["p"] < p or residuals[worker_key] > res:
                if worst_user == {} or residuals[worker_key] > worst_user["residual"]:
                    worst_user["unique_key"] = worker_key
                    worst_user["residual"] = residuals[worker_key]
        if worst_user == {}:
            break
        bad_workers.add(worst_user["unique_key"])

    return bad_workers


def update_residuals(tasks, cached_chi2=None):
    # If we have an up-to-date result of get_chi2() we can pass
    # it as cached_chi2 to avoid needless recomputation.
    if cached_chi2 is None:
        chi2 = get_chi2(tasks)
    else:
        chi2 = cached_chi2
    residuals = chi2["residual"]

    for task in tasks:
        if "bad" in task:
            continue
        if "worker_info" not in task:
            continue
        task["residual"] = residuals.get(
            task["worker_info"]["unique_key"], float("inf")
        )

        if crash_or_time(task):
            task["residual"] = 10.0
            task["residual_color"] = "#FF6A6A"
        elif abs(task["residual"]) < chi2["z_95"]:
            task["residual_color"] = "#44EB44"
        elif abs(task["residual"]) < chi2["z_99"]:
            task["residual_color"] = "yellow"
        else:
            task["residual_color"] = "#FF6A6A"


def format_bounds(elo_model, elo0, elo1):
    seps = {"BayesElo": r"[]", "logistic": r"{}", "normalized": r"<>"}
    return "{}{:.2f},{:.2f}{}".format(
        seps[elo_model][0], elo0, elo1, seps[elo_model][1]
    )


def format_results(run_results, run):
    result = {"style": "", "info": []}

    # win/loss/draw count
    WLD = [run_results["wins"], run_results["losses"], run_results["draws"]]

    if "spsa" in run["args"]:
        result["info"].append(
            "{:d}/{:d} iterations".format(
                run["args"]["spsa"]["iter"], run["args"]["spsa"]["num_iter"]
            )
        )
        result["info"].append(
            "{:d}/{:d} games played".format(sum(WLD), run["args"]["num_games"])
        )
        return result

    state = "unknown"
    if "sprt" in run["args"]:
        sprt = run["args"]["sprt"]
        state = sprt.get("state", "")
        elo_model = sprt.get("elo_model", "BayesElo")
        result["info"].append(
            "LLR: {:.2f} ({:.2f},{:.2f}) {}".format(
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
        eloInfo = "Elo: {:.2f} ± {:.1f} (95%)".format(elo, elo95)
        losInfo = "LOS: {:.1%}".format(los)

        result["info"].append(eloInfo + " " + losInfo)

        if los < 0.05:
            state = "rejected"
        elif los > 0.95:
            state = "accepted"

    result["info"].append(
        "Total: {:d} W: {:d} L: {:d} D: {:d}".format(sum(WLD), WLD[0], WLD[1], WLD[2])
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


@cache  # A single hash lookup should be much cheaper than parsing a string
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


def get_tc_ratio(tc, threads=1, base="10+0.1"):
    """Get TC ratio relative to the `base`, which defaults to standard STC.
    Example: standard LTC is 6x, SMP-STC is 4x."""
    return threads * estimate_game_duration(tc) / estimate_game_duration(base)


def is_active_sprt_ltc(run):
    return (
        not run["finished"]
        and "sprt" in run["args"]
        and get_tc_ratio(run["args"]["tc"], run["args"]["threads"]) > 4
    )  # SMP-STC ratio is 4


def remaining_hours(run):
    r = run["results"]
    if "sprt" in run["args"]:
        # Current average number of games. The number should be regularly updated.
        average_total_games = 95000

        # SPRT tests always have pentanomial stats.
        p = r["pentanomial"]
        N = sum(p)

        sprt = run["args"]["sprt"]
        llr, alpha, beta = sprt["llr"], sprt["alpha"], sprt["beta"]
        o0, o1 = 0, 0
        if "overshoot" in sprt:
            o = sprt["overshoot"]
            o0 = -o["sq0"] / o["m0"] / 2 if o["m0"] != 0 else 0
            o1 = o["sq1"] / o["m1"] / 2 if o["m1"] != 0 else 0
        llr_bound = (
            math.log((1 - beta) / alpha) - o1
            if llr > 0.0
            else math.log(beta / (1 - alpha)) + o0
        )

        # Use 0.1 as a safeguard if LLR is too small.
        llr, llr_bound = max(0.1, abs(llr)), abs(llr_bound)
        if llr >= llr_bound:
            return 0

        # Assume all tests use default book (UHO_XXL_+0.90_+1.19).
        book_positions = 223070
        t = scipy.stats.beta(1, 15).cdf(min(N / book_positions, 1.0))
        expected_games_llr = int(2 * N * llr_bound / llr)
        expected_games = min(
            run["args"]["num_games"],
            int(expected_games_llr * t + average_total_games * (1 - t)),
        )
        remaining_games = max(0, expected_games - 2 * N)
    else:
        expected_games = run["args"]["num_games"]
        remaining_games = max(0, expected_games - r["wins"] - r["losses"] - r["draws"])
    game_secs = estimate_game_duration(run["args"]["tc"])
    return game_secs * remaining_games * int(run["args"].get("threads", 1)) / (60 * 60)


def post_in_fishcooking_results(run):
    """Posts the results of the run to the fishcooking forum:
    https://groups.google.com/g/fishcooking-results
    """
    title = run["args"]["new_tag"][:23]

    if "username" in run["args"]:
        title += "  (" + run["args"]["username"] + ")"

    body = FISH_URL + "{}\n\n".format(str(run["_id"]))

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


def plural(n, s):
    return s + (n != 1) * "s"


def delta_date(diff):
    if diff == timedelta.max:
        return "Never"
    tv = diff.days, diff.seconds // 3600, diff.seconds // 60
    td = "day", "hour", "minute"
    for v, d in zip(tv, td):
        if v >= 1:
            return "{:d} {} ago".format(v, plural(v, d))
    return "seconds ago"


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


class optional_key:
    def __init__(self, key):
        self.key = key


class union:
    def __init__(self, *schemas):
        self.schemas = schemas

    def __validate__(self, object, name, strict=False):
        messages = []
        for schema in self.schemas:
            message = validate(schema, object, name, strict=strict)
            if message == "":
                return ""
            else:
                messages.append(message)
        return " and ".join(messages)


def validate(schema, object, name, strict=False):
    if isinstance(schema, type):
        if not isinstance(object, schema):
            return "{} is not of type {}".format(name, schema.__name__)
        else:
            return ""
    elif isinstance(schema, list) or isinstance(schema, tuple):
        if type(schema) != type(object):
            return "{} is not of type {}".format(name, type(schema).__name__)
        l = len(object)
        if strict and l != len(schema):
            return "{} does not have length {}".format(name, len(schema))
        for i in range(len(schema)):
            name_ = "{}[{}]".format(name, i)
            if i >= l:
                return "{} does not exist".format(name_)
            else:
                ret = validate(schema[i], object[i], name_, strict=strict)
                if ret != "":
                    return ret
        return ""
    elif isinstance(schema, dict):
        if type(schema) != type(object):
            return "{} is not of type {}".format(name, type(schema).__name__)
        if strict and len(object) != len(schema):
            return "the number of keys in {} is not equal to {}".format(
                name, len(schema)
            )
        for k in schema:
            k_ = k
            if isinstance(k, optional_key):
                k_ = k.key
                if k_ not in object:
                    continue
            name_ = "{}['{}']".format(name, k_)
            if k_ not in object:
                return "{} is missing".format(name_)
            else:
                ret = validate(schema[k], object[k_], name_, strict=strict)
                if ret != "":
                    return ret
        return ""
    elif hasattr(schema, "__validate__"):  # duck typing
        return schema.__validate__(object, name, strict=strict)
    elif object != schema:
        return "{} is not equal to {}".format(name, repr(schema))
    return ""


# Workaround for a bug in pyramid.request.cookies.
# Chrome may send different cookies with the same name.
# The one that applies is the first one (the one with the
# most specific path).
# But pyramid.request.cookies picks the last one.
def get_cookie(request, name):
    name = name.strip()
    if "Cookie" not in request.headers:
        return None
    cookies = request.headers["Cookie"].split(";")
    for cookie in cookies:
        try:
            k, v = cookie.split("=", 1)
        except ValueError:
            continue
        if k.strip() == name:
            return v.strip()


def email_valid(email):
    try:
        resolver = caching_resolver(timeout=10)
        valid = validate_email(email, dns_resolver=resolver)
        return True, valid.email
    except EmailNotValidError as e:
        return False, str(e)


def get_hash(s):
    h = re.search("Hash=([0-9]+)", s)
    if h:
        return int(h.group(1))
    return 0
