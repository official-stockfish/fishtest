#!/usr/bin/env python3
import atexit
import base64
import json
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
from configparser import ConfigParser
from contextlib import ExitStack
from datetime import datetime
from functools import partial
from optparse import OptionParser
from os import path

# Try to import an user installed package,
# fall back to the local one in case of error.
try:
    import requests
except ImportError:
    sys.path.append(path.join(path.dirname(path.realpath(__file__)), "packages"))
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

WORKER_VERSION = 136
HTTP_TIMEOUT = 15.0
MAX_RETRY_TIME = 14400.0  # four hours
IS_WINDOWS = "windows" in platform.system().lower()

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


def safe_sleep(f):
    try:
        time.sleep(f)
    except:
        print("\nSleep interrupted...")


def setup_parameters(config_file):

    # Step 1: read the config file if it exists.
    config = ConfigParser()
    config.read(config_file)

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
        print("Memory: " + str(mem))
    except Exception as e:
        print("Exception checking HW info:\n", e, sep="", file=sys.stderr)
        return None

    cpu_count = min(3, max(1, multiprocessing.cpu_count() - 1))

    defaults = [
        ("login", "username", ""),
        ("login", "password", ""),
        ("parameters", "protocol", "https"),
        ("parameters", "host", "tests.stockfishchess.org"),
        ("parameters", "port", "443"),
        ("parameters", "concurrency", str(cpu_count)),
        ("parameters", "max_memory", str(int(mem / 2 / 1024 / 1024))),
        ("parameters", "min_threads", "1"),
        ("parameters", "fleet", "False"),
        ("parameters", "use_all_cores", "False"),
    ]

    for v in defaults:
        if not config.has_section(v[0]):
            config.add_section(v[0])
        if not config.has_option(v[0], v[1]):
            config.set(*v)

    # Step 3: parse the command line. Use the current config options as defaults.
    parser = OptionParser()
    parser.add_option(
        "-P",
        "--protocol",
        dest="protocol",
        default=config.get("parameters", "protocol"),
    )
    parser.add_option(
        "-n", "--host", dest="host", default=config.get("parameters", "host")
    )
    parser.add_option(
        "-p", "--port", dest="port", default=config.get("parameters", "port")
    )
    parser.add_option(
        "-c",
        "--concurrency",
        dest="concurrency",
        default=config.get("parameters", "concurrency"),
    )
    parser.add_option(
        "-m",
        "--max_memory",
        dest="max_memory",
        default=config.get("parameters", "max_memory"),
    )
    parser.add_option(
        "-t",
        "--min_threads",
        dest="min_threads",
        default=config.get("parameters", "min_threads"),
    )
    parser.add_option(
        "-f", "--fleet", dest="fleet", default=config.get("parameters", "fleet")
    )
    parser.add_option(
        "-a",
        "--use_all_cores",
        dest="use_all_cores",
        default=config.get("parameters", "use_all_cores"),
    )
    parser.add_option("-w", "--only_config", dest="only_config", default=False)
    (options, args) = parser.parse_args()

    username = config.get("login", "username")
    password = config.get("login", "password", raw=True)

    if len(args) == 2:
        username = args[0]
        password = args[1]
    elif len(args) != 0 or len(username) == 0 or len(password) == 0:
        print("{} [username] [password]\n".format(sys.argv[0]))
        return None

    options.username = username
    options.password = password

    # Step 4: fix inconsistencies in the config options.
    protocol = options.protocol.lower()
    options.protocol = protocol
    if protocol not in ["http", "https"]:
        print("Wrong protocol, use https or http\n")
        return None
    elif protocol == "http" and options.port == "443":
        # Rewrite old port 443 to 80
        options.port = "80"
    elif protocol == "https" and options.port == "80":
        # Rewrite old port 80 to 443
        options.port = "443"

    try:
        if options.use_all_cores == "True":
            cpu_count = multiprocessing.cpu_count()
        else:
            cpu_count = int(options.concurrency)
            if cpu_count > multiprocessing.cpu_count() - 1:
                print(
                    (
                        "\nYou cannot have concurrency {} but at most:\n"
                        "{} with option --concurrency\n"
                        "{} with option --use_all_cores\n"
                    ).format(
                        options.concurrency,
                        multiprocessing.cpu_count() - 1,
                        multiprocessing.cpu_count(),
                    )
                )
                return None
    except Exception as e:
        print(e, file=sys.stderr)
        cpu_count = int(options.concurrency)

    if cpu_count <= 0:
        print("Not enough CPUs to run fishtest: set '--concurrency' to at least one")
        return None

    options.concurrency = str(cpu_count)

    # Step 5: write command line parameters to the config file.
    config.set("login", "username", options.username)
    config.set("login", "password", options.password)
    config.set("parameters", "protocol", options.protocol)
    config.set("parameters", "host", options.host)
    config.set("parameters", "port", options.port)
    config.set("parameters", "concurrency", options.concurrency)
    config.set("parameters", "max_memory", options.max_memory)
    config.set("parameters", "min_threads", options.min_threads)
    config.set("parameters", "fleet", options.fleet)
    config.set("parameters", "use_all_cores", options.use_all_cores)

    with open(config_file, "w") as f:
        config.write(f)

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

    worker_dir = path.dirname(path.realpath(__file__))
    print("Worker started in {} ... (PID={})".format(worker_dir, os.getpid()))

    # Python doesn't have a cross platform file locking api.
    # So we check periodically for the existence
    # of a lock file.
    lock_file = path.join(worker_dir, "worker.lock")
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
    config_file = path.join(worker_dir, "fishtest.cfg")
    options = setup_parameters(config_file)
    if options is None:
        return 1
    if options.only_config:
        return 0

    # Make sure a suitable version of gcc is present.
    gcc_version_ = gcc_version()
    if gcc_version_ is None:
        return 1
    major, minor, patchlevel = gcc_version_
    if (major, minor) < (7, 3):
        print("Please update to g++ version 7.3 or later".format(major, minor))
        return 1

    # Assemble the config/options data as well as some other data in a
    # "worker_info" dictionary.
    # This data will be sent to the server when a new task is requested.
    uname = platform.uname()
    worker_info = {
        "uname": uname[0] + " " + uname[2],
        "architecture": platform.architecture(),
        "concurrency": int(options.concurrency),
        "max_memory": int(options.max_memory),
        "min_threads": int(options.min_threads),
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
    with open(path.join(worker_dir, "uuid.txt"), "w") as f:
        f.write(worker_info["unique_key"])

    # All seems to be well...
    remote = "{}://{}:{}".format(options.protocol, options.host, options.port)
    print("Worker version {} connecting to {}".format(WORKER_VERSION, remote))

    # Start heartbeat.
    heartbeat_thread = threading.Thread(
        target=heartbeat, args=(worker_info, options.password, remote, current_state)
    )
    heartbeat_thread.setDaemon(True)  # This should not be necessary,
    # but there might be bugs ...
    heartbeat_thread.start()

    # If fleet==True then the worker will quit if it is unable to obtain
    # or execute a task. If fleet==False then the worker will go to the
    # next iteration of the main loop.
    # The reason for the existence of this parameter is that it allows
    # a fleet of workers to quickly quit as soon as the queue is empty
    # or the server down.

    fleet = options.fleet.lower() == "true"

    # Start the main loop.
    delay = HTTP_TIMEOUT
    fish_exit = False
    while current_state["alive"]:
        if path.isfile(path.join(worker_dir, "fish.exit")):
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
            if fleet:
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
