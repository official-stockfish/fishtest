import copy
import hashlib
import math
import re
from datetime import UTC, datetime
from functools import cache

import numpy as np
import scipy.stats
from email_validator import EmailNotValidError, caching_resolver, validate_email
from zxcvbn import zxcvbn

import fishtest.github_api as gh
import fishtest.stats.stat_util

FISHTEST = "fishtest_new"
PASSWORD_MAX_LENGTH = 72
VALID_USERNAME_PATTERN = "[A-Za-z0-9]{2,}"


class GeneratorAsFileReader:
    def __init__(self, generator):
        self.generator = generator
        self.buffer = b""

    def read(self, size=-1):
        while size < 0 or len(self.buffer) < size:
            try:
                self.buffer += next(self.generator)
            except StopIteration:
                break
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def close(self):
        pass  # No cleanup needed, but method is required


def hex_print(run_id):
    return hashlib.md5(str(run_id).encode("utf-8")).digest().hex()


def worker_name(worker_info, short=False):
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
        if len(uuid_split) >= 2 and not short:
            name += "-" + uuid_split[1]
    if modified and not short:
        name += "*"
    return name


def get_chi2(tasks, exclude_workers=set()):
    """Perform chi^2 test on the stats from each worker."""

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
            # So we combine the ww and ll frequencies with the wd and ld frequencies,
            # this is equivalent to use the frequencies for the pair of games.
            wld = [float(p[4] + p[3]), float(p[0] + p[1]), float(p[2])]

        users[key] = [
            user_val + wld_val
            for user_val, wld_val in zip(users.get(key, [0] * len(wld)), wld)
        ]
    # We filter out the workers whose expected frequences are <= 5 as
    # they break the chi2 test.
    filtering_done = False
    while not filtering_done:
        # Whenever less than two qualifying workers are left,
        # we bail out and just return "something".
        if len(users) <= 1:
            return default_results
        # Now do the matrix computations with numpy.
        observed = np.array(list(users.values()))
        rows, columns = observed.shape
        column_sums = np.sum(observed, axis=0)
        row_sums = np.sum(observed, axis=1)
        grand_total = np.sum(column_sums)
        # if no games have been received, we cannot continue
        if grand_total == 0:
            return default_results
        expected = np.outer(row_sums, column_sums) / grand_total
        filtering_done = True
        for key, expected_row in zip(list(users), expected):
            if min(expected_row) <= 5:
                del users[key]
                filtering_done = False

    # Now we do the basic chi2 computation.
    df = (rows - 1) * (columns - 1)
    raw_residual = observed - expected
    ratio = raw_residual**2 / expected
    row_chi2 = np.sum(ratio, axis=1)
    chi2 = np.sum(row_chi2)
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

    for idx, key in enumerate(users):
        # We cap the standard normal "residuals" at zero since negative values
        # do not look very nice and moreover they do not convey any
        # information.
        users[key] = max(0, res_z[idx])

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
    for i in range(iters):
        chi2 = (
            get_chi2(tasks, exclude_workers=bad_workers)
            if i > 0 or cached_chi2 is None
            else cached_chi2
        )
        worst_user = {}
        residuals = chi2["residual"]
        for worker_key in residuals:
            if worker_key in bad_workers:
                continue
            if chi2["p"] < p or residuals[worker_key] > res:
                if not worst_user or residuals[worker_key] > worst_user["residual"]:
                    worst_user["unique_key"] = worker_key
                    worst_user["residual"] = residuals[worker_key]
        if not worst_user:
            break
        bad_workers.add(worst_user["unique_key"])

    return bad_workers


def residual_to_color(residual, chi2):
    if abs(residual) < chi2["z_95"]:
        return "green"
    elif abs(residual) < chi2["z_99"]:
        return "yellow"
    else:
        return "red"


def display_residual(task, chi2):
    if "bad" in task and "residual" in task:
        residual = task["residual"]
        residual_color = task["residual_color"]
    else:
        if crash_or_time(task):
            residual = 10.0
            residual_color = "red"
        else:
            residual = chi2["residual"].get(
                task["worker_info"]["unique_key"], float("inf")
            )
            residual_color = residual_to_color(residual, chi2)

    display_colors = {
        "green": "#44EB44",
        "yellow": "yellow",
        "red": "#FF6A6A",
        "#44EB44": "#44EB44",  # legacy bad tasks
        "#FF6A6A": "#FF6A6A",
    }

    display_color = display_colors[residual_color]

    return {
        "residual": residual,
        "residual_color": residual_color,
        "display_color": display_color,
    }


def format_bounds(elo_model, elo0, elo1):
    seps = {"BayesElo": r"[]", "logistic": r"{}", "normalized": r"<>"}
    return "{}{:.2f},{:.2f}{}".format(
        seps[elo_model][0], elo0, elo1, seps[elo_model][1]
    )


def format_results(run):
    run_results = run["results"]

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


def is_sprt_ltc_data(args):
    return (
        "sprt" in args and get_tc_ratio(args["tc"], args["threads"]) > 4
    )  # SMP-STC ratio is 4


def is_active_sprt_ltc(run):
    return not run["finished"] and is_sprt_ltc_data(run["args"])


def format_date(date):
    if not date or date == "Unknown":
        return "Unknown"

    # Define month names
    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    # Extract date components
    year = date.year
    month = month_names[date.month - 1]
    day = date.day
    hours = date.hour
    minutes = date.minute

    # Determine AM/PM
    ampm = "AM" if hours < 12 else "PM"
    hours = hours % 12 or 12  # Convert 0 to 12 for 12-hour format

    # Format minutes to always have two digits
    formatted_minutes = f"{minutes:02}"

    # Construct the formatted date string
    formatted_date = (
        f"{month} {day}, {year}, at {hours}:{formatted_minutes} {ampm} (UTC)"
    )

    return formatted_date


def remaining_hours(run):
    if "sprt" in run["args"]:
        # Current average number of games. The number should be regularly updated.
        average_total_games = 95000

        # SPRT tests always have pentanomial stats.
        played_pairs = sum(run["results"]["pentanomial"])
        played_games = played_pairs * 2

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

        # Assume all tests use default book (UHO_Lichess_4852_v1).
        book_positions = 2632036
        t = scipy.stats.beta(1, 15).cdf(min(played_pairs / book_positions, 1.0))
        expected_games_llr = int(played_games * llr_bound / llr)
        expected_games = min(
            run["args"]["num_games"],
            int(expected_games_llr * t + average_total_games * (1 - t)),
        )
        remaining_games = max(0, expected_games - played_games)
    else:
        played_games = sum(run["results"][key] for key in ("wins", "losses", "draws"))
        expected_games = run["args"]["num_games"]
        remaining_games = max(0, expected_games - played_games)
    game_secs = estimate_game_duration(run["args"]["tc"])
    return game_secs * remaining_games * int(run["args"].get("threads", 1)) / (60 * 60)


def plural(quantity, word):
    return word if quantity == 1 else word + "s"


def format_time_ago(date):
    if date == datetime.min.replace(tzinfo=UTC):
        return "Never"
    elapsed_time = datetime.now(UTC) - date
    time_values = (
        elapsed_time.days,
        elapsed_time.seconds // 3600,
        elapsed_time.seconds // 60,
    )
    time_units = "day", "hour", "minute"
    for value, unit in zip(time_values, time_units):
        if value >= 1:
            unit_label = plural(value, unit)
            return f"{value:d} {unit_label} ago"
    return "seconds ago"


def format_group(groups):
    return (
        ", ".join([group.replace("group:", "") for group in groups])
        if groups and len(groups) > 0
        else "No group"
    )


def password_strength(password, *args):
    # Maximum length enforced by zxcvbn.
    if len(password) < 1:
        return False, "Error! Non-empty password required"
    if len(password) > PASSWORD_MAX_LENGTH:
        return False, (
            f"Error! Password too long (max {PASSWORD_MAX_LENGTH} characters)"
        )

    # Add given username and email to user_inputs
    # such that the chosen password isn't similar to either
    password_analysis = zxcvbn(password, user_inputs=[i for i in args])
    # Strength scale: [0-weakest <-> 4-strongest]
    # values below 3 will give suggestions and an (optional) warning
    if password_analysis["score"] > 2:
        return True, ""
    else:
        feedback = password_analysis.get("feedback") or {}
        suggestions_list = feedback.get("suggestions") or []
        suggestions = suggestions_list[0] if suggestions_list else ""
        warning = feedback.get("warning") or ""
        details = " ".join(part for part in (suggestions, warning) if part)
        if details:
            return False, "Error! Weak password: " + details
        return False, "Error! Weak password"


def email_valid(email):
    try:
        resolver = caching_resolver(timeout=10)
        valid = validate_email(email, dns_resolver=resolver)
        return True, valid.email
    except EmailNotValidError as e:
        return False, str(e)


def get_hash(engine_options):
    match = re.search("Hash=([0-9]+)", engine_options)
    return int(match.group(1)) if match else 0


def strip_run(run):
    """Expose only non-sensitive workers data and skip deepcopying some heavy data."""

    stripped = {}
    for k1, v1 in run.items():
        if k1 in ("tasks", "bad_tasks"):
            stripped[k1] = []
        elif k1 == "args":
            stripped[k1] = {}
            for k2, v2 in v1.items():
                if k2 == "spsa":
                    stripped[k1][k2] = {
                        k3: [] if k3 == "param_history" else copy.deepcopy(v3)
                        for k3, v3 in v2.items()
                    }
                else:
                    stripped[k1][k2] = copy.deepcopy(v2)
        else:
            stripped[k1] = copy.deepcopy(v1)

    # and some string conversions
    for key in ("_id", "start_time", "last_updated"):
        stripped[key] = str(run[key])

    return stripped


def count_games(stats):
    return stats["wins"] + stats["losses"] + stats["draws"]


def tests_repo(run):
    tests_repo = run["args"]["tests_repo"]
    if tests_repo != "":
        return tests_repo
    else:
        # very old tests didn't have a separate
        # tests repo
        return "https://github.com/official-stockfish/Stockfish"


def diff_url(run, master_check=True):
    tests_repo_ = tests_repo(run)
    user2, repo = gh.parse_repo(tests_repo_)
    sha2 = run["args"]["resolved_new"]
    if "spsa" in run["args"]:
        user1 = "official-stockfish"
        sha1 = gh.official_master_sha
    else:
        user1 = user2
        sha1 = run["args"]["resolved_base"]
    if master_check:
        im1 = im2 = False
        try:
            im1 = gh.is_master(sha1)
            im2 = gh.is_master(sha2)
        except Exception as e:
            print(
                f"Unable to evaluate is_master({sha1}) or is_master({sha2}): {str(e)}"
            )
        else:
            if im1:
                user1 = "official-stockfish"
            if im2:
                user2 = "official-stockfish"
    return gh.compare_branches_url(user1=user1, branch1=sha1, user2=user2, branch2=sha2)


def ok_hash(tc_ratio, hash):
    # for historical reasons hash doesn't scale linearly between tc ratios 1-6, so only check 5+.
    if tc_ratio < 5:
        return (
            True  # MTC and STC are assumed fine, could be handled if we really want to
        )
    # tc_ratio 6 has has 64 MB, and linearly for all above
    target_hash = 64 * tc_ratio / 6
    return 0.6 <= hash / target_hash <= 1.5


def reasonable_run_hashes(run):
    # if this func returns false, then emit warning to user to verify hashes
    base_hash = get_hash(run["args"]["base_options"])
    new_hash = get_hash(run["args"]["new_options"])
    tc_ratio = get_tc_ratio(run["args"]["tc"], run["args"]["threads"])
    return ok_hash(tc_ratio, base_hash) and ok_hash(tc_ratio, new_hash)


supported_compilers = ["clang++", "g++"]


# List of architectures extracted from the output of "make help"
# in the src directory of the Stockfish source code.
# The worker compiles with "make ARCH=native", which uses
# the output of Stockfish script "get_native_properties.sh".
# Architectures not covered by the script must be listed as commented out.

supported_arches = [
    "apple-silicon",
    "armv7",
    "armv7-neon",
    "armv8",
    "armv8-dotprod",
    "e2k",
    "general-32",
    "general-64",
    "loongarch64",
    "loongarch64-lasx",
    "loongarch64-lsx",
    "ppc-32",
    "ppc-64",
    "ppc-64-altivec",
    "ppc-64-vsx",
    "riscv64",
    "x86-32",
    "x86-32-sse2",
    "x86-32-sse41-popcnt",
    "x86-64",
    "x86-64-avx2",
    "x86-64-avx512",
    "x86-64-avxvnni",
    "x86-64-bmi2",
    "x86-64-sse3-popcnt",
    "x86-64-sse41-popcnt",
    "x86-64-ssse3",
    "x86-64-vnni512",
    "x86-64-avx512icl",
]
