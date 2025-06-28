import base64
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import requests
from fishtest.schemas import sha as sha_schema
from vtjson import validate

TIMEOUT = 3

_official_master_sha = None
_github_rate_limit = -1


def call(url, *args, **kwargs):
    global _github_rate_limit
    r = requests.get(url, *args, **kwargs)
    resource = r.headers.get("X-RateLimit-Resource", "")
    if resource == "core":
        _github_rate_limit = int(
            r.headers.get("X-RateLimit-Remaining", _github_rate_limit)
        )
    return r


def _download_from_github_raw(
    item, user="official-stockfish", repo="Stockfish", branch="master"
):
    item_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{item}"
    r = call(item_url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def _download_from_github_api(
    item, user="official-stockfish", repo="Stockfish", branch="master"
):
    item_url = (
        f"https://api.github.com/repos/{user}/{repo}/contents/{item}?ref={branch}"
    )
    r = call(item_url, timeout=TIMEOUT)
    r.raise_for_status()
    git_url = r.json()["git_url"]
    r = call(git_url, timeout=TIMEOUT)
    r.raise_for_status()
    return base64.b64decode(r.json()["content"])


def download_from_github(
    item, user="official-stockfish", repo="Stockfish", branch="master", method="api"
):
    if method == "api":
        return _download_from_github_api(item, user=user, repo=repo, branch=branch)
    elif method == "raw":
        return _download_from_github_raw(item, user=user, repo=repo, branch=branch)
    else:
        raise ValueError(f"Unknown method {method}")


def get_commit(user="official-stockfish", repo="Stockfish", branch="master"):
    url = f"https://api.github.com/repos/{user}/{repo}/commits/{branch}"
    r = call(url, timeout=TIMEOUT)
    r.raise_for_status()
    commit = r.json()
    return commit


def get_commits(user="official-stockfish", repo="Stockfish"):
    url = f"https://api.github.com/repos/{user}/{repo}/commits"
    r = call(url, timeout=TIMEOUT)
    r.raise_for_status()
    commit = r.json()
    return commit


def rate_limit():
    url = "https://api.github.com/rate_limit"
    r = call(url, timeout=TIMEOUT)
    r.raise_for_status()
    rate_limit = r.json()["resources"]["core"]
    return rate_limit


@lru_cache(maxsize=1000)
def compare_sha(user1="official-stockfish", sha1=None, user2=None, sha2=None):
    # Non sha arguments cannot be safely cached
    validate(sha_schema, sha1)
    validate(sha_schema, sha2)

    # Protect against DOS'ing
    if _github_rate_limit < 2500:
        raise Exception(r"Rate limit more than 50% consumed.")

    if user2 is None:
        user2 = user1
    url = (
        "https://api.github.com/repos/official-stockfish/"
        f"Stockfish/compare/{user1}:{sha1}...{user2}:{sha2}"
    )
    r = call(url, headers={"Accept": "application/vnd.github+json"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def parse_repo(repo_url):
    p = Path(urlparse(repo_url).path).parts
    return (p[1], p[2])


def get_merge_base_commit(user1="official-stockfish", sha1=None, user2=None, sha2=None):
    if user2 is None:
        user2 = user1
    master_diff = compare_sha(user1=user1, sha1=sha1, user2=user2, sha2=sha2)
    return master_diff["merge_base_commit"]["sha"]


def is_ancestor(user1="official-stockfish", sha1=None, user2=None, sha2=None):
    if user2 is None:
        user2 = user1
    merge_base_commit = get_merge_base_commit(
        user1=user1, sha1=sha1, user2=user2, sha2=sha2
    )
    return merge_base_commit == sha1


@lru_cache(maxsize=1000)
def _is_master(sha, official_master_sha):
    try:
        return is_ancestor(sha1=sha, sha2=official_master_sha)
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return False


def is_master(sha):
    try:
        return _is_master(sha, _official_master_sha)
    except Exception as e:
        print(f"Unable to evaluate is_master({sha}): {str(e)}", flush=True)
        return False


def get_master_repo(user="official-stockfish", repo="Stockfish"):
    api_url = f"https://api.github.com/repos/{user}/{repo}"
    r = call(api_url, timeout=TIMEOUT)
    r.raise_for_status()
    r = r.json()
    while True:
        if "fork" not in r:
            return None
        if not r["fork"]:
            return r.get("html_url", None)
        else:
            if "parent" not in r:
                return None
            r = r["parent"]


def compare_branches_url(
    user1="stockfish-chess", branch1="master", user2=None, branch2=None
):
    if user2 is None:
        user2 = user1
    return (
        "https://github.com/official-stockfish/Stockfish/"
        f"compare/{user1}:{branch1}...{user2}:{branch2}"
    )


def commit_url(user="official-stockfish", repo="Stockfish", branch="master"):
    return f"https://github.com/{user}/{repo}/commit/{branch}"
