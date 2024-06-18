from fishtest.util import get_hash, get_tc_ratio


def tests_repo(run):
    return run["args"].get(
        "tests_repo", "https://github.com/official-monty/Monty"
    )


def master_diff_url(run):
    return "{}/compare/master...{}".format(
        tests_repo(run), run["args"]["resolved_base"][:10]
    )


def diff_url(run):
    if run["args"].get("spsa"):
        return master_diff_url(run)
    else:
        return "{}/compare/{}...{}".format(
            tests_repo(run),
            run["args"]["resolved_base"][:10],
            run["args"]["resolved_new"][:10],
        )


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
