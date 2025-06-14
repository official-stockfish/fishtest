from fishtest.github_api import compare_branches_url, parse_repo
from fishtest.util import get_hash, get_tc_ratio


def tests_repo(run):
    tests_repo = run["args"]["tests_repo"]
    if tests_repo != "":
        return tests_repo
    else:
        # very old tests didn't have a separate
        # tests repo
        return "https://github.com/official-stockfish/Stockfish"


def diff_url(run):
    tests_repo_ = tests_repo(run)
    user2, repo = parse_repo(tests_repo_)
    sha2 = run["args"]["resolved_new"]
    if "spsa" in run["args"]:
        user1 = "offficial-stockfish"
        sha1 = run["args"].get("official_master_sha", "master")
    else:
        user1 = user2
        sha1 = run["args"]["resolved_base"]
    return compare_branches_url(user1=user1, branch1=sha1, user2=user2, branch2=sha2)


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
