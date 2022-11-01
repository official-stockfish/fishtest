#!/usr/bin/env python3
import atexit
import base64
import datetime
import getpass
import glob
import hashlib
import json
import math
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
import zlib
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from configparser import ConfigParser
from contextlib import ExitStack
from functools import partial
from zipfile import ZipFile

# Try to import the system wide package (eg requests).
# Fall back to the local one if the global one does not exist.

packages_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "packages")
sys.path.append(packages_dir)

# Several packages are called "expression".
# So we make sure to use the locally installed one.

import packages.expression as expression
import requests
from games import (
    EXE_SUFFIX,
    FatalException,
    RunException,
    WorkerException,
    backup_log,
    download_from_github,
    format_return_code,
    log,
    requests_get,
    run_games,
    send_api_post_request,
    str_signal,
)
from updater import update

WORKER_VERSION = 181
FILE_LIST = ["updater.py", "worker.py", "games.py"]
SRI_URL = "https://raw.githubusercontent.com/glinscott/fishtest/master/worker/sri.txt"
HTTP_TIMEOUT = 30.0
INITIAL_RETRY_TIME = 15.0
THREAD_JOIN_TIMEOUT = 15.0
MAX_RETRY_TIME = 900.0  # 15 minutes
IS_WINDOWS = "windows" in platform.system().lower()
IS_MACOS = "darwin" in platform.system().lower()
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

<fishtest>     = https://tests.stockfishchess.org
<github>       = https://api.github.com
<github-books> = <github>/repos/official-stockfish/books

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
    with open(file) as f:  # text mode to have newline translation!
        return base64.b64encode(
            hashlib.sha384(f.read().encode("utf8")).digest()
        ).decode("utf8")


def generate_sri(install_dir):
    sri = {
        "__version": WORKER_VERSION,
    }
    for file in FILE_LIST:
        item = os.path.join(install_dir, file)
        sri[file] = text_hash(item)
    return sri


def write_sri(install_dir):
    sri = generate_sri(install_dir)
    sri_file = os.path.join(install_dir, "sri.txt")
    print("Writing sri hashes to {}".format(sri_file))
    with open(sri_file, "w") as f:
        json.dump(sri, f)
        f.write("\n")


def verify_sri(install_dir):  # used by CI
    sri = generate_sri(install_dir)
    sri_file = os.path.join(install_dir, "sri.txt")
    if not os.path.exists(sri_file):
        print("{} does not exist".format(sri_file))
        return False
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
        if k not in sri_ or v != sri_[k]:
            print("The value for {} is incorrect in {}".format(k, sri_file))
            return False
    print("The file {} is up to date!".format(sri_file))
    return True


def download_sri():
    print("Downloading {}".format(SRI_URL))
    try:
        ret = requests_get(SRI_URL).json()
    except:
        print("Unable to download {}".format(SRI_URL))
        return None
    return ret


def verify_remote_sri(install_dir):
    # Returns:
    # None in case of network error
    # True if verification succeeded
    # False if verification failed
    sri = generate_sri(install_dir)
    sri_ = download_sri()
    if sri_ is None:
        return None
    version = sri_.get("__version", -1)
    if version > WORKER_VERSION:
        print("The master sri file has a later version. Ignoring!")
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


def verify_required_cutechess(testing_dir, cutechess):
    # Verify that cutechess is working and has the required minimum version.
    cutechess = os.path.join(testing_dir, cutechess)

    print("Obtaining version info for {} ...".format(cutechess))

    if not os.path.exists(cutechess):
        print("{} does not exist ...".format(cutechess))
        return False

    try:
        with subprocess.Popen(
            [cutechess, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            errors = p.stderr.read()
            pattern = re.compile("cutechess-cli ([0-9]*).([0-9]*).([0-9]*)")
            major, minor, patch = 0, 0, 0
            for line in iter(p.stdout.readline, ""):
                m = pattern.search(line)
                if m:
                    print("Found: ", line.strip())
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


def setup_cutechess():
    # Create the testing directory if missing.
    worker_dir = os.path.dirname(os.path.realpath(__file__))
    testing_dir = os.path.join(worker_dir, "testing")
    if not os.path.exists(testing_dir):
        os.makedirs(testing_dir)

    try:
        os.chdir(testing_dir)
    except Exception as e:
        print("Unable to enter {}. Error: {}".format(testing_dir, str(e)))
        return False

    cutechess = "cutechess-cli" + EXE_SUFFIX

    if not verify_required_cutechess(testing_dir, cutechess):
        if len(EXE_SUFFIX) > 0:
            zipball = "cutechess-cli-win.zip"
        elif IS_MACOS:
            zipball = "cutechess-cli-macos-64bit.zip"
        else:
            zipball = "cutechess-cli-linux-{}.zip".format(platform.architecture()[0])
        try:
            download_from_github(zipball, testing_dir)
            with ZipFile(zipball) as zip_file:
                zip_file.extractall()
            os.remove(zipball)
            os.chmod(cutechess, os.stat(cutechess).st_mode | stat.S_IEXEC)
        except Exception as e:
            print(
                "Exception downloading or extracting {}:\n".format(zipball),
                e,
                sep="",
                file=sys.stderr,
            )

        if not verify_required_cutechess(testing_dir, cutechess):
            print(
                "The downloaded cutechess-cli is not working. Trying to restore a backup copy ..."
            )
            bkp_cutechess_clis = sorted(
                glob.glob(os.path.join(worker_dir, "_testing_*", cutechess)),
                key=os.path.getctime,
            )
            if bkp_cutechess_clis:
                bkp_cutechess_cli = bkp_cutechess_clis[-1]
                try:
                    shutil.copy(bkp_cutechess_cli, testing_dir)
                except Exception as e:
                    print(
                        "Unable to copy {} to {}. Error: {}".format(
                            bkp_cutechess_cli, testing_dir, str(e)
                        )
                    )

                if not verify_required_cutechess(testing_dir, cutechess):
                    print(
                        "The backup copy {} doesn't work either ...".format(
                            bkp_cutechess_cli
                        )
                    )
                    print("No suitable cutechess-cli found")
                    return False
            else:
                print("No backup copy found")
                print("No suitable cutechess-cli found")
                return False

    return True


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
    config_file = os.path.join(worker_dir, CONFIGFILE)
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
    if "g++" not in compiler_names:
        default_compiler = compiler_names[0]
    else:
        default_compiler = "g++"

    schema = [
        # (<section>, <option>, <default>, <type>, <preprocessor>),
        ("login", "username", "", str, None),
        ("login", "password", "", str, None),
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

    options.compiler = compilers[options.compiler_]

    options.hw_id = hw_id(config.getint("private", "hw_seed"))
    print("Default uuid_prefix: {}".format(options.hw_id))

    # Step 6: determine credentials

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
        options.concurrency_ + " ; = {} cores".format(options.concurrency),
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
    fingerprint_path = fingerprint(os.path.realpath(__file__))
    return format(hw_seed ^ fingerprint_machine ^ fingerprint_path, "08x")


def get_uuid(options):
    if options.uuid_prefix == "_hw":
        uuid_prefix = options.hw_id
    else:
        uuid_prefix = options.uuid_prefix

    return uuid_prefix[:8] + str(uuid.uuid4())[8:]


def get_rate():
    try:
        rate = requests.get(
            "https://api.github.com/rate_limit", timeout=HTTP_TIMEOUT
        ).json()["resources"]["core"]
    except Exception as e:
        print("Exception fetching rate_limit:\n", e, sep="", file=sys.stderr)
        rate = {"remaining": 0, "limit": 5000}
        return rate, False
    remaining = rate["remaining"]
    print("API call rate limits:", rate)
    return rate, remaining < math.sqrt(rate["limit"])


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
                    print("clang++ poses as g++")
                    return None
                if "__GNUC__" in line:
                    major = line.split()[2]
                if "__GNUC_MINOR__" in line:
                    minor = line.split()[2]
                if "__GNUC_PATCHLEVEL__" in line:
                    patchlevel = line.split()[2]
    except (OSError, subprocess.SubprocessError):
        print("No g++ or g++ is not executable")
        return None
    if p.returncode != 0:
        print("g++ version query failed with return code {}".format(p.returncode))
        return None

    try:
        major = int(major)
        minor = int(minor)
        patchlevel = int(patchlevel)
        compiler = "g++"
    except:
        print("Failed to parse g++ version.")
        return None

    if (major, minor) < (7, 3):
        print(
            "Found g++ version {}.{}.{}. First usable version is 7.3.0.".format(
                major, minor, patchlevel
            )
        )
        return None
    print("Found {} version {}.{}.{}".format(compiler, major, minor, patchlevel))
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
        print("No clang++ or clang++ is not executable")
        return None
    if p.returncode != 0:
        print("clang++ version query failed with return code {}".format(p.returncode))
        return None

    try:
        major = int(clang_major)
        minor = int(clang_minor)
        patchlevel = int(clang_patchlevel)
        compiler = "clang++"
    except:
        print("Failed to parse clang++ version.")
        return None

    print("Found {} version {}.{}.{}".format(compiler, major, minor, patchlevel))
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


def get_exception(files):
    i = 0
    exc_type, exc_obj, tb = sys.exc_info()
    filename, lineno, name, line = traceback.extract_tb(tb)[i]
    message = "Exception {} at {}:{}".format(
        exc_type.__name__, os.path.basename(filename), lineno
    )
    while os.path.basename(filename) in files:
        message = "Exception {} at {}:{}".format(
            exc_type.__name__, os.path.basename(filename), lineno
        )
        i += 1
        try:
            filename, lineno, name, line = traceback.extract_tb(tb)[i]
        except:
            break
    return message


def heartbeat(worker_info, password, remote, current_state):
    print("Start heartbeat")
    payload = {
        "password": password,
        "worker_info": worker_info,
    }
    count = 0
    while current_state["alive"]:
        time.sleep(1)
        count += 1
        if count == 60:
            count = 0
            print("  Send heartbeat for", worker_info["unique_key"], end=" ... ")
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
        with open(file, "r") as f:
            return int(f.read())
    except:
        return None


def write_int(file, n):
    try:
        with open(file, "w") as f:
            f.write("{}\n".format(n))
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
            os.remove(lock_file)
        except:
            print("Unable to delete lock file")


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
    print("Verify worker version...")
    payload = {"worker_info": {"username": username}, "password": password}
    req = send_api_post_request(remote + "/api/request_version", payload)
    if "error" in req:
        return False
    if req["version"] > WORKER_VERSION:
        print("Updating worker version to {}".format(req["version"]))
        backup_log()
        update()
    return True


def fetch_and_handle_task(worker_info, password, remote, lock_file, current_state):
    # This function should normally not raise exceptions.
    # Unusual conditions are handled by returning False.
    # If an immediate exit is necessary then one can set
    # current_state["alive"] to False.

    # The following check can be triggered theoretically
    # but probably not in practice.
    if locked_by_others(lock_file):
        current_state["alive"] = False
        return False

    try:
        rate, near_api_limit = get_rate()
        if near_api_limit:
            print("Near API limit")
            return False

        worker_info["rate"] = rate

        if not verify_worker_version(remote, worker_info["username"], password):
            current_state["alive"] = False
            return False

        print(
            "Current time is {} UTC (offset: {}) ".format(
                datetime.datetime.utcnow(), utcoffset()
            )
        )
        print("Fetching task...")
        payload = {"worker_info": worker_info, "password": password}
        req = send_api_post_request(remote + "/api/request_task", payload)
    except Exception as e:
        print("Exception accessing host:\n", e, sep="", file=sys.stderr)
        return False

    if "error" in req:
        return False

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
        run_games(worker_info, password, remote, run, task_id, pgn_file)
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
    pgn_file = pgn_file[0]
    if pgn_file is not None and os.path.exists(pgn_file) and "spsa" not in run["args"]:
        try:
            with open(pgn_file, "r") as f:
                data = f.read()
            # Ignore non utf-8 characters in PGN file.
            data = bytes(data, "utf-8").decode("utf-8", "ignore")
            payload["pgn"] = base64.b64encode(
                zlib.compress(data.encode("utf-8"))
            ).decode()
            print("Uploading compressed PGN of {} bytes".format(len(payload["pgn"])))
            req = send_api_post_request(remote + "/api/upload_pgn", payload)
        except Exception as e:
            print("\nException uploading PGN file:\n", e, sep="", file=sys.stderr)

    if pgn_file is not None and os.path.exists(pgn_file):
        try:
            os.remove(pgn_file)
        except Exception as e:
            print("Exception deleting PGN file:\n", e, sep="", file=sys.stderr)

    print("Task exited")

    return success


def worker():
    if os.path.basename(__file__) != "worker.py":
        print("The script must be named 'worker.py'!")
        return 1

    print(LOGO)

    worker_dir = os.path.dirname(os.path.realpath(__file__))
    print("Worker started in {} ... (PID={})".format(worker_dir, os.getpid()))

    # Python doesn't have a cross platform file locking api.
    # So we check periodically for the existence
    # of a lock file.
    lock_file = os.path.join(worker_dir, "worker.lock")
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
        "alive": True,  # controls the main loop and
        # the heartbeat loop
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
        if not verify_worker_version(remote, options.username, options.password):
            return 1
    except Exception as e:
        print("Exception verifying worker version:\n", e, sep="", file=sys.stderr)
        return 1

    # Make sure we have a working cutechess-cli
    if not setup_cutechess():
        return 1

    # Check if we are running an unmodified worker
    un_modified = verify_remote_sri(worker_dir)
    if un_modified is None:
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
        "gcc_version": (
            major,
            minor,
            patchlevel,
        ),
        "compiler": compiler,
        "unique_key": get_uuid(options),
        "modified": not un_modified,
        "ARCH": "?",
        "nps": 0.0,
    }

    print("UUID:", worker_info["unique_key"])
    with open(os.path.join(worker_dir, "uuid.txt"), "w") as f:
        f.write(worker_info["unique_key"])

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
    while current_state["alive"]:
        if os.path.isfile(os.path.join(worker_dir, "fish.exit")):
            current_state["alive"] = False
            print("Stopped by 'fish.exit' file")
            fish_exit = True
            break
        success = fetch_and_handle_task(
            worker_info, options.password, remote, lock_file, current_state
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
            delay = INITIAL_RETRY_TIME

    print("Waiting for the heartbeat thread to finish...")
    heartbeat_thread.join(THREAD_JOIN_TIMEOUT)

    return 0 if fish_exit else 1


if __name__ == "__main__":
    sys.exit(worker())
