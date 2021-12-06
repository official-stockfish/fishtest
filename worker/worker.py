#!/usr/bin/env python3
import atexit
import base64
import getpass
import math
import multiprocessing
import os
import platform
import random
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zlib
from configparser import ConfigParser, NoOptionError, NoSectionError
from contextlib import ExitStack
from datetime import datetime
from functools import partial
from argparse import ArgumentParser

# Try to import an user installed package,
# fall back to the local one in case of error.
try:
    import requests
except ImportError:
    sys.path.append(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "packages")
    )
    import requests

from games import (
    FatalException,
    RunException,
    WorkerException,
    run_games,
    send_api_post_request,
    str_signal,
)
from updater import update

WORKER_VERSION = 137
HTTP_TIMEOUT = 15.0
MAX_RETRY_TIME = 14400.0  # four hours
IS_WINDOWS = "windows" in platform.system().lower()
CONFIGFILE = "fishtest.cfg"

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


def safe_sleep(f):
    try:
        time.sleep(f)
    except:
        print("\nSleep interrupted...")


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
            req = send_api_post_request(remote + "/api/request_version", payload)
        except:
            return None  # network problem (unrecoverable)
        if "error" in req:
            return False  # invalid username/password
    else:
        return False  # empty username or password
    print("Credentials ok!")
    return True


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
    if not options.validate:
        return username, password

    ret = verify_credentials(remote, username, password, cached)
    if ret is None:
        return "", ""
    elif not ret:
        try:
            username = input("Username: ")
            if username != "":
                password = getpass.getpass()
        except:
            print("")
            return "", ""
        else:
            if not verify_credentials(remote, username, password, False):
                return "", ""

    return username, password


def setup_parameters(worker_dir):

    # Step 1: read the config file if it exists.
    config = ConfigParser()
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
        config = ConfigParser()

    # Step 2: replace missing config options by defaults.
    mem = 0
    system_type = platform.system().lower()
    try:
        if "linux" in system_type:
            cmd = "free -b"
        elif "windows" in system_type:
            cmd = "wmic computersystem get TotalPhysicalMemory"
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

    max_cpu_count = 0
    try:
        max_cpu_count = multiprocessing.cpu_count()
    except Exception as e:
        print("Exception checking the CPU cores count:\n", e, sep="", file=sys.stderr)

    default_cpu_count = min(3, max(1, max_cpu_count - 1))
    cpu_count = default_cpu_count

    try:
        if config.getboolean("parameters", "use_all_cores"):
            try:
                _ = config.get("parameters", "concurrency")
            except (NoOptionError, NoSectionError):
                cpu_count = max_cpu_count
    except (NoOptionError, NoSectionError, ValueError):
        pass

    defaults = [
        ("login", "username", "", str),
        ("login", "password", "", str),
        ("parameters", "protocol", "https", ["http", "https"]),
        ("parameters", "host", "tests.stockfishchess.org", str),
        ("parameters", "port", "443", int),
        ("parameters", "concurrency", str(cpu_count), int),
        ("parameters", "max_memory", str(int(mem / 2 / 1024 / 1024)), int),
        ("parameters", "min_threads", "1", int),
        ("parameters", "fleet", "False", _bool),
        ("parameters", "use_all_cores", "False", _bool),
    ]

    for v in defaults:
        if not config.has_section(v[0]):
            config.add_section(v[0])
        if not config.has_option(v[0], v[1]):
            config.set(*v[:3])
        else:
            o = config.get(v[0], v[1])
            t = v[3]
            if callable(t):
                try:
                    _ = t(o)
                except:
                    print(
                        "The value '{}' of config option '{}' is not of type {}.\n"
                        "Replacing it by the default value {}".format(
                            o, v[1], v[3].__name__, v[2]
                        )
                    )
                    config.set(*v[:3])
            elif o not in t:
                print(
                    "The value '{}' of config option '{}' is not in {}.\n"
                    "Replacing it by the default value {}".format(o, v[1], v[3], v[2])
                )
                config.set(*v[:3])

    # Step 3: parse the command line. Use the current config options mostly as defaults.

    parser = ArgumentParser(
        description="usage (long version):" " worker.py USERNAME PASSWORD [OPTIONS]",
        usage="python worker.py [USERNAME PASSWORD] [OPTIONS]",
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
        dest="concurrency",
        type=int,
        help="the maximum amount of cores that the worker will use",
    )
    parser.add_argument(
        "-m",
        "--max_memory",
        dest="max_memory",
        default=config.getint("parameters", "max_memory"),
        type=int,
        help="the maximum amount of memory (in MiB) that the worker will use",
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
        help="quit in case of errors or if no task is available",
    )
    parser.add_argument(
        "-a",
        "--use_all_cores",
        dest="use_all_cores",
        type=_bool,
        choices=[False, True],
        help="allow the worker to use all cores",
    )
    parser.add_argument(
        "-w",
        "--only_config",
        dest="only_config",
        default=False,
        type=_bool,
        choices=[False, True],
        help="just write the configfile and quit",
    )
    parser.add_argument(
        "-v",
        "--validate",
        dest="validate",
        default=True,
        type=_bool,
        choices=[False, True],
        help="validate username/password with server",
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
        parser.print_usage()
        return None

    # Step 4: fix inconsistencies in the config options.
    if options.protocol == "http" and options.port == 443:
        # Rewrite old port 443 to 80
        print("Changing port to 80")
        options.port = 80
    elif options.protocol == "https" and options.port == 80:
        # Rewrite old port 80 to 443
        print("Changing port to 443")
        options.port = 443

    # "--use_all_cores True" (1) allows the use of all cores;
    # (2) makes the default concurrency equal to the number of
    # cores.
    # The default can be overridden by supplying an explicit
    # "--concurrency" option.

    # "--use_all_cores False" disallows the use of all cores.

    # When using --use_all_cores False when --use_all_cores True
    # is in effect, we reset concurrency to the default
    # value.

    # We first want to look at the option --use_all_cores on
    # the command line, before replacing it by the value from
    # the config file.
    if (
        options.use_all_cores is not None
        and options.use_all_cores
        and options.concurrency is None
    ):
        options.concurrency = max_cpu_count
    if (
        options.use_all_cores is not None
        and not options.use_all_cores
        and options.concurrency is None
        and config.getint("parameters", "concurrency") >= max_cpu_count
    ):
        print("Resetting concurrency to the default value {}".format(default_cpu_count))
        options.concurrency = default_cpu_count
    if options.use_all_cores is None:
        options.use_all_cores = config.getboolean("parameters", "use_all_cores")
    if options.concurrency is None:
        options.concurrency = config.getint("parameters", "concurrency")

    if options.concurrency > max_cpu_count or (
        not options.use_all_cores and options.concurrency >= max_cpu_count
    ):
        print(
            (
                "\nYou cannot have concurrency {} but at most:\n"
                "  a) {} with '--use_all_cores True';\n"
                "  b) {} otherwise.\n"
                "Please use option a) only if your computer is very lightly loaded.\n"
            ).format(
                options.concurrency,
                max_cpu_count,
                max_cpu_count - 1,
            )
        )
        return None

    if options.concurrency <= 0:
        print("Not enough CPUs to run fishtest: set '--concurrency' to at least one")
        return None

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
    if options.concurrency != max_cpu_count:
        config.set("parameters", "concurrency", str(options.concurrency))
    else:
        assert options.use_all_cores
        config.remove_option("parameters", "concurrency")
    config.set("parameters", "max_memory", str(options.max_memory))
    config.set("parameters", "min_threads", str(options.min_threads))
    config.set("parameters", "fleet", str(options.fleet))
    config.set("parameters", "use_all_cores", str(options.use_all_cores))

    with open(config_file, "w") as f:
        config.write(f)

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
    raise WorkerException("Terminated by signal {}".format(str_signal(signal)))


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
    with subprocess.Popen(
        ["g++", "-E", "-dM", "-"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    ) as p:
        for line in iter(p.stdout.readline, ""):
            if "__GNUC__" in line:
                major = line.split()[2]
            if "__GNUC_MINOR__" in line:
                minor = line.split()[2]
            if "__GNUC_PATCHLEVEL__" in line:
                patchlevel = line.split()[2]

    if p.returncode != 0:
        print("g++ version query failed with return code {}".format(p.returncode))
        return None

    try:
        major = int(major)
        minor = int(minor)
        patchlevel = int(patchlevel)
    except:
        print("Failed to parse g++ version.")
        return None

    print("Found g++ version {}.{}.{}".format(major, minor, patchlevel))
    return (major, minor, patchlevel)


def get_exception(files):
    i = 0
    exc_type, exc_obj, tb = sys.exc_info()
    filename, lineno, name, line = traceback.extract_tb(tb)[i]
    message = "Exception at {}:{}".format(os.path.basename(filename), lineno)
    while os.path.basename(filename) in files:
        message = "Exception at {}:{}".format(os.path.basename(filename), lineno)
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
                req = send_api_post_request(remote + "/api/beat", payload)
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
            p = stack.enter_context(
                subprocess.Popen(
                    [
                        "wmic",
                        "path",
                        "Win32_Process",
                        "where",
                        "handle={}".format(pid),
                        "get",
                        "commandline",
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
                    ["ps", "-f", "-p", str(pid)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    universal_newlines=True,
                    bufsize=1,
                    close_fds=not IS_WINDOWS,
                )
            )
        for line in iter(p.stdout.readline, ""):
            if name in line:
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

    payload = {"worker_info": worker_info, "password": password}

    try:
        rate, near_api_limit = get_rate()
        if near_api_limit:
            print("Near API limit")
            return False

        worker_info["rate"] = rate

        t0 = datetime.utcnow()

        print("Verify worker version...")
        req = send_api_post_request(remote + "/api/request_version", payload)

        if "error" in req:
            current_state["alive"] = False
            return False

        if req["version"] > WORKER_VERSION:
            print("Updating worker version to {}".format(req["version"]))
            update()
        print(
            "Worker version checked successfully in {}s".format(
                (datetime.utcnow() - t0).total_seconds()
            )
        )

        t0 = datetime.utcnow()
        print("Fetch task...")
        req = send_api_post_request(remote + "/api/request_task", payload)
    except Exception as e:
        print("Exception accessing host:\n", e, sep="", file=sys.stderr)
        return False

    print("Task requested in {}s".format((datetime.utcnow() - t0).total_seconds()))
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

        # The delay below is mainly to help with finished SPRT runs.
        # In that case many tasks may potentially finish at the same time.
        if success:
            sleep = random.randint(1, 10)
            print("Wait {} seconds before uploading PGN...".format(sleep))
            safe_sleep(sleep)

        print("Uploading PGN...")

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
    if options.only_config:
        return 0

    # Make sure a suitable version of gcc is present.
    gcc_version_ = gcc_version()
    if gcc_version_ is None:
        return 1
    major, minor, patchlevel = gcc_version_
    if (major, minor) < (7, 3):
        print(
            "Found g++ version {}.{}. Please update to g++ version 7.3 or later".format(
                major, minor
            )
        )
        return 1

    # Assemble the config/options data as well as some other data in a
    # "worker_info" dictionary.
    # This data will be sent to the server when a new task is requested.
    uname = platform.uname()
    worker_info = {
        "uname": uname[0] + " " + uname[2],
        "architecture": platform.architecture(),
        "concurrency": options.concurrency,
        "max_memory": options.max_memory,
        "min_threads": options.min_threads,
        "username": options.username,
        "version": "{}:{}.{}.{}".format(
            WORKER_VERSION,
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        ),
        "gcc_version": "{}.{}.{}".format(major, minor, patchlevel),
        "unique_key": str(uuid.uuid4()),
    }

    print("UUID:", worker_info["unique_key"])
    with open(os.path.join(worker_dir, "uuid.txt"), "w") as f:
        f.write(worker_info["unique_key"])

    # All seems to be well...
    remote = "{}://{}:{}".format(options.protocol, options.host, options.port)

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
    delay = HTTP_TIMEOUT
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
            delay = HTTP_TIMEOUT

    print("Waiting for the heartbeat thread to finish...")
    heartbeat_thread.join(HTTP_TIMEOUT)

    return 0 if fish_exit else 1


if __name__ == "__main__":
    sys.exit(worker())
