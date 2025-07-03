import base64
from pathlib import Path
from urllib.parse import urlparse

import requests
from fishtest.lru_cache import LRUCache
from fishtest.schemas import sha as sha_schema
from vtjson import validate

"""
We treat this module as a singleton.
"""
"""
Note: we generally don't suppress exceptions since too many things can
go wrong. The caller should gracefully handle whatever comes their
way.
"""
GITHUB_API_VERSION = 1
TIMEOUT = 3
INITIAL_RATELIMIT = 5000
LRU_CACHE_SIZE = 6000

_github_rate_limit = None
_lru_cache = None
_kvstore = None

# This one is set externally
_official_master_sha = None


def init(kvstore):
    global _github_rate_limit, _kvstore, _lru_cache
    _kvstore = kvstore
    _lru_cache = LRUCache(LRU_CACHE_SIZE)
    github_api_cache = {"version": GITHUB_API_VERSION, "lru_cache": []}
    try:
        if "github_api_cache" in _kvstore:
            github_api_cache = _kvstore["github_api_cache"]
        else:
            print("Initializing github_api_cache", flush=True)
        if github_api_cache["version"] != GITHUB_API_VERSION:
            raise Exception("Stored github_api_cache has different version")
        for k, v in github_api_cache["lru_cache"]:
            _lru_cache[tuple(k)] = v
    except Exception as e:
        print(f"Unable to restore github_api_cache from kvstore: {str(e)}", flush=True)
    try:
        _github_rate_limit = rate_limit()["remaining"]
    except Exception as e:
        print(
            f"Unable to initialize github rate limit :{str(e)}. Assuming {INITIAL_RATELIMIT}."
        )


def save():
    global _kvstore
    _kvstore["github_api_cache"] = {
        "version": GITHUB_API_VERSION,
        "lru_cache": [(k, v) for k, v in _lru_cache.items()],
    }


def call(url, *args, _method="GET", _ignore_rate_limit=False, **kwargs):
    global _github_rate_limit
    if not _ignore_rate_limit and _github_rate_limit < INITIAL_RATELIMIT / 2:
        raise Exception(r"Rate limit more than 50% consumed.")

    r = requests.request(_method, url, *args, **kwargs)
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
    r = call(item_url, timeout=TIMEOUT, _ignore_rate_limit=True)
    r.raise_for_status()
    return r.content


def _download_from_github_api(
    item,
    user="official-stockfish",
    repo="Stockfish",
    branch="master",
    ignore_rate_limit=False,
):
    item_url = (
        f"https://api.github.com/repos/{user}/{repo}/contents/{item}?ref={branch}"
    )
    r = call(item_url, timeout=TIMEOUT, _ignore_rate_limit=ignore_rate_limit)
    r.raise_for_status()
    git_url = r.json()["git_url"]
    r = call(git_url, timeout=TIMEOUT, _ignore_rate_limit=True)
    r.raise_for_status()
    return base64.b64decode(r.json()["content"])


def download_from_github(
    item,
    user="official-stockfish",
    repo="Stockfish",
    branch="master",
    method="api",
    ignore_rate_limit=False,
):
    if method == "api":
        return _download_from_github_api(
            item,
            user=user,
            repo=repo,
            branch=branch,
            ignore_rate_limit=ignore_rate_limit,
        )
    elif method == "raw":
        return _download_from_github_raw(item, user=user, repo=repo, branch=branch)
    else:
        raise ValueError(f"Unknown method {method}")


def get_commit(
    user="official-stockfish",
    repo="Stockfish",
    branch="master",
    ignore_rate_limit=False,
):
    url = f"https://api.github.com/repos/{user}/{repo}/commits/{branch}"
    r = call(url, timeout=TIMEOUT, _ignore_rate_limit=ignore_rate_limit)
    r.raise_for_status()
    commit = r.json()
    return commit


def get_commits(user="official-stockfish", repo="Stockfish", ignore_rate_limit=False):
    url = f"https://api.github.com/repos/{user}/{repo}/commits"
    r = call(url, timeout=TIMEOUT, _ignore_rate_limit=ignore_rate_limit)
    r.raise_for_status()
    commit = r.json()
    return commit


def rate_limit():
    url = "https://api.github.com/rate_limit"
    r = call(url, timeout=TIMEOUT, _ignore_rate_limit=True)
    r.raise_for_status()
    rate_limit = r.json()["resources"]["core"]
    return rate_limit


def compare_sha(
    user1="official-stockfish",
    sha1=None,
    user2=None,
    sha2=None,
    ignore_rate_limit=False,
):
    global _lru_cache
    # Non sha arguments cannot be safely cached
    validate(sha_schema, sha1)
    validate(sha_schema, sha2)

    if user2 is None:
        user2 = user1

    # it's not necessary to include user1, user2 as shas
    # are globally unique
    inputs = ("compare_sha", sha1, sha2)
    if inputs in _lru_cache:
        return _lru_cache[inputs]
    url = (
        "https://api.github.com/repos/official-stockfish/"
        f"Stockfish/compare/{user1}:{sha1}...{user2}:{sha2}"
    )
    r = call(
        url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=TIMEOUT,
        _ignore_rate_limit=ignore_rate_limit,
    )
    r.raise_for_status()
    json = r.json()
    json1 = {}
    json1["merge_base_commit"] = {}
    json1["merge_base_commit"]["sha"] = json["merge_base_commit"]["sha"]
    _lru_cache[inputs] = json1
    return json1


def parse_repo(repo_url):
    p = Path(urlparse(repo_url).path).parts
    return (p[1], p[2])


def get_merge_base_commit(
    user1="official-stockfish",
    sha1=None,
    user2=None,
    sha2=None,
    ignore_rate_limit=False,
):
    if user2 is None:
        user2 = user1
    master_diff = compare_sha(
        user1=user1,
        sha1=sha1,
        user2=user2,
        sha2=sha2,
        ignore_rate_limit=ignore_rate_limit,
    )
    return master_diff["merge_base_commit"]["sha"]


def is_ancestor(
    user1="official-stockfish",
    sha1=None,
    user2=None,
    sha2=None,
    ignore_rate_limit=False,
):
    if user2 is None:
        user2 = user1
    merge_base_commit = get_merge_base_commit(
        user1=user1,
        sha1=sha1,
        user2=user2,
        sha2=sha2,
        ignore_rate_limit=ignore_rate_limit,
    )
    return merge_base_commit == sha1


def _is_master(sha, official_master_sha, ignore_rate_limit=False):
    global _lru_cache
    inputs = ("_is_master", sha, official_master_sha)
    if inputs in _lru_cache:
        return _lru_cache[inputs]
    try:
        ret = is_ancestor(
            sha1=sha, sha2=official_master_sha, ignore_rate_limit=ignore_rate_limit
        )
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            ret = False
            # Positive answers are already cached in compare_sha
            _lru_cache[inputs] = ret
    return ret


def is_master(sha, ignore_rate_limit=False):
    return _is_master(sha, _official_master_sha, ignore_rate_limit=ignore_rate_limit)


def get_master_repo(
    user="official-stockfish", repo="Stockfish", ignore_rate_limit=False
):
    api_url = f"https://api.github.com/repos/{user}/{repo}"
    r = call(api_url, timeout=TIMEOUT, _ignore_rate_limit=ignore_rate_limit)
    r.raise_for_status()
    r = r.json()
    while True:
        if not r["fork"]:
            return r["html_url"]
        else:
            r = r["parent"]


def normalize_repo(repo):
    r = call(repo, _method="HEAD", allow_redirects=True, _ignore_rate_limit=True)
    r.raise_for_status()
    return r.url


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
