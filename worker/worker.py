#!/usr/bin/env python3
import atexit
import base64
import getpass
import gzip
import hashlib
import io
import json
import multiprocessing
import os
import platform
import random
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import traceback
import uuid
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from configparser import ConfigParser
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

# Fall back to the provided packages if missing in the local system.

packages_dir = Path(__file__).resolve().parent / "packages"
sys.path.append(str(packages_dir))

import requests
from games import (
    EXE_SUFFIX,
    IS_MACOS,
    IS_WINDOWS,
    FatalException,
    RunException,
    WorkerException,
    backup_log,
    download_from_github,
    format_return_code,
    log,
    run_games,
    send_api_post_request,
    str_signal,
    unzip,
)
from packages import expression
from updater import update

# Several packages are called "expression".
# So we make sure to use the locally installed one.

# Minimum requirement of compiler version for Monty.
MIN_CARGO_MAJOR = 1
MIN_CARGO_MINOR = 77

WORKER_VERSION = 0
FILE_LIST = ["updater.py", "worker.py", "games.py"]
HTTP_TIMEOUT = 30.0
INITIAL_RETRY_TIME = 15.0
THREAD_JOIN_TIMEOUT = 15.0
MAX_RETRY_TIME = 900.0  # 15 minutes
IS_COLAB = False
try:
    import google.colab

    IS_COLAB = True
    del google.colab
except:
    pass
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
games.py  :          launch_cutechess()           [in loop for spsa]
games.py  :             parse_cutechess_output()

Apis used by the worker
=======================

<fishtest>     = https://montychess.org
<github>       = https://api.github.com
<github-books> = <github>/repos/official-monty/books

Heartbeat           <fishtest>/api/beat                                         POST

Setup task          <github>/rate_limit                                         GET
                    <fishtest>/api/request_version                              POST
                    <fishtest>/api/request_task                                 POST
                    <fishtest>/api/nn/<nnue>                                    GET
                    <github-books>/git/trees/master                             GET
                    <github-books>/git/trees/master/blobs/<sha-cutechess-cli>   GET
                    <github-books>/git/trees/master/blobs/<sha-book>            GET
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
        print("The prefix {} is too short".format(x))
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
        e = expression.Expression_Parser(
            variables={"MAX": self.MAX}, functions={"min": min, "max": max}
        )
        try:
            ret = round(max(min(e.parse(x), self.MAX), 0))
        except:
            print("Unable to parse expression for max_memory")
            raise ValueError(x)

        return x, ret


class _concurrency:
    def __init__(self, MAX):
        self.MAX = MAX
        self.__name__ = "concurrency"

    def __call__(self, x):
        e = expression.Expression_Parser(
            variables={"MAX": self.MAX}, functions={"min": min, "max": max}
        )
        try:
            ret = round(e.parse(x))
        except:
            print("Unable to parse expression for concurrency")
            raise ValueError(x)

        if ret <= 0:
            print("concurrency must be at least 1")
            raise ValueError(x)

        if ("MAX" not in x and ret >= self.MAX) or ret > self.MAX:
            print(
                (
                    "\nYou cannot have concurrency {} but at most:\n"
                    "  a) {} with '--concurrency MAX';\n"
                    "  b) {} otherwise.\n"
                    "Please use option a) only if your computer is very lightly loaded.\n"
                ).format(
                    ret,
                    self.MAX,
                    self.MAX - 1,
                )
            )
            raise ValueError(x)

        return x, ret


def safe_sleep(f):
    try:
        time.sleep(f)
    except:
        print("\nSleep interrupted...")


def text_hash(file):
    # text mode to have newline translation!
    return base64.b64encode(
        hashlib.sha384(file.read_text().encode("utf8")).digest()
    ).decode("utf8")


def generate_sri(install_dir):
    sri = {
        "__version": WORKER_VERSION,
    }
    for file in FILE_LIST:
        item = install_dir / file
        try:
            sri[file] = text_hash(item)
        except Exception as e:
            print(
                "Exception computing sri hash of {}:\n".format(item),
                e,
                sep="",
                file=sys.stderr,
            )
            return None
    return sri


def write_sri(install_dir):
    sri = generate_sri(install_dir)
    sri_file = install_dir / "sri.txt"
    print("Writing sri hashes to {}".format(sri_file))
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
        print("Exception reading {}:\n".format(sri_file), e, sep="", file=sys.stderr)
        return False
    if not isinstance(sri_, dict):
        print("The file {} does not contain a dictionary".format(sri_file))
        return False
    for k, v in sri.items():
        # When we update, the running worker is not the same as the one we are verifying.
        # If the running worker and the verified worker are the same then a version check is
        # still redundant as different version numbers must result in different worker hashes.
        if k == "__version":
            continue
        if k not in sri_ or v != sri_[k]:
            print("The value for {} is incorrect in {}".format(k, sri_file))
            return False
    print("The file {} matches the worker files!".format(sri_file))
    return True


def download_sri():
    try:
        return json.loads(
            download_from_github(
                "worker/sri.txt", owner="official-monty", repo="montytest"
            )
        )
    except:
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
            print("{} has been modified!".format(k))
            tainted = True
    if tainted:
        print("This worker is tainted...")
    else:
        print("Running an unmodified worker...")

    return not tainted


def verify_credentials(remote, username, password, cached):
    # Returns:
    # True  : username/password are ok
    # False : username/password are not ok
    # None  : network error: unable to determine the status of
    #         username/password
    req = {}
    if username != "" and password != "":
        print(
            "Confirming {} credentials with {}".format(
                "cached" if cached else "supplied", remote
            )
        )
        payload = {"worker_info": {"username": username}, "password": password}
        try:
            req = send_api_post_request(
                remote + "/api/request_version", payload, quiet=True
            )
        except:
            return None  # network problem (unrecoverable)
        if "error" in req:
            return False  # invalid username/password
        print("Credentials ok!")
        return True
    return False  # empty username or password


def get_credentials(config, options, args):
    remote = "{}://{}:{}".format(options.protocol, options.host, options.port)
    print("Worker version {} connecting to {}".format(WORKER_VERSION, remote))

    username = config.get("login", "username")
    password = config.get("login", "password", raw=True)
    cached = True
    if len(args) == 2:
        username = args[0]
        password = args[1]
        cached = False
    if options.no_validation:
        return username, password

    ret = verify_credentials(remote, username, password, cached)
    if ret is None:
        return "", ""
    elif not ret:
        try:
            print("")
            username = input("Username: ")
            if username != "":
                password = getpass.getpass()
            print("")
        except:
            print("\n")
            return "", ""
        else:
            if not verify_credentials(remote, username, password, False):
                return "", ""

    return username, password


def download_cutechess(cutechess, save_dir):
    if len(EXE_SUFFIX) > 0:
        zipball = "cutechess-cli-win.zip"
    elif IS_MACOS:
        zipball = "cutechess-cli-macos-64bit.zip"
    else:
        zipball = "cutechess-cli-linux-{}.zip".format(platform.architecture()[0])
    try:
        blob = download_from_github(zipball)
        unzip(blob, save_dir)

        os.chmod(cutechess, os.stat(cutechess).st_mode | stat.S_IEXEC)
    except Exception as e:
        print(
            "Exception downloading or extracting {}:\n".format(zipball),
            e,
            sep="",
            file=sys.stderr,
        )
    else:
        print("Finished downloading {}".format(cutechess))


def verify_required_cutechess(cutechess_path):
    # Verify that cutechess is working and has the required minimum version.

    if not cutechess_path.exists():
        return False

    print("Obtaining version info for {} ...".format(cutechess_path))

    try:
        with subprocess.Popen(
            [cutechess_path, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            errors = p.stderr.read()
            pattern = re.compile(r"cutechess-cli ([0-9]+)\.([0-9]+)\.([0-9]+)")
            major, minor, patch = 0, 0, 0
            for line in iter(p.stdout.readline, ""):
                m = pattern.search(line)
                if m:
                    print("Found", line.strip())
                    major = int(m.group(1))
                    minor = int(m.group(2))
                    patch = int(m.group(3))
    except (OSError, subprocess.SubprocessError) as e:
        print("Unable to run cutechess-cli. Error: {}".format(str(e)))
        return False

    if p.returncode != 0:
        print(
            "Unable to run cutechess-cli. Return code: {}. Error: {}".format(
                format_return_code(p.returncode), errors
            )
        )
        return False

    if major + minor + patch == 0:
        print("Unable to find the version of cutechess-cli.")
        return False

    if (major, minor) < (1, 2):
        print("Requires cutechess 1.2 or higher, found version doesn't match")
        return False

    return True


def setup_cutechess(worker_dir):
    # Create the testing directory if missing.
    testing_dir = worker_dir / "testing"
    testing_dir.mkdir(exist_ok=True)

    curr_dir = Path.cwd()

    try:
        os.chdir(testing_dir)
    except Exception as e:
        print("Unable to enter {}. Error: {}".format(testing_dir, str(e)))
        return False

    cutechess = "cutechess-cli" + EXE_SUFFIX
    cutechess_path = testing_dir / cutechess

    # Download cutechess-cli if missing or overwrite if there are issues.
    if not verify_required_cutechess(cutechess_path):
        download_cutechess(cutechess, testing_dir)
    else:
        os.chdir(curr_dir)
        return True

    ret = True

    if not verify_required_cutechess(cutechess_path):
        print(
            "The downloaded cutechess-cli is not working. Trying to restore a backup copy ..."
        )
        bkp_cutechess_clis = sorted(
            worker_dir.glob("_testing_*/" + cutechess),
            key=os.path.getctime,
            reverse=True,
        )
        if bkp_cutechess_clis:
            bkp_cutechess_cli = bkp_cutechess_clis[0]
            try:
                shutil.copy(bkp_cutechess_cli, testing_dir)
            except Exception as e:
                print(
                    "Unable to copy {} to {}. Error: {}".format(
                        bkp_cutechess_cli, testing_dir, str(e)
                    )
                )

            if not verify_required_cutechess(cutechess_path):
                print(
                    "The backup copy {} doesn't work either ...".format(
                        bkp_cutechess_cli
                    )
                )
                print("No suitable cutechess-cli found")
                ret = False
        else:
            print("No backup copy found")
            print("No suitable cutechess-cli found")
            ret = False

    os.chdir(curr_dir)
    return ret


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
                        "Replacing the value '{}' of config option '{}' by '{}'".format(
                            o, v[1], o1
                        )
                    )
                    config.set(v[0], v[1], o1)
                    o = o1
            t = v[3]  # type
            if callable(t):
                try:
                    _ = t(o)
                except:
                    # v[2] is the default
                    print(
                        "The value '{}' of config option '{}' is not of type '{}'.\n"
                        "Replacing it by the default value '{}'".format(
                            o, v[1], v[3].__name__, v[2]
                        )
                    )
                    config.set(*v[:3])
            elif o not in t:  # choices
                print(
                    "The value '{}' of config option '{}' is not in {}.\n"
                    "Replacing it by the default value '{}'".format(o, v[1], v[3], v[2])
                )
                config.set(*v[:3])

    # cleanup
    schema_sections = [v[0] for v in schema]
    schema_options = [v[:2] for v in schema]
    for section in config.sections():
        if section not in schema_sections:
            print("Removing unknown config section '{}'".format(section))
            config.remove_section(section)
            continue
        for option in config.options(section):
            if (section, option) not in schema_options:
                print("Removing unknown config option '{}'".format(option))
                config.remove_option(section, option)


def setup_parameters(worker_dir):
    # Step 1: read the config file if it exists.
    config = ConfigParser(inline_comment_prefixes=";", interpolation=None)
    config_file = worker_dir / CONFIGFILE
    try:
        config.read(config_file)
    except Exception as e:
        print(
            "Exception reading configfile {}:\n".format(config_file),
            e,
            sep="",
            file=sys.stderr,
        )
        print("Initializing configfile")
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
            print("Unknown system")
        with os.popen(cmd) as proc:
            mem_str = str(proc.readlines())
        mem = int(re.search(r"\d+", mem_str).group())
    except Exception as e:
        print("Exception checking HW info:\n", e, sep="", file=sys.stderr)
        return None

    # Step 2b: determine the number of cores.
    max_cpu_count = 0
    try:
        max_cpu_count = multiprocessing.cpu_count()
    except Exception as e:
        print("Exception checking the CPU cores count:\n", e, sep="", file=sys.stderr)
        return None

    # Step 2c: detect the available compilers.
    compilers = detect_compilers()
    if compilers == {}:
        print("No usable compilers found")
        return None

    # Step 3: validate config options and replace missing or invalid
    # ones by defaults.

    compiler_names = list(compilers.keys())
    if "cargo" not in compiler_names:
        default_compiler = compiler_names[0]
    else:
        default_compiler = "cargo"

    schema = [
        # (<section>, <option>, <default>, <type>, <preprocessor>),
        ("login", "username", "", str, None),
        ("login", "password", "", str, None),
        ("parameters", "protocol", "https", ["http", "https"], None),
        ("parameters", "host", "montychess.org", str, None),
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
        help="do not validate username/password with server",
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
        print("Unparsed command line arguments: {}".format(" ".join(args)))
        parser.print_usage()
        return None

    # Step 5: fixup the config options.

    options.concurrency_, options.concurrency = options.concurrency_
    options.max_memory_, options.max_memory = options.max_memory_

    if options.protocol == "http" and options.port == 443:
        # Rewrite old port 443 to 80
        print("Changing port to 80")
        options.port = 80
    elif options.protocol == "https" and options.port == 80:
        # Rewrite old port 80 to 443
        print("Changing port to 443")
        options.port = 443

    # Limit concurrency so that at least STC tests can run with the evailable memory
    # The memory need per engine is 16 for the TT Hash, 10 for the process 138 for the net and 16 per thread
    # 60 is the need for cutechess-cli
    # These numbers need to be up-to-date with the server values
    STC_memory = 2 * (16 + 10 + 138 + 16)
    max_concurrency = int((options.max_memory - 60) / STC_memory)
    if max_concurrency < 1:
        print(
            "You need to reserve at least {} MiB to run the worker!".format(STC_memory)
        )
        return None
    options.concurrency_reduced = False
    if max_concurrency < options.concurrency:
        print(
            "Changing concurrency to allow for running STC tests with the available memory"
        )
        print(
            "The required memory to run with {} concurrency is {} MiB".format(
                options.concurrency, STC_memory * options.concurrency
            )
        )
        print("The concurrency has been reduced to {}".format(max_concurrency))
        print("Consider increasing max_memory if possible")
        options.concurrency = max_concurrency
        options.concurrency_reduced = True

    options.compiler = compilers[options.compiler_]

    options.hw_id = hw_id(config.getint("private", "hw_seed"))
    print("Default uuid_prefix: {}".format(options.hw_id))

    # Step 6: determine credentials.

    username, password = get_credentials(config, options, args)

    if username == "":
        print("Invalid or missing credentials")
        return None

    options.username = username
    options.password = password

    # Step 7: write command line parameters to the config file.
    config.set("login", "username", options.username)
    config.set("login", "password", options.password)
    config.set("parameters", "protocol", options.protocol)
    config.set("parameters", "host", options.host)
    config.set("parameters", "port", str(options.port))
    config.set(
        "parameters",
        "concurrency",
        options.concurrency_
        + " ; = {} cores".format(options.concurrency)
        + (" (reduced)" if options.concurrency_reduced else ""),
    )
    config.set(
        "parameters",
        "max_memory",
        options.max_memory_ + " ; = {} MiB".format(options.max_memory),
    )
    config.set(
        "parameters",
        "uuid_prefix",
        options.uuid_prefix
        + (" ; = {}".format(options.hw_id) if options.uuid_prefix == "_hw" else ""),
    )
    config.set("parameters", "min_threads", str(options.min_threads))
    config.set("parameters", "fleet", str(options.fleet))
    config.set("parameters", "compiler", options.compiler_)

    with open(config_file, "w") as f:
        config.write(f)

    # Step 8: give some feedback to the user.

    print(
        "System memory determined to be: {:.3f}GiB".format(mem / (1024 * 1024 * 1024))
    )
    print(
        "Worker constraints: {{'concurrency': {}, 'max_memory': {}, 'min_threads': {}}}".format(
            options.concurrency, options.max_memory, options.min_threads
        )
    )
    print("Config file {} written".format(config_file))

    return options


def on_sigint(current_state, signal, frame):
    current_state["alive"] = False
    raise FatalException("Terminated by signal {}".format(str_signal(signal)))


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
        # Get windows machine_id from the registry key:
        # HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography\MachineGuid
        # See https://www.medo64.com/2020/04/unique-machine-id/ .
        path = r"SOFTWARE\Microsoft\Cryptography"
        name = "MachineGuid"
        machine_id = read_winreg(path, name)
        if machine_id is not None:
            print(
                "machine_id {} obtained from HKEY_LOCAL_MACHINE\\{}\\{}".format(
                    machine_id, path, name
                )
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
            print(
                "Exception while reading the machine_id:\n",
                e,
                sep="",
                file=sys.stderr,
            )
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
                print("machine_id {} obtained via '{}'".format(machine_id, cmd))
                return machine_id
    elif os.name == "posix":
        host_ids = ["/etc/machine-id", "/var/lib/dbus/machine-id"]
        for file in host_ids:
            try:
                with open(file) as f:
                    machine_id = f.read().strip()
                    print("machine_id {} obtained from {}".format(machine_id, file))
                    return machine_id
            except:
                pass
    print("Unable to obtain the machine id")
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
            "Exception fetching rate_limit (invalid ~/.netrc?):\n",
            e,
            sep="",
            file=sys.stderr,
        )
        return 0


def cargo_version():
    """Parse the output of cargo --version"""
    try:
        with subprocess.Popen(
            ["cargo", "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            for line in iter(p.stdout.readline, ""):
                if "cargo" in line:
                    ver = line.split(' ')[1].split('.')
                    major = ver[0]
                    minor = ver[1]
                    patchlevel = ver[2]
    except (OSError, subprocess.SubprocessError):
        print("No cargo or cargo is not executable")
        return None
    if p.returncode != 0:
        print("cargo version query failed with return code {}".format(p.returncode))
        return None

    try:
        major = int(major)
        minor = int(minor)
        patchlevel = int(patchlevel)
        compiler = "cargo"
    except:
        print("Failed to parse cargo version.")
        return None

    if (major, minor) < (MIN_CARGO_MAJOR, MIN_CARGO_MINOR):
        print(
            "Found cargo version {}.{}.{}. First usable version is {}.{}.0".format(
                major, minor, patchlevel, MIN_CARGO_MAJOR, MIN_CARGO_MINOR
            )
        )
        return None
    print("Found {} version {}.{}.{}".format(compiler, major, minor, patchlevel))
    return (compiler, major, minor, patchlevel)


def detect_compilers():
    ret = {}

    cargo_version_ = cargo_version()
    if cargo_version_ is not None:
        ret["cargo"] = cargo_version_

    return ret


def verify_toolchain():
    cmds = {"strip": ["strip", "-V"], "make": ["make", "-v"]}
    if IS_MACOS:
        # MacOSX apears not to have a method to detect strip
        cmds["strip"] = ["which", "strip"]
    for name, cmd in cmds.items():
        cmd_str = " ".join(cmd)
        ret = True
        try:
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"'{cmd_str}' raised Exception: {type(e).__name__}: {e}")
            ret = False
        if ret and p.returncode != 0:
            print(
                f"Executing '{cmd_str}' failed with return code "
                f"{format_return_code(p.returncode)}. Error: {p.stderr.decode().strip()}"
            )
            ret = False
        if not ret:
            print(f"It appears '{name}' is not properly installed")
            return ret
    return True


def get_exception(files):
    i = 0
    exc_type, exc_obj, tb = sys.exc_info()
    filename, lineno, name, line = traceback.extract_tb(tb)[i]
    filename = Path(filename).name
    message = "Exception {} at {}:{} WorkerVersion: {}".format(
        exc_type.__name__, filename, lineno, WORKER_VERSION
    )
    while filename in files:
        message = "Exception {} at {}:{} WorkerVersion: {}".format(
            exc_type.__name__, filename, lineno, WORKER_VERSION
        )
        i += 1
        try:
            filename, lineno, name, line = traceback.extract_tb(tb)[i]
            filename = Path(filename).name
        except:
            break
    return message


def heartbeat(worker_info, password, remote, current_state):
    print("Start heartbeat")
    payload = {
        "password": password,
        "worker_info": worker_info,
    }
    while current_state["alive"]:
        time.sleep(1)
        now = datetime.now(timezone.utc)
        if current_state["last_updated"] + timedelta(seconds=120) < now:
            print("  Send heartbeat for", worker_info["unique_key"], end=" ... ")
            current_state["last_updated"] = now
            run = current_state["run"]
            payload["run_id"] = str(run["_id"]) if run else None
            task_id = current_state["task_id"]
            payload["task_id"] = task_id
            if payload["run_id"] is None or payload["task_id"] is None:
                print("Skipping heartbeat ...")
                continue
            try:
                req = send_api_post_request(remote + "/api/beat", payload, quiet=True)
            except Exception as e:
                print("Exception calling heartbeat:\n", e, sep="", file=sys.stderr)
            else:
                if "error" not in req:
                    print("(received)")
    else:
        print("Heartbeat stopped")


def read_int(file):
    try:
        return int(file.read_text())
    except:
        return None


def write_int(file, n):
    try:
        file.write_text("{}\n".format(n))
        return True
    except:
        return False


def create_lock_file(lock_file):
    print("Creating lock file {}".format(lock_file))
    atexit.register(delete_lock_file, lock_file)
    return write_int(lock_file, os.getpid())


def delete_lock_file(lock_file):
    pid = read_int(lock_file)
    if pid is None or pid == os.getpid():
        print("Deleting lock file {}".format(lock_file))
        try:
            lock_file.unlink()
        except Exception as e:
            print("Exception deleting the lock file\n", e, sep="", file=sys.stderr)


def pid_valid(pid, name):
    with ExitStack() as stack:
        if IS_WINDOWS:
            cmdlet = (
                "(Get-CimInstance Win32_Process "
                "-Filter 'ProcessId = {}').CommandLine"
            ).format(pid)
            p = stack.enter_context(
                subprocess.Popen(
                    [
                        "powershell",
                        cmdlet,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    universal_newlines=True,
                    bufsize=1,
                    close_fds=not IS_WINDOWS,
                )
            )
        else:
            p = stack.enter_context(
                subprocess.Popen(
                    # for busybox these options are undocumented...
                    ["ps", "-f", "-a"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    universal_newlines=True,
                    bufsize=1,
                    close_fds=not IS_WINDOWS,
                )
            )
        for line in iter(p.stdout.readline, ""):
            if name in line and str(pid) in line:
                return True
    return False


def locked_by_others(lock_file, require_valid=True):
    # At the start of the worker we tolerate an
    # invalid or non existing lock file since we
    # intend to replace it with one of our own.
    # Once we have started, we only accept a
    # valid lock file containing our own PID.
    pid = read_int(lock_file)
    if pid is None:
        if require_valid:
            print(
                "\n*** Worker (PID={}) stopped! ***\n"
                "Unable to read the lock file:\n{}.".format(os.getpid(), lock_file)
            )
        return require_valid
    if pid != os.getpid() and (require_valid or pid_valid(pid, "worker.py")):
        print(
            "\n*** Worker (PID={}) stopped! ***\n"
            "Another worker (PID={}) is already running in this directory, "
            "using the lock file:\n{}".format(os.getpid(), pid, lock_file)
        )
        return True
    return False


def utcoffset():
    dst = time.localtime().tm_isdst == 1 and time.daylight != 0
    utcoffset = -time.altzone if dst else -time.timezone
    abs_utcoffset_min = abs(utcoffset // 60)
    hh, mm = divmod(abs_utcoffset_min, 60)
    return "{}{:02d}:{:02d}".format("+" if utcoffset >= 0 else "-", hh, mm)


def verify_worker_version(remote, username, password):
    # Returns:
    # True: we are the right version and have the correct credentials
    # False: incorrect credentials (the user may have been blocked in the meantime)
    # None: network error: unable to verify
    # We don't return if the server informs us that a newer version of the worker
    # is available
    print("Verify worker version...")
    payload = {"worker_info": {"username": username}, "password": password}
    try:
        req = send_api_post_request(remote + "/api/request_version", payload)
    except WorkerException:
        return None  # the error message has already been written
    if "error" in req:
        return False  # likewise
    if req["version"] > WORKER_VERSION:
        print("Updating worker version to {}".format(req["version"]))
        backup_log()
        try:
            update()
        except Exception as e:
            print(
                "Exception while updating to version {}:\n".format(req["version"]),
                e,
                sep="",
                file=sys.stderr,
            )
        print("Attempted update to worker version {} failed!".format(req["version"]))
        return False
    return True


def fetch_and_handle_task(
    worker_info, password, remote, lock_file, current_state, clear_binaries
):
    # This function should normally not raise exceptions.
    # Unusual conditions are handled by returning False.
    # If an immediate exit is necessary then one can set
    # current_state["alive"] to False.

    # The following check can be triggered theoretically
    # but probably not in practice.
    if locked_by_others(lock_file):
        current_state["alive"] = False
        return False

    # Print the current time for log purposes
    print(
        "Current time is {} UTC (local offset: {}) ".format(
            datetime.now(timezone.utc), utcoffset()
        )
    )

    # Check the worker version and upgrade if necessary
    ret = verify_worker_version(remote, worker_info["username"], password)
    if ret is False:
        current_state["alive"] = False
    if not ret:
        return False

    # Verify if we still have enough GitHub api calls
    remaining = get_remaining_github_api_calls()
    print("Remaining number of GitHub api calls = {}".format(remaining))
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
    payload = {"worker_info": worker_info, "password": password}
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

    print(
        "Working on task {} from {}/tests/view/{}".format(task_id, remote, run["_id"])
    )
    if "sprt" in run["args"]:
        type = "sprt"
    elif "spsa" in run["args"]:
        type = "spsa"
    else:
        type = "num_games"
    log(
        "run: {} task: {} size: {} tc: {} concurrency: {} threads: {} [ {} : {} ]".format(
            run["_id"],
            task_id,
            run["my_task"]["num_games"],
            run["args"]["tc"],
            worker_info["concurrency"],
            run["args"]["threads"],
            type,
            run["args"]["num_games"],
        )
    )
    print("Running {} vs {}".format(run["args"]["new_tag"], run["args"]["base_tag"]))

    success = False
    message = ""
    server_message = ""
    api = remote + "/api/failed_task"
    pgn_file = [None]
    try:
        run_games(
            worker_info,
            current_state,
            password,
            remote,
            run,
            task_id,
            pgn_file,
            clear_binaries,
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
        message = "{} ({})".format(server_message, str(e))
        current_state["alive"] = False

    current_state["task_id"] = None
    current_state["run"] = None

    payload = {
        "password": password,
        "run_id": str(run["_id"]),
        "task_id": task_id,
        "message": server_message,
        "worker_info": worker_info,
    }

    if not success:
        print("\nException running games:\n", message, sep="", file=sys.stderr)
        print("Informing the server")
        try:
            req = send_api_post_request(api, payload)
        except Exception as e:
            print("Exception posting failed_task:\n", e, sep="", file=sys.stderr)
    # Upload PGN file.
    if pgn_file[0] is not None:
        pgn_file = pgn_file[0]
        if pgn_file.exists():
            if "spsa" not in run["args"]:
                try:
                    # Ignore non utf-8 characters in PGN file.
                    data = pgn_file.read_text(encoding="utf-8", errors="ignore")
                    with io.BytesIO() as gz_buffer:
                        with gzip.GzipFile(
                            filename=f"{str(run['_id'])}-{task_id}.pgn.gz",
                            mode="wb",
                            fileobj=gz_buffer,
                        ) as gz:
                            gz.write(data.encode())
                        payload["pgn"] = base64.b64encode(gz_buffer.getvalue()).decode()
                    print(
                        "Uploading compressed PGN of {} bytes".format(
                            len(payload["pgn"])
                        )
                    )
                    req = send_api_post_request(remote + "/api/upload_pgn", payload)
                except Exception as e:
                    print(
                        "\nException uploading PGN file:\n", e, sep="", file=sys.stderr
                    )

            try:
                pgn_file.unlink()
            except Exception as e:
                print("Exception deleting PGN file:\n", e, sep="", file=sys.stderr)

    print("Task exited")

    return success


def worker():
    if Path(__file__).name != "worker.py":
        print("The script must be named 'worker.py'!")
        return 1

    print(LOGO)

    worker_dir = Path(__file__).resolve().parent
    print("Worker started in {} ... (PID={})".format(worker_dir, os.getpid()))

    # Python doesn't have a cross platform file locking api.
    # So we check periodically for the existence
    # of a lock file.
    lock_file = worker_dir / "worker.lock"
    if locked_by_others(lock_file, require_valid=False):
        return 1
    if not create_lock_file(lock_file):
        print("Creating lock file failed")
        return 1
    # The start of the worker is racy so after a small
    # delay we check that we still have a valid
    # lock file containing our own PID.
    # This will stop duplicate workers right here,
    # except on extremely slow systems.
    time.sleep(0.5)
    if locked_by_others(lock_file):
        return 1

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
    except:
        # Windows does not have SIGQUIT.
        pass
    try:
        signal.signal(signal.SIGBREAK, partial(on_sigint, current_state))
    except:
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

    remote = "{}://{}:{}".format(options.protocol, options.host, options.port)

    # Check the worker version and upgrade if necessary
    try:
        if verify_worker_version(remote, options.username, options.password) is False:
            return 1
    except Exception as e:
        print("Exception verifying worker version:\n", e, sep="", file=sys.stderr)
        return 1

    # Check for common tool chain issues
    if not verify_toolchain():
        return 1

    # Make sure we have a working cutechess-cli
    if not setup_cutechess(worker_dir):
        return 1

    # Check if we are running an unmodified worker
    unmodified = verify_remote_sri(worker_dir)
    if unmodified is None:
        return 1

    # Assemble the config/options data as well as some other data in a
    # "worker_info" dictionary.
    # This data will be sent to the server when a new task is requested.

    compiler, major, minor, patchlevel = options.compiler
    print("Using {} {}.{}.{}".format(compiler, major, minor, patchlevel))

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
        "cargo_version": (
            major,
            minor,
            patchlevel,
        ),
        "compiler": compiler,
        "unique_key": get_uuid(options),
        "modified": not unmodified,
        "ARCH": "?",
        "nps": 0.0,
    }

    print("UUID:", worker_info["unique_key"])

    # Start heartbeat thread as a daemon (not strictly necessary, but there might be bugs)
    heartbeat_thread = threading.Thread(
        target=heartbeat,
        args=(worker_info, options.password, remote, current_state),
        daemon=True,
    )
    heartbeat_thread.start()

    # If fleet==True then the worker will quit if it is unable to obtain
    # or execute a task. If fleet==False then the worker will go to the
    # next iteration of the main loop.
    # The reason for the existence of this parameter is that it allows
    # a fleet of workers to quickly quit as soon as the queue is empty
    # or the server down.

    # Start the main loop.
    delay = INITIAL_RETRY_TIME
    fish_exit = False
    clear_binaries = True
    while current_state["alive"]:
        if (worker_dir / "fish.exit").is_file():
            current_state["alive"] = False
            print("Stopped by 'fish.exit' file")
            fish_exit = True
            break
        success = fetch_and_handle_task(
            worker_info,
            options.password,
            remote,
            lock_file,
            current_state,
            clear_binaries,
        )
        if not current_state["alive"]:  # the user may have pressed Ctrl-C...
            break
        elif not success:
            if options.fleet:
                current_state["alive"] = False
                print("Exiting the worker since fleet==True and an error occurred")
                break
            else:
                print("Waiting {} seconds before retrying".format(delay))
                safe_sleep(delay)
                delay = min(MAX_RETRY_TIME, delay * 2)
        else:
            clear_binaries = False
            delay = INITIAL_RETRY_TIME

    if fish_exit:
        (worker_dir / "fish.exit").unlink()

    print("Waiting for the heartbeat thread to finish...")
    heartbeat_thread.join(THREAD_JOIN_TIMEOUT)

    return 0 if fish_exit else 1


if __name__ == "__main__":
    sys.exit(worker())
