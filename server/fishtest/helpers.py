def tests_repo(run):
    return run["args"].get(
        "tests_repo", "https://github.com/official-stockfish/Stockfish"
    )


def tests_repo_api(run):
    """Return URL for GitHub API of the repository"""
    return run["args"].get(
        "tests_repo", "https://github.com/official-stockfish/Stockfish"
        ).replace(
            "//github.com/", "//api.github.com/repos/", 1)


def master_diff_url(run):
    return "https://github.com/official-stockfish/Stockfish/compare/master...{}".format(
        run["args"]["resolved_base"][:10]
    )


def diff_url(run, *, api_url=False):
    """Produces GitHub diff URL

    Uses the two-dotted format for non-API, the three-dotted format for API."""
    if run["args"].get("spsa"):
        return master_diff_url(run)
    else:
        return "{}/compare/{}{}{}".format(
            tests_repo(run) if not api_url else tests_repo_api(run),
            run["args"]["resolved_base"][:10],
            ".." if not api_url else "...",
            run["args"]["resolved_new"][:10],
        )
