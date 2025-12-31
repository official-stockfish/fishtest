import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from fishtest.lru_cache import LRUCache
from fishtest.schemas import sha as sha_schema
from fishtest.schemas import str_int, uint
from vtjson import ValidationError, union, validate
from vtjson import url as url_schema

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

_api_initialized = False

_github_rate_limit = {
    "limit": INITIAL_RATELIMIT,
    "remaining": INITIAL_RATELIMIT,
    "reset": int(time.time()),
    "used": 0,
    "resource": "core",
    "_uninitialized": True,
}
_lru_cache = None
_kvstore = None

_dummy_sha = 40 * "f"
official_master_sha = _dummy_sha


def init(kvstore, actiondb):
    global _actiondb, _github_rate_limit, _kvstore, _lru_cache, _api_initialized
    _kvstore = kvstore
    _actiondb = actiondb
    _lru_cache = LRUCache(LRU_CACHE_SIZE)
    try:
        if "github_api_cache" in _kvstore:
            github_api_cache = _kvstore["github_api_cache"]
        else:
            raise Exception("No previously saved github_api_cache")
        if github_api_cache["version"] != GITHUB_API_VERSION:
            raise Exception("Stored github_api_cache has different version")
        for k, v in github_api_cache["lru_cache"]:
            _lru_cache[tuple(k)] = v
    except Exception as e:
        print(f"Unable to restore github_api_cache from kvstore: {str(e)}", flush=True)

    _api_initialized = True
    update_official_master_sha()


def clear_api_cache():
    global _lru_cache
    _lru_cache = LRUCache(LRU_CACHE_SIZE)


def save():
    global _kvstore
    _kvstore["github_api_cache"] = {
        "version": GITHUB_API_VERSION,
        "lru_cache": [(k, v) for k, v in _lru_cache.items()],
    }


def call(url, *args, _method="GET", _ignore_rate_limit=False, **kwargs):
    global _github_rate_limit
    if not _api_initialized:
        raise Exception("github_api.py was not properly initialized")
    if (
        not _ignore_rate_limit
        and time.time() <= _github_rate_limit["reset"]
        and _github_rate_limit["remaining"] < _github_rate_limit["used"]
    ):
        raise Exception(r"Rate limit more than 50% consumed.")

    headers = kwargs.pop("headers", {})
    if "GH_TOKEN" in os.environ:
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]

    r = requests.request(_method, url, *args, headers=headers, **kwargs)
    resource = r.headers.get("X-RateLimit-Resource", "")
    if resource == "core":
        _github_rate_limit["remaining"] = int(
            r.headers.get("X-RateLimit-Remaining", _github_rate_limit["remaining"])
        )
        _github_rate_limit["used"] = int(
            r.headers.get("X-RateLimit-Used", _github_rate_limit["used"])
        )
        _github_rate_limit["reset"] = int(
            r.headers.get("X-RateLimit-Reset", _github_rate_limit["reset"])
        )
        _github_rate_limit["limit"] = int(
            r.headers.get("X-RateLimit-Limit", _github_rate_limit["limit"])
        )
        _github_rate_limit.pop("_uninitialized", None)
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
    r = call(
        item_url,
        headers={"Accept": "application/vnd.github.raw+json"},
        timeout=TIMEOUT,
        _ignore_rate_limit=ignore_rate_limit,
    )
    r.raise_for_status()
    return r.content


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


def _update_rate_limit():
    if (
        "_uninitialized" not in _github_rate_limit
        and _github_rate_limit["remaining"] == _github_rate_limit["limit"]
    ):
        _github_rate_limit["reset"] = time.time() + 3600
    elif (
        "_uninitialized" in _github_rate_limit
        or time.time() > _github_rate_limit["reset"]
    ):
        url = "https://api.github.com/rate_limit"
        try:
            # sets _github_rate_limit
            call(url, timeout=TIMEOUT, _ignore_rate_limit=True)
        except Exception as e:
            print(f"Unable to get rate limit: {str(e)}", flush=True)


def rate_limit():
    _update_rate_limit()
    return _github_rate_limit


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

    github_error = {"message": str, "documentation_url": url_schema, "status": str_int}
    cache_schema = union(
        {"merge_base_commit": {"sha": sha_schema}},
        {
            "__error__": True,
            "http_error": str,
            "status": uint,
            "url": url_schema,
            "github_error": github_error,
            "timestamp": float,
        },
    )

    if user2 is None:
        user2 = user1

    # it's not necessary to include user1, user2 as shas
    # are globally unique
    inputs = ("compare_sha", sha1, sha2)
    previous_value = None
    if inputs in _lru_cache:
        previous_value = _lru_cache[inputs]
        if "__error__" not in previous_value:
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
    saved_http_exception = None
    try:
        r.raise_for_status()
        json = {"merge_base_commit": {"sha": r.json()["merge_base_commit"]["sha"]}}
        if previous_value is not None:
            message = (
                f"The previous attempt with url {previous_value['url']} failed with "
                f"HTTP error {previous_value['http_error']} and GitHub error "
                f"{previous_value['github_error']} but now {url} succeeded"
            )
            print(message, flush=True)
            _actiondb.log_message(
                username="fishtest.system",
                message=message,
            )
    except requests.HTTPError as e:
        json = {
            "__error__": True,
            "http_error": str(e),
            "url": url,
            "status": e.response.status_code,
            "github_error": r.json(),
            "timestamp": time.time(),
        }
        saved_http_exception = e
    try:
        validate(cache_schema, json)
    except ValidationError as e:
        message = (
            f"Validation of cache entry for GitHub API call {url} failed: {str(e)}"
        )
        print(message, flush=True)
        _actiondb.log_message(
            username="fishtest.system",
            message=message,
        )

    _lru_cache[inputs] = json
    if saved_http_exception is None:
        return json
    else:
        raise saved_http_exception


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


def is_master(sha, ignore_rate_limit=False):
    global _lru_cache
    inputs = ("is_master", sha)
    if inputs in _lru_cache:
        return _lru_cache[inputs]
    try:
        merge_base_commit = get_merge_base_commit(
            sha1=sha, sha2=official_master_sha, ignore_rate_limit=ignore_rate_limit
        )
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            # sha has been deleted so it can never become master
            _lru_cache[inputs] = False
            return False

    if merge_base_commit == sha:
        # once master, forever master
        _lru_cache[inputs] = True
        return True

    if merge_base_commit != official_master_sha:
        # sha can never become master
        _lru_cache[inputs] = False
        return False

    # there is a theoretical possibility that sha becomes master in the future
    return False


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


normalize_repo_cache = LRUCache(size=128, expiration=600, refresh_on_access=False)


def normalize_repo(repo):
    try:
        return normalize_repo_cache[repo]
    except KeyError:
        pass
    r = call(
        repo,
        _method="HEAD",
        timeout=TIMEOUT,
        allow_redirects=True,
        _ignore_rate_limit=True,
    )
    r.raise_for_status()
    normalize_repo_cache[repo] = r.url
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


def update_official_master_sha():
    global official_master_sha
    try:
        response = get_commit(ignore_rate_limit=True)
        official_master_sha = response["sha"]
    except Exception as e:
        print(
            f"Unable to obtain the official stockfish master sha: {str(e)}",
            flush=True,
        )
    if official_master_sha != _dummy_sha:
        _kvstore["official_master_sha"] = official_master_sha
    else:
        official_master_sha = _kvstore.get("official_master_sha", _dummy_sha)
        if official_master_sha == _dummy_sha:
            print("Unable to initialize the official master sha", flush=True)
