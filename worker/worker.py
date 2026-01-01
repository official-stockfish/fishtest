#!/usr/bin/env python3
import base64
import getpass
import gzip
import hashlib
import importlib
import io
import json
import multiprocessing
import os
import platform
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zlib
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from configparser import ConfigParser
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

try:
    from expression import Expression_Parser
except ImportError:
    from packages.expression import Expression_Parser
try:
    import openlock
except (ImportError, SyntaxError):
    from packages import openlock
try:
    import requests
except ImportError:
    from packages import requests

from games import (
    EXE_SUFFIX,
    IS_MACOS,
    IS_WINDOWS,
    FatalException,
    RunException,
    WorkerException,
    add_auth,
    backup_log,
    cache_read,
    cache_write,
    download_from_github,
    format_returncode,
    log,
    requests_get,
    run_games,
    send_api_post_request,
    str_signal,
    text_hash,
    trim_files,
    unzip,
)
from updater import update

LOCK_FILE = Path(__file__).resolve().parent / "fishtest_worker.lock"

# Minimum requirement of compiler version for Stockfish.
MIN_GCC_MAJOR = 9
MIN_GCC_MINOR = 3

MIN_CLANG_MAJOR = 10
MIN_CLANG_MINOR = 0

FASTCHESS_SHA = "e892ad92a74c8a4fd7184b9e4867b97ae8952685"

WORKER_VERSION = 306
FILE_LIST = ["updater.py", "worker.py", "games.py"]
HTTP_TIMEOUT = 30.0
INITIAL_RETRY_TIME = 15.0
THREAD_JOIN_TIMEOUT = 15.0
MAX_RETRY_TIME = 900.0  # 15 minutes

# We do not import "google.colab" directly since it is not used
# and there are subtleties involved in deleting it after import
# (see #2395).
# Note that checking for "google.colab" implies importing "google".
# So we first check for the latter to avoid an ImportError.
IS_COLAB = (
    importlib.util.find_spec("google") is not None
    and importlib.util.find_spec("google.colab") is not None
)

CONFIGFILE = "fishtest.cfg"

LOGO = r"""
______ _     _     _            _                        _
|  ___(_)   | |   | |          | |                      | |
| |_   _ ___| |__ | |_ ___  ___| |_  __      _____  _ __| | _____ _ __
|  _| | / __| '_ \| __/ _ \/ __| __| \ \ /\ / / _ \| '__| |/ / _ \ '__|
| |   | \__ \ | | | ||  __/\__ \ |_   \ V  V / (_) | |  |   <  __/ |
\_|   |_|___/_| |_|\__\___||___/\__|   \_/\_/ \___/|_|  |_|\_\___|_|
"""

"""
Bird's eye view of the worker
=============================

The main control flow of the worker
is as follows:

worker.py : worker()
worker.py :    fetch_and_handle_task()            [in loop]
games.py  :       run_games()
games.py  :          launch_fastchess()           [in loop for spsa]
games.py  :             parse_fastchess_output()

Apis used by the worker
=======================

<fishtest>     = https://tests.stockfishchess.org
<github>       = https://api.github.com
<github-books> = <github>/repos/official-stockfish/books

Heartbeat           <fishtest>/api/beat                                         POST

Setup task          <github>/rate_limit                                         GET
                    <fishtest>/api/request_version                              POST
                    <fishtest>/api/request_task                                 POST
                    <fishtest>/api/nn/<nnue>                                    GET
                    <github-books>/git/trees/master                             GET
                    <github-books>/git/trees/master/blobs/<sha-book>            GET
                    <github>/repos/Disservin/fastchess/zipball/<sha>            GET
                    <github>/repos/<user-repo>/zipball/<sha>                    GET

Main loop           <fishtest>/api/update_task                                  POST
                    <fishtest>/api/request_spsa                                 POST

Finish task         <fishtest>/api/failed_task                                  POST
                    <fishtest>/api/stop_run                                     POST
                    <fishtest>/api/upload_pgn                                   POST


The POST requests are json encoded. For the shape of a valid request, consult
"api.py" in the Fishtest source.

The POST requests return a json encoded dictionary. It may contain a key "error".
In that case the corresponding value is an error message.
"""


def _bool(x):
    x = x.strip().lower()
    if x in {"true", "1"}:
        return True
    if x in {"false", "0"}:
        return False
    raise ValueError(x)


_bool.__name__ = "bool"


def _alpha_numeric(x):
    x = x.strip()
    if x == "_hw":
        return x
    if len(x) <= 1:
        print(f"The prefix {x} is too short.")
        raise ValueError(x)
    if not all(ord(c) < 128 for c in x) or not x.isalnum():
        raise ValueError(x)
    return x[:8]


_alpha_numeric.__name__ = "alphanumeric"


class _memory:
    def __init__(self, MAX):
        self.MAX = MAX
        self.__name__ = "memory"

    def __call__(self, x):
        try:
            e = Expression_Parser(
                variables={"MAX": self.MAX}, functions={"min": min, "max": max}
            )
            ret = round(max(min(e.parse(x), self.MAX), 0))
        except Exception:
            print("Unable to parse expression for max_memory.")
            raise ValueError(x)

        return x, ret


class _concurrency:
    def __init__(self, MAX):
        self.MAX = MAX
        self.__name__ = "concurrency"

    def __call__(self, x):
        try:
            e = Expression_Parser(
                variables={"MAX": self.MAX}, functions={"min": min, "max": max}
            )
            ret = round(e.parse(x))
        except Exception:
            print("Unable to parse expression for concurrency.")
            raise ValueError(x)

        if ret <= 0:
            print("concurrency must be at least 1.")
            raise ValueError(x)

        if ("MAX" not in x and ret >= self.MAX) or ret > self.MAX:
            print(
                f"\nYou cannot have concurrency {ret} but at most:\n"
                f"  a) {self.MAX} with '--concurrency MAX';\n"
                f"  b) {self.MAX - 1} otherwise.\n"
                "Please use option a) only if your computer is very lightly loaded.\n"
            )
            raise ValueError(x)

        return x, ret


def safe_sleep(f):
    try:
        time.sleep(f)
    except Exception:
        print("\nSleep interrupted...")


def generate_sri(install_dir):
    sri = {
        "__version": WORKER_VERSION,
    }
    for file in FILE_LIST:
        item = install_dir / file
        try:
            sri[file] = text_hash(item)
        except Exception as e:
            print(f"Exception computing sri hash of {item}:\n{e}", file=sys.stderr)
            return None
    return sri


def write_sri(install_dir):
    sri = generate_sri(install_dir)
    sri_file = install_dir / "sri.txt"
    print(f"Writing sri hashes to {sri_file}.")
    with open(sri_file, "w") as f:
        json.dump(sri, f)
        f.write("\n")


def verify_sri(install_dir):
    # This is is used by CI and by updater.py.
    # If you change this function, make sure
    # that the update process still works.
    sri = generate_sri(install_dir)
    if sri is None:
        return False
    sri_file = install_dir / "sri.txt"
    try:
        with open(sri_file, "r") as f:
            sri_ = json.load(f)
    except Exception as e:
        print(f"Exception reading {sri_file}:\n{e}", file=sys.stderr)
        return False
    if not isinstance(sri_, dict):
        print(f"The file {sri_file} does not contain a dictionary.")
        return False
    for k, v in sri.items():
        # When we update, the running worker is not the same as the one we are verifying.
        # If the running worker and the verified worker are the same, then a version check is
        # still redundant as different version numbers must result in different worker hashes.
        if k == "__version":
            continue
        if k not in sri_ or v != sri_[k]:
            print(f"The value for {k} is incorrect in {sri_file}.")
            return False
    print(f"The file {sri_file} matches the worker files!")
    return True


def download_sri():
    try:
        return json.loads(download_from_github("worker/sri.txt", repo="fishtest"))
    except Exception:
        return None


def verify_remote_sri(install_dir):
    # Returns:
    # True  : verification succeeded
    # False : verification failed
    # None  : network error: unable to verify
    sri = generate_sri(install_dir)
    sri_ = download_sri()
    if sri_ is None:
        return None
    version = sri_.get("__version", -1)
    if version != WORKER_VERSION:
        print("The master sri file has a different version number. Ignoring!")
        return True
    tainted = False
    for k, v in sri_.items():
        if k not in sri or v != sri[k]:
            print(f"{k} has been modified!")
            tainted = True
    if tainted:
        print("This worker is tainted...")
    else:
        print("Running an unmodified worker...")

    return not tainted


def verify_credentials(remote, username, password, cached):
    # Returns:
    # (True, api_key) : username/password are ok
    # (False, None) : username/password are not ok
    # (None, None) : network error: unable to determine the status of
    #               username/password
    req = {}
    if username != "" and password != "":
        print(
            f"Confirming {'cached' if cached else 'supplied'} credentials with {remote}."
        )
        payload = {"worker_info": {"username": username}, "password": password}
        try:
            req = send_api_post_request(
                remote + "/api/request_version", payload, quiet=True
            )
        except Exception:
            return None, None  # network problem (unrecoverable)
        if "error" in req:
            return False, None  # invalid username/password
        print("Credentials ok!")
        return True, req.get("api_key")
    return False, None  # empty username or password


def verify_api_key(remote, username, api_key, cached):
    # Returns:
    # True  : api_key is ok
    # False : api_key is not ok
    # None  : network error
    if username != "" and api_key != "":
        print(f"Confirming {'cached' if cached else 'supplied'} API key with {remote}.")
        payload = {"worker_info": {"username": username}, "api_key": api_key}
        try:
            req = send_api_post_request(
                remote + "/api/request_version", payload, quiet=True
            )
        except Exception:
            return None
        if "error" in req:
            return False
        print("Auth token ok!")
        return True
    return False


def get_credentials(config, options, args):
    remote = f"{options.protocol}://{options.host}:{options.port}"
    print(f"Worker version {WORKER_VERSION} connecting to {remote}.")

    username = config.get("login", "username")
    password = config.get("login", "password", raw=True)
    api_key = (
        options.api_key
        if options.api_key is not None
        else config.get("login", "api_key", raw=True)
    )
    cached = True
    if len(args) == 2:
        username = args[0]
        password = args[1]
        api_key = options.api_key if options.api_key is not None else ""
        cached = False
    if options.no_validation:
        return username, password, api_key

    if api_key:
        ret = verify_api_key(remote, username, api_key, cached)
        if ret is None:
            return "", "", ""
        if ret:
            return username, password, api_key

    ret, new_api_key = verify_credentials(remote, username, password, cached)
    if ret is None:
        return "", "", ""
    elif not ret:
        try:
            username = input("\nUsername: ")
            if username != "":
                password = getpass.getpass()
            print("")
        except Exception:
            print("\n")
            return "", "", ""
        else:
            ret, new_api_key = verify_credentials(remote, username, password, False)
            if not ret:
                return "", "", ""

    return username, password, new_api_key or api_key


def verify_fastchess(fastchess_path, fastchess_sha):
    # Verify that fastchess is working and has the required minimum version.
    print(f"Obtaining version info for {fastchess_path}...")
    try:
        with subprocess.Popen(
            [fastchess_path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            errors = p.stderr.read()
            pattern = re.compile(
                r"fastchess alpha [0-9]*.[0-9]*.[0-9]* [0-9]*-([0-9a-f-]*)$"
            )
            short_sha = ""
            for line in iter(p.stdout.readline, ""):
                m = pattern.search(line)
                if m:
                    print("Found", line.strip())
                    short_sha = m.group(1)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Running fastchess raised {type(e).__name__}: {e}")
        return False

    if p.returncode != 0:
        print(
            f"Unable to run fastchess. Return code: {format_returncode(p.returncode)}. Error: {errors}"
        )
        return False

    if len(short_sha) < 7:
        print(
            "Unable to find a suitable sha of length 7 or more in the fastchess version."
        )
        return False

    if not fastchess_sha.startswith(short_sha):
        print(
            f"fastchess sha {fastchess_sha} required but the version shows {short_sha}."
        )
        return False

    return True


def setup_fastchess(worker_dir, compiler, concurrency, global_cache, tests=False):
    fastchess_path = (worker_dir / "testing" / "fastchess").with_suffix(EXE_SUFFIX)
    if fastchess_path.exists():
        if verify_fastchess(fastchess_path, FASTCHESS_SHA):
            return True
        else:
            try:
                fastchess_path.unlink()
            except Exception as e:
                print(f"Removing fastchess raised {type(e).__name__}: {e}")
                return False
    tmp_dir = Path(tempfile.mkdtemp(dir=worker_dir))
    try:
        print("Building fastchess from sources...")
        should_cache = False
        fastchess_zip = FASTCHESS_SHA + ".zip"
        blob = cache_read(global_cache, fastchess_zip)

        if blob is None:
            item_url = (
                "https://api.github.com/repos/Disservin/fastchess/zipball/"
                + FASTCHESS_SHA
            )
            print(f"Downloading {item_url}.")
            blob = requests_get(item_url).content
            should_cache = True
        else:
            print(f"Using {fastchess_zip} from global cache.")

        file_list = unzip(blob, tmp_dir)
        build_dir = tmp_dir / os.path.commonprefix([n.filename for n in file_list])

        if should_cache:
            cache_write(global_cache, fastchess_zip, blob)

        os.chdir(build_dir)

        cmds = [
            f"make -j{concurrency} CXX={compiler} GIT_SHA={FASTCHESS_SHA[:8]} GIT_DATE=01010101",
        ]
        if tests:
            cmds[:0] = [
                f"make -j{concurrency} tests CXX={compiler} GIT_SHA={FASTCHESS_SHA[:8]} GIT_DATE=01010101",
                str((build_dir / "fastchess-tests").with_suffix(EXE_SUFFIX)),
                "make clean",
            ]

        for cmd in cmds:
            print(cmd)
            with subprocess.Popen(
                cmd,
                shell=True,
                env=os.environ,
                start_new_session=False if IS_WINDOWS else True,
                stdout=None if tests else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                close_fds=not IS_WINDOWS,
            ) as p:
                try:
                    errors = p.stderr.readlines()
                except Exception as e:
                    if not IS_WINDOWS:
                        os.killpg(p.pid, signal.SIGINT)
                    raise Exception(
                        f"Executing {cmd} raised {type(e).__name__}: {e}"
                    ) from e

            if p.returncode != 0:
                raise Exception(
                    f"Executing {cmd} failed. Return code: "
                    f"{format_returncode(p.returncode)}. Error: {errors}"
                )

        (build_dir / "fastchess").with_suffix(EXE_SUFFIX).replace(fastchess_path)

    except Exception as e:
        print(
            f"Exception downloading, extracting or building fastchess:\n{e}",
            file=sys.stderr,
        )
        return False
    else:
        return (
            verify_fastchess(fastchess_path, FASTCHESS_SHA)
            if fastchess_path.exists()
            else False
        )
    finally:
        os.chdir(worker_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def validate(config, schema):
    for v in schema:
        if not config.has_section(v[0]):
            config.add_section(v[0])
        if not config.has_option(v[0], v[1]):
            config.set(*v[:3])
        else:
            o = config.get(v[0], v[1])
            if callable(v[4]):  # prepocessor
                o1 = v[4](o)
                if o1 != o:
                    print(
                        f"Replacing the value '{o}' of config option '{v[1]}' by '{o1}'."
                    )
                    config.set(v[0], v[1], o1)
                    o = o1
            t = v[3]  # type
            if callable(t):
                try:
                    _ = t(o)
                except Exception:
                    # v[2] is the default
                    print(
                        f"The value '{o}' of config option '{v[1]}' is not of type '{v[3].__name__}'.\n"
                        f"Replacing it by the default value '{v[2]}'."
                    )
                    config.set(*v[:3])
            elif o not in t:  # choices
                print(
                    f"The value '{o}' of config option '{v[1]}' is not in {v[3]}.\n"
                    f"Replacing it by the default value '{v[2]}'."
                )
                config.set(*v[:3])

    # cleanup
    schema_sections = [v[0] for v in schema]
    schema_options = [v[:2] for v in schema]
    for section in config.sections():
        if section not in schema_sections:
            print(f"Removing unknown config section '{section}'.")
            config.remove_section(section)
            continue
        for option in config.options(section):
            if (section, option) not in schema_options:
                print(f"Removing unknown config option '{option}'.")
                config.remove_option(section, option)


def setup_parameters(worker_dir):
    # Step 1: read the config file if it exists.
    config = ConfigParser(inline_comment_prefixes=";", interpolation=None)
    config_file = worker_dir / CONFIGFILE
    try:
        config.read(config_file)
    except Exception as e:
        print(f"Exception reading configfile {config_file}:\n{e}", file=sys.stderr)
        print("Initializing configfile...")
        config = ConfigParser(inline_comment_prefixes=";", interpolation=None)

    # Step 2: probe the host system.

    # Step 2a: determine the amount of available memory.
    mem = 0
    system_type = platform.system().lower()
    try:
        if "linux" in system_type:
            cmd = "free -b"
        elif "windows" in system_type:
            cmd = (
                "powershell (Get-CimInstance Win32_OperatingSystem)"
                ".TotalVisibleMemorySize*1024"
            )
        elif "darwin" in system_type:
            cmd = "sysctl hw.memsize"
        else:
            cmd = ""
            print("Unknown system.")
        with os.popen(cmd) as proc:
            mem_str = str(proc.readlines())
        mem = int(re.search(r"\d+", mem_str).group())
    except Exception as e:
        print(f"Exception checking HW info:\n{e}", file=sys.stderr)
        return None

    # Step 2b: determine the number of cores.
    max_cpu_count = 0
    try:
        max_cpu_count = multiprocessing.cpu_count()
    except Exception as e:
        print(f"Exception checking the CPU cores count:\n{e}", file=sys.stderr)
        return None

    # Step 2c: detect the available compilers.
    compilers = detect_compilers()
    if compilers == {}:
        print("No usable compilers found.")
        return None

    # Step 3: validate config options and replace missing or invalid
    # ones by defaults.

    compiler_names = list(compilers.keys())
    if "g++" not in compiler_names:
        default_compiler = compiler_names[0]
    else:
        default_compiler = "g++"

    schema = [
        # (<section>, <option>, <default>, <type>, <preprocessor>),
        ("login", "username", "", str, None),
        ("login", "password", "", str, None),
        ("login", "api_key", "", str, None),
        ("parameters", "protocol", "https", ["http", "https"], None),
        ("parameters", "host", "tests.stockfishchess.org", str, None),
        ("parameters", "port", "443", int, None),
        (
            "parameters",
            "concurrency",
            "max(1,min(3,MAX-1))",
            _concurrency(MAX=max_cpu_count),
            None,
        ),
        (
            "parameters",
            "max_memory",
            "MAX/2",
            _memory(MAX=mem / 1024 / 1024),
            None,
        ),
        ("parameters", "uuid_prefix", "_hw", _alpha_numeric, None),
        ("parameters", "min_threads", "1", int, None),
        ("parameters", "fleet", "False", _bool, None),
        ("parameters", "global_cache", "", str, None),
        ("parameters", "compiler", default_compiler, compiler_names, None),
        ("private", "hw_seed", str(random.randint(0, 0xFFFFFFFF)), int, None),
    ]

    validate(config, schema)

    # Step 4: parse the command line. Use the current config options as defaults.

    class ExplicitDefaultsHelpFormatter(ArgumentDefaultsHelpFormatter):
        def _get_help_string(self, action):
            if action.const:
                return action.help
            return super()._get_help_string(action)

    parser = ArgumentParser(
        usage="python worker.py [USERNAME PASSWORD] [OPTIONS]",
        formatter_class=ExplicitDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-P",
        "--protocol",
        dest="protocol",
        default=config.get("parameters", "protocol"),
        choices=["http", "https"],
        help="the protocol used by the server",
    )
    parser.add_argument(
        "-n",
        "--host",
        dest="host",
        default=config.get("parameters", "host"),
        help="the hostname of the fishtest server",
    )
    parser.add_argument(
        "-p",
        "--port",
        dest="port",
        default=config.getint("parameters", "port"),
        type=int,
        help="the port of the fishtest server",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        dest="concurrency_",
        metavar="CONCURRENCY",
        default=config.get("parameters", "concurrency"),
        type=_concurrency(MAX=max_cpu_count),
        help="an expression, potentially involving the variable 'MAX', "
        "evaluating to the maximal number of cores that the worker will use",
    )
    parser.add_argument(
        "-m",
        "--max_memory",
        dest="max_memory_",
        metavar="MAX_MEMORY",
        default=config.get("parameters", "max_memory"),
        type=_memory(MAX=mem / 1024 / 1024),
        help="an expression, potentially involving the variable 'MAX', "
        "evaluating to the maximum amount of memory in MiB that the worker will use",
    )
    parser.add_argument(
        "-u",
        "--uuid_prefix",
        dest="uuid_prefix",
        default=config.get("parameters", "uuid_prefix"),
        type=_alpha_numeric,
        help="set the initial part of the UUID (_hw to use an internal algorithm), "
        "if you run more than one worker, please make sure their prefixes are distinct",
    )
    parser.add_argument(
        "-t",
        "--min_threads",
        dest="min_threads",
        default=config.getint("parameters", "min_threads"),
        type=int,
        help="do not accept tasks with fewer threads than MIN_THREADS",
    )
    parser.add_argument(
        "-f",
        "--fleet",
        dest="fleet",
        default=config.getboolean("parameters", "fleet"),
        type=_bool,
        choices=[False, True],  # useful for usage message
        help="if 'True', quit in case of errors or if no task is available",
    )
    parser.add_argument(
        "-g",
        "--global_cache",
        dest="global_cache",
        default=config.get("parameters", "global_cache"),
        type=str,
        help="""Useful only when running multiple workers concurrently:
                an existing absolute path to be used to globally cache on disk
                certain downloads, reducing load on github or net server.
                An empty string ("") disables using a cache.""",
    )
    parser.add_argument(
        "-C",
        "--compiler",
        dest="compiler_",
        default=config.get("parameters", "compiler"),
        type=str,
        choices=compiler_names,
        help="choose the compiler used by the worker",
    )
    parser.add_argument(
        "-w",
        "--only_config",
        dest="only_config",
        action="store_true",
        help="write the configfile, update the sri hashes, and then quit",
    )
    parser.add_argument(
        "-v",
        "--no_validation",
        dest="no_validation",
        action="store_true",
        help="do not validate credentials with server",
    )
    parser.add_argument(
        "--api_key",
        dest="api_key",
        default=None,
        help="override stored API key used for worker authentication",
    )

    def my_error(e):
        raise Exception(e)

    parser.error = my_error
    try:
        (options, args) = parser.parse_known_args()
    except Exception as e:
        print(str(e))
        return None

    if len(args) not in [0, 2]:
        print(f"Unparsed command line arguments: {' '.join(args)}")
        parser.print_usage()
        return None

    # Step 5: fixup the config options.

    options.concurrency_, options.concurrency = options.concurrency_
    options.max_memory_, options.max_memory = options.max_memory_

    if options.protocol == "http" and options.port == 443:
        # Rewrite old port 443 to 80
        print("Changing port to 80.")
        options.port = 80
    elif options.protocol == "https" and options.port == 80:
        # Rewrite old port 80 to 443
        print("Changing port to 443.")
        options.port = 443

    # Limit concurrency so that at least STC tests can run with the available memory
    # The memory needs per engine are:
    # 16 for the TT Hash, 12 for the process, 139 for the net, and 31 per thread
    # 220 is the need for fastchess, 2 * 80 for the binaries, 64 for python
    # These numbers need to be up-to-date with the server values
    STC_memory = 2 * (16 + 12 + 139 + 31)
    fc_memory = 220 + 2 * 80 + 64
    max_concurrency = int((options.max_memory - fc_memory) / STC_memory)
    if max_concurrency < 1:
        print(
            f"You need to reserve at least {STC_memory + fc_memory} MiB to run the worker!"
        )
        return None
    options.concurrency_reduced = False
    if max_concurrency < options.concurrency:
        print(
            "Changing concurrency to allow for running STC tests with the available memory."
        )
        print(
            f"The required memory to run with {options.concurrency} concurrency is {STC_memory * options.concurrency + fc_memory} MiB."
        )
        print(f"The concurrency has been reduced to {max_concurrency}.")
        print("Consider increasing max_memory if possible.")
        options.concurrency = max_concurrency
        options.concurrency_reduced = True

    options.compiler = compilers[options.compiler_]

    options.hw_id = hw_id(config.getint("private", "hw_seed"))
    print(f"Default uuid_prefix: {options.hw_id}")

    # Step 6: determine credentials.

    username, password, api_key = get_credentials(config, options, args)

    if username == "":
        print("Invalid or missing credentials.")
        return None

    options.username = username
    options.password = password
    options.api_key = api_key

    # Step 7: write command line parameters to the config file.
    config.set("login", "username", options.username)
    config.set("login", "password", options.password)
    config.set("login", "api_key", options.api_key)
    config.set("parameters", "protocol", options.protocol)
    config.set("parameters", "host", options.host)
    config.set("parameters", "port", str(options.port))
    config.set(
        "parameters",
        "concurrency",
        options.concurrency_
        + f" ; = {options.concurrency} cores"
        + (" (reduced)" if options.concurrency_reduced else ""),
    )
    config.set(
        "parameters",
        "max_memory",
        options.max_memory_ + f" ; = {options.max_memory} MiB",
    )
    config.set(
        "parameters",
        "uuid_prefix",
        options.uuid_prefix
        + (f" ; = {options.hw_id}" if options.uuid_prefix == "_hw" else ""),
    )
    config.set("parameters", "min_threads", str(options.min_threads))
    config.set("parameters", "fleet", str(options.fleet))
    config.set("parameters", "global_cache", str(options.global_cache))
    config.set("parameters", "compiler", options.compiler_)

    with open(config_file, "w") as f:
        config.write(f)

    # Step 8: give some feedback to the user.

    print(f"System memory determined to be: {mem / 1024**3:.3f}GiB.")
    print(
        f"Worker constraints: {{'concurrency': {options.concurrency}, 'max_memory': {options.max_memory}, 'min_threads': {options.min_threads}}}"
    )
    print(f"Config file {config_file} written.")

    return options


def on_sigint(current_state, signal, frame):
    current_state["alive"] = False
    raise FatalException(f"Terminated by signal {str_signal(signal)}.")


def fingerprint(s):
    # A cryptographically secure hash
    return int.from_bytes(
        hashlib.md5(str(s).encode("utf-8")).digest()[:4], byteorder="big"
    )


def read_winreg(path, name):
    import winreg

    views = [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]
    value = None
    for v in views:
        try:
            registry_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | v
            )
            value, regtype = winreg.QueryValueEx(registry_key, name)
            winreg.CloseKey(registry_key)
            break
        except WindowsError:
            pass
    return value


def get_machine_id():
    if IS_WINDOWS:
        # Get Windows machine_id from the registry key:
        # HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography\MachineGuid
        # See https://www.medo64.com/2020/04/unique-machine-id/ .
        path = r"SOFTWARE\Microsoft\Cryptography"
        name = "MachineGuid"
        machine_id = read_winreg(path, name)
        if machine_id is not None:
            print(
                f"machine_id {machine_id} obtained from HKEY_LOCAL_MACHINE\\{path}\\{name}."
            )
            return machine_id
    elif IS_MACOS:
        # https://stackoverflow.com/questions/11999886/get-machine-id-of-mac-os-x
        # Somebody with a Mac should clean this code up a bit.
        cmd = "ioreg -rd1 -c IOPlatformExpertDevice"
        machine_uuid_str = ""
        try:
            with subprocess.Popen(
                cmd.split(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                close_fds=not IS_WINDOWS,
            ) as p:
                for line in iter(p.stdout.readline, ""):
                    if "UUID" not in line:
                        continue
                    if not line:
                        break
                    machine_uuid_str += line
        except Exception as e:
            print(f"Exception while reading the machine_id:\n{e}", file=sys.stderr)
        if machine_uuid_str != "":
            match_obj = re.compile(
                "[A-Z,0-9]{8,8}-"
                + "[A-Z,0-9]{4,4}-"
                + "[A-Z,0-9]{4,4}-"
                + "[A-Z,0-9]{4,4}-"
                + "[A-Z,0-9]{12,12}"
            )
            result = match_obj.findall(machine_uuid_str)
            if len(result) > 0:
                machine_id = result[0]
                print(f"machine_id {machine_id} obtained via '{cmd}'.")
                return machine_id
    elif os.name == "posix":
        host_ids = ["/etc/machine-id", "/var/lib/dbus/machine-id"]
        for file in host_ids:
            try:
                with open(file) as f:
                    machine_id = f.read().strip()
                    print(f"machine_id {machine_id} obtained from {file}.")
                    return machine_id
            except Exception:
                pass
    print("Unable to obtain the machine id.")
    return ""


def hw_id(hw_seed):
    fingerprint_machine = fingerprint(get_machine_id())
    fingerprint_path = fingerprint(Path(__file__).resolve())
    return format(hw_seed ^ fingerprint_machine ^ fingerprint_path, "08x")


def get_uuid(options):
    if options.uuid_prefix == "_hw":
        uuid_prefix = options.hw_id
    else:
        uuid_prefix = options.uuid_prefix

    return uuid_prefix[:8] + str(uuid.uuid4())[8:]


def get_remaining_github_api_calls():
    try:
        rate = requests.get("https://api.github.com/rate_limit", timeout=HTTP_TIMEOUT)
        rate.raise_for_status()
        return rate.json()["resources"]["core"]["remaining"]
    except Exception as e:
        print(
            f"Exception fetching rate_limit (invalid ~/.netrc?):\n{e}", file=sys.stderr
        )
        return 0


def gcc_version():
    """Parse the output of g++ -E -dM -"""
    try:
        with subprocess.Popen(
            ["g++", "-E", "-dM", "-"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            for line in iter(p.stdout.readline, ""):
                if "__clang_major__" in line:
                    print("clang++ poses as g++.")
                    return None
                if "__GNUC__" in line:
                    major = line.split()[2]
                if "__GNUC_MINOR__" in line:
                    minor = line.split()[2]
                if "__GNUC_PATCHLEVEL__" in line:
                    patchlevel = line.split()[2]
    except (OSError, subprocess.SubprocessError):
        print("No g++ or g++ is not executable.")
        return None
    if p.returncode != 0:
        print(
            f"g++ version query failed with return code {format_returncode(p.returncode)}."
        )
        return None

    try:
        major = int(major)
        minor = int(minor)
        patchlevel = int(patchlevel)
        compiler = "g++"
    except Exception:
        print("Failed to parse g++ version.")
        return None

    if (major, minor) < (MIN_GCC_MAJOR, MIN_GCC_MINOR):
        print(
            f"Found g++ version {major}.{minor}.{patchlevel}. First usable version is {MIN_GCC_MAJOR}.{MIN_GCC_MINOR}.0."
        )
        return None
    print(f"Found {compiler} version {major}.{minor}.{patchlevel}.")
    return (compiler, major, minor, patchlevel)


def clang_version():
    """Parse the output of clang++ -E -dM -"""
    try:
        with subprocess.Popen(
            ["clang++", "-E", "-dM", "-"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            for line in iter(p.stdout.readline, ""):
                if "__clang_major__" in line:
                    clang_major = line.split()[2]
                if "__clang_minor__" in line:
                    clang_minor = line.split()[2]
                if "__clang_patchlevel__" in line:
                    clang_patchlevel = line.split()[2]
    except (OSError, subprocess.SubprocessError):
        print("No clang++ or clang++ is not executable.")
        return None
    if p.returncode != 0:
        print(
            f"clang++ version query failed with return code {format_returncode(p.returncode)}."
        )
        return None
    try:
        major = int(clang_major)
        minor = int(clang_minor)
        patchlevel = int(clang_patchlevel)
        compiler = "clang++"
    except Exception:
        print("Failed to parse clang++ version.")
        return None

    if (major, minor) < (MIN_CLANG_MAJOR, MIN_CLANG_MINOR):
        print(
            f"Found clang++ version {major}.{minor}.{patchlevel}. First usable version is {MIN_CLANG_MAJOR}.{MIN_CLANG_MINOR}.0."
        )
        return None

    # Check for a common toolchain issue
    try:
        subprocess.run(
            (["xcrun"] if IS_MACOS else []) + ["llvm-profdata", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        print(
            "clang++ is present but misconfigured: the command 'llvm-profdata' is missing."
        )
        return None

    print(f"Found {compiler} version {major}.{minor}.{patchlevel}.")
    return (compiler, major, minor, patchlevel)


def detect_compilers():
    ret = {}
    gcc_version_ = gcc_version()
    if gcc_version_ is not None:
        ret["g++"] = gcc_version_
    clang_version_ = clang_version()
    if clang_version_ is not None:
        ret["clang++"] = clang_version_
    return ret


def verify_toolchain():
    print("Toolchain check...")
    cmds = {
        "strip": ["strip", "-V"],
        "make": ["make", "-v"],
    }
    if IS_MACOS:
        # MacOSX appears not to have a method to detect strip
        cmds["strip"] = ["which", "strip"]

    missing_tools = []
    for name, cmd in cmds.items():
        cmd_str = " ".join(cmd)
        try:
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if p.returncode != 0:
                print(
                    f"'{cmd_str}' returned code: {format_returncode(p.returncode)} and error: {p.stderr.decode().strip()}"
                )
                missing_tools.append(name)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"'{cmd_str}' raised: {type(e).__name__}: {e}")
            missing_tools.append(name)

    if missing_tools:
        print(f"Missing required tools: {', '.join(missing_tools)}")
        return False
    return True


def get_exception(files):
    i = 0
    exc_type, exc_obj, tb = sys.exc_info()
    filename, lineno, name, line = traceback.extract_tb(tb)[i]
    filename = Path(filename).name
    message = f"Exception {exc_type.__name__} at {filename}:{lineno} WorkerVersion: {WORKER_VERSION}"
    while filename in files:
        message = f"Exception {exc_type.__name__} at {filename}:{lineno} WorkerVersion: {WORKER_VERSION}"
        i += 1
        try:
            filename, lineno, name, line = traceback.extract_tb(tb)[i]
            filename = Path(filename).name
        except Exception:
            break
    return message


def heartbeat(worker_info, auth, remote, current_state):
    print("Start heartbeat.")
    payload = {"worker_info": worker_info}
    while current_state["alive"]:
        time.sleep(1)
        now = datetime.now(timezone.utc)
        if current_state["last_updated"] + timedelta(seconds=120) < now:
            print(f"  Send heartbeat for {worker_info['unique_key']}... ", end="")
            current_state["last_updated"] = now
            run = current_state["run"]
            payload["run_id"] = str(run["_id"]) if run else None
            task_id = current_state["task_id"]
            payload["task_id"] = task_id
            add_auth(payload, auth)
            if payload["run_id"] is None or payload["task_id"] is None:
                print("Skipping heartbeat...")
                continue
            try:
                req = send_api_post_request(remote + "/api/beat", payload, quiet=True)
            except Exception as e:
                print(f"Exception calling heartbeat:\n{e}", file=sys.stderr)
            else:
                if "error" not in req:
                    print("(received)")
                    task_alive = req.get("task_alive", True)
                    if not task_alive:
                        print(
                            "The server told us that no more games are needed for the current task."
                        )
                        current_state["task_id"] = None
                        current_state["run"] = None
                else:
                    # Error message has already been printed.
                    current_state["task_id"] = None
                    current_state["run"] = None
    else:
        print("Heartbeat stopped.")


def utcoffset():
    dst = time.localtime().tm_isdst == 1 and time.daylight != 0
    utcoffset = -time.altzone if dst else -time.timezone
    abs_utcoffset_min = abs(utcoffset // 60)
    hh, mm = divmod(abs_utcoffset_min, 60)
    return f"{'+' if utcoffset >= 0 else '-'}{hh:02d}:{mm:02d}"


def verify_worker_version(remote, username, auth, worker_lock):
    # Returns:
    # True: we are the right version and have the correct credentials
    # False: incorrect credentials (the user may have been blocked in the meantime)
    # None: network error: unable to verify
    # We don't return if the server informs us that a newer version of the worker
    # is available
    print("Verify worker version...")
    payload = {"worker_info": {"username": username}}
    add_auth(payload, auth)
    try:
        req = send_api_post_request(remote + "/api/request_version", payload)
    except WorkerException:
        return None  # the error message has already been written
    if "error" in req:
        if auth.get("api_key") and auth.get("password"):
            print("API key rejected, retrying with password.")
            payload = {
                "worker_info": {"username": username},
                "password": auth["password"],
            }
            try:
                req = send_api_post_request(remote + "/api/request_version", payload)
            except WorkerException:
                return None
            if "error" in req:
                return False
            if "api_key" in req:
                auth["api_key"] = req["api_key"]
        else:
            return False  # likewise
    if "api_key" in req:
        auth["api_key"] = req["api_key"]
    if req["version"] > WORKER_VERSION:
        print(f"Updating worker version to {req['version']}.")
        backup_log()
        try:
            worker_lock.release()
            update()
        except Exception as e:
            print(
                f"Exception while updating to version {req['version']}:\n{e}",
                file=sys.stderr,
            )
        print(f"Attempted update to worker version {req['version']} failed!")
        return False
    return True


def fetch_and_handle_task(
    worker_dir,
    worker_info,
    auth,
    remote,
    current_state,
    global_cache,
    worker_lock,
):
    # This function should normally not raise exceptions.
    # Unusual conditions are handled by returning False.
    # If an immediate exit is necessary then one can set
    # current_state["alive"] to False.

    # Print the current time for log purposes
    print(
        f"Current time is {datetime.now(timezone.utc)} UTC (local offset: {utcoffset()})."
    )

    # Check the worker version and upgrade if necessary
    ret = verify_worker_version(remote, worker_info["username"], auth, worker_lock)
    if ret is False:
        current_state["alive"] = False
    if not ret:
        return False

    # Clean up old files:
    trim_files(worker_dir / "testing")

    # Verify if we still have enough GitHub api calls
    remaining = get_remaining_github_api_calls()
    print(f"Remaining number of GitHub api calls = {remaining}.")
    near_github_api_limit = remaining <= 10
    if near_github_api_limit:
        print(
            """
  We have almost exhausted our GitHub api calls.
  The server will only give us tasks for tests we have seen before.
"""
        )
    worker_info["near_github_api_limit"] = near_github_api_limit

    # Let's go!
    print("Fetching task...")
    payload = {"worker_info": worker_info}
    add_auth(payload, auth)
    try:
        req = send_api_post_request(remote + "/api/request_task", payload)
    except WorkerException:
        return False  # error message has already been printed

    if "error" in req:
        return False  # likewise

    # No tasks ready for us yet, just wait...
    if "task_waiting" in req:
        print("No tasks available at this time, waiting...")
        return False

    run, task_id = req["run"], req["task_id"]
    current_state["run"] = run
    current_state["task_id"] = task_id

    print(f"Working on task {task_id} from {remote}/tests/view/{run['_id']}.")
    if "sprt" in run["args"]:
        run_type = "sprt"
    elif "spsa" in run["args"]:
        run_type = "spsa"
    else:
        run_type = "num_games"
    log(
        "run: {} task: {} size: {} tc: {} concurrency: {} threads: {} [ {} : {} ]".format(
            run["_id"],
            task_id,
            run["my_task"]["num_games"],
            run["args"]["tc"],
            worker_info["concurrency"],
            run["args"]["threads"],
            run_type,
            run["args"]["num_games"],
        )
    )
    print(f"Running {run['args']['new_tag']} vs {run['args']['base_tag']}.")

    success = False
    message = ""
    server_message = ""
    api = remote + "/api/failed_task"
    pgn_file = {"name": None, "CRC": None}

    try:
        run_games(
            worker_dir,
            worker_info,
            current_state,
            auth,
            remote,
            run,
            task_id,
            pgn_file,
            global_cache,
        )
        success = True
    except FatalException as e:
        message = str(e)
        server_message = message
        current_state["alive"] = False
    except RunException as e:
        message = str(e)
        server_message = message
        api = remote + "/api/stop_run"
    except WorkerException as e:
        message = str(e)
        server_message = message
    except Exception as e:
        server_message = get_exception(["worker.py", "games.py"])
        message = f"{server_message} ({e})"
        current_state["alive"] = False

    current_state["task_id"] = None
    current_state["run"] = None

    payload = {
        "run_id": str(run["_id"]),
        "task_id": task_id,
        "message": server_message,
        "worker_info": worker_info,
    }
    add_auth(payload, auth)

    if not success:
        print(f"\nException running games:\n{message}", file=sys.stderr)
        print("Informing the server.")
        try:
            req = send_api_post_request(api, payload)
        except Exception as e:
            print(f"Exception posting failed_task:\n{e}", file=sys.stderr)

    def upload_pgn_data(pgn_data, run_id, task_id, remote, payload):
        with io.BytesIO() as gz_buffer:
            with gzip.GzipFile(
                filename=f"{str(run_id)}-{task_id}.pgn.gz",
                mode="wb",
                fileobj=gz_buffer,
            ) as gz:
                gz.write(pgn_data.encode())
            payload["pgn"] = base64.b64encode(gz_buffer.getvalue()).decode()

        print(f"Uploading compressed PGN of {len(payload['pgn'])} bytes.")
        send_api_post_request(remote + "/api/upload_pgn", payload)

    if (
        not pgn_file["name"]
        or not pgn_file["name"].exists()
        or pgn_file["name"].stat().st_size == 0
    ):
        print("Task exited")
        return success

    crc_expected = pgn_file["CRC"]
    pgn_file = pgn_file["name"]

    # Upload PGN file.
    if "spsa" not in run["args"]:
        try:
            file_content = pgn_file.read_bytes()

            crc_actual = hex(zlib.crc32(file_content))

            # Check that the file is not corrupted
            if crc_actual != crc_expected:
                print(
                    f"Checksum of file ({crc_actual}) does not match expected value ({crc_expected}).\nSkipping upload."
                )
            else:
                # Decode bytes to text, ignoring non UTF-8 characters
                data = file_content.decode("utf-8", errors="ignore")
                upload_pgn_data(data, run["_id"], task_id, remote, payload)
        except Exception as e:
            print(f"\nException uploading PGN file:\n{e}", file=sys.stderr)

    print("Task exited.")
    return success


def worker():
    print(LOGO)
    worker_lock = None
    try:
        worker_lock = openlock.FileLock(LOCK_FILE)
        worker_lock.acquire(timeout=0)
    except openlock.Timeout:
        print(
            f"\n*** Another worker (with PID={worker_lock.getpid()}) is already running in this "
            "directory. ***"
        )
        return 1
    # Make sure that the worker can upgrade!
    except Exception as e:
        print(f"\n *** Unexpected exception: {e} ***\n")

    worker_dir = Path(__file__).resolve().parent
    print(f"Worker started in {worker_dir} with PID={os.getpid()}.")

    # Create the testing directory if missing.
    (worker_dir / "testing").mkdir(exist_ok=True)

    # We record some state that is shared by the three
    # parallel event handling mechanisms:
    # - the main loop;
    # - the heartbeat loop;
    # - the signal handler.
    current_state = {
        "run": None,  # the current run
        "task_id": None,  # the id of the current task
        "alive": True,  # controls the main and heartbeat loop
        "last_updated": datetime.now(
            timezone.utc
        ),  # tracks the last update to the server
    }

    # Install signal handlers.
    signal.signal(signal.SIGINT, partial(on_sigint, current_state))
    signal.signal(signal.SIGTERM, partial(on_sigint, current_state))
    try:
        signal.signal(signal.SIGQUIT, partial(on_sigint, current_state))
    except Exception:
        # Windows does not have SIGQUIT.
        pass
    try:
        signal.signal(signal.SIGBREAK, partial(on_sigint, current_state))
    except Exception:
        # Linux does not have SIGBREAK.
        pass

    # Handle command line parameters and the config file.
    options = setup_parameters(worker_dir)

    if options is None:
        print("Error parsing options. Config file not written.")
        return 1

    # Write sri hashes of the worker files
    write_sri(worker_dir)

    if options.only_config:
        return 0

    remote = f"{options.protocol}://{options.host}:{options.port}"
    auth = {"password": options.password, "api_key": options.api_key}

    # Check the worker version and upgrade if necessary
    try:
        if verify_worker_version(remote, options.username, auth, worker_lock) is False:
            return 1
    except Exception as e:
        print(f"Exception verifying worker version:\n{e}", file=sys.stderr)
        return 1

    # Assemble the config/options data as well as some other data in a
    # "worker_info" dictionary.
    # This data will be sent to the server when a new task is requested.

    compiler, major, minor, patchlevel = options.compiler
    print(f"Using {compiler} {major}.{minor}.{patchlevel}.")

    # Check for common tool chain issues
    if not verify_toolchain():
        return 1

    # Make sure we have a working fastchess
    if not setup_fastchess(
        worker_dir, compiler, options.concurrency, options.global_cache, tests=True
    ):
        return 1

    # Check if we are running an unmodified worker
    unmodified = verify_remote_sri(worker_dir)
    if unmodified is None:
        return 1

    uname = platform.uname()
    worker_info = {
        "uname": uname[0] + " " + uname[2] + (" (colab)" if IS_COLAB else ""),
        "architecture": platform.architecture(),
        "concurrency": options.concurrency,
        "max_memory": options.max_memory,
        "min_threads": options.min_threads,
        "username": options.username,
        "version": WORKER_VERSION,
        "python_version": (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        ),
        "gcc_version": (
            major,
            minor,
            patchlevel,
        ),
        "compiler": compiler,
        "unique_key": get_uuid(options),
        "modified": not unmodified,
        "ARCH": "?",
        "nps": 0.0,
        "near_github_api_limit": False,
    }

    print("UUID:", worker_info["unique_key"])

    # Start heartbeat thread as a daemon (not strictly necessary, but there might be bugs)
    heartbeat_thread = threading.Thread(
        target=heartbeat,
        args=(worker_info, auth, remote, current_state),
        daemon=True,
    )
    heartbeat_thread.start()

    # If fleet==True then the worker will quit if it is unable to obtain
    # or execute a task. If fleet==False then the worker will go to the
    # next iteration of the main loop.
    # The reason for the existence of this parameter is that it allows
    # a fleet of workers to quickly quit as soon as the queue is empty
    # or the server is down.

    # Start the main loop.
    delay = INITIAL_RETRY_TIME
    fish_exit = False

    while current_state["alive"]:
        success = fetch_and_handle_task(
            worker_dir,
            worker_info,
            auth,
            remote,
            current_state,
            options.global_cache,
            worker_lock,
        )
        if (worker_dir / "fish.exit").is_file():
            current_state["alive"] = False
            print("Stopped by 'fish.exit' file.")
            fish_exit = True
            break
        elif not current_state["alive"]:  # the user may have pressed Ctrl-C...
            break
        elif not success:
            if options.fleet:
                current_state["alive"] = False
                print("Exiting the worker since fleet==True and an error occurred.")
                break
            else:
                print(f"Waiting {delay} seconds before retrying.")
                safe_sleep(delay)
                delay = min(MAX_RETRY_TIME, delay * 2)
        else:
            delay = INITIAL_RETRY_TIME

    if fish_exit:
        print("Removing fish.exit file.")
        (worker_dir / "fish.exit").unlink()

    print("Releasing the worker lock.")
    worker_lock.release()

    print("Waiting for the heartbeat thread to finish...")
    heartbeat_thread.join(THREAD_JOIN_TIMEOUT)

    return 0 if fish_exit else 1


if __name__ == "__main__":
    sys.exit(worker())
