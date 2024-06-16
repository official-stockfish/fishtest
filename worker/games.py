import copy
import ctypes
import hashlib
import io
import json
import math
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
from base64 import b64decode
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Queue
from zipfile import ZipFile

import requests

IS_WINDOWS = "windows" in platform.system().lower()
IS_MACOS = "darwin" in platform.system().lower()
LOGFILE = "api.log"

LOG_LOCK = threading.Lock()


class WorkerException(Exception):
    def __new__(cls, msg, e=None):
        if e is not None and isinstance(e, WorkerException):
            # Note that this forwards also instances of
            # subclasses of WorkerException, e.g.
            # FatalException.
            return e
        else:
            return super().__new__(cls, msg)

    def __init__(self, *args, **kw):
        pass


class FatalException(WorkerException):
    pass


class RunException(WorkerException):
    pass


def is_windows_64bit():
    if "PROCESSOR_ARCHITEW6432" in os.environ:
        return True
    return os.environ["PROCESSOR_ARCHITECTURE"].endswith("64")


def is_64bit():
    if IS_WINDOWS:
        return is_windows_64bit()
    return "64" in platform.architecture()[0]


HTTP_TIMEOUT = 30.0
CUTECHESS_KILL_TIMEOUT = 15.0
UPDATE_RETRY_TIME = 15.0

RAWCONTENT_HOST = "https://raw.githubusercontent.com"
API_HOST = "https://api.github.com"
EXE_SUFFIX = ".exe" if IS_WINDOWS else ""


def log(s):
    logfile = Path(__file__).resolve().parent / LOGFILE
    with LOG_LOCK:
        with open(logfile, "a") as f:
            f.write("{} : {}\n".format(datetime.now(timezone.utc), s))


def backup_log():
    try:
        logfile = Path(__file__).resolve().parent / LOGFILE
        logfile_previous = logfile.with_suffix(logfile.suffix + ".previous")
        if logfile.exists():
            print("Moving logfile {} to {}".format(logfile, logfile_previous))
            with LOG_LOCK:
                logfile.replace(logfile_previous)
    except Exception as e:
        print(
            "Exception moving log:\n",
            e,
            sep="",
            file=sys.stderr,
        )


def str_signal(signal_):
    try:
        return signal.Signals(signal_).name
    except (ValueError, AttributeError):
        return "SIG<{}>".format(signal_)


def format_return_code(r):
    if r < 0:
        return str_signal(-r)
    elif r >= 256:
        return str(hex(r))
    else:
        return str(r)


def send_ctrl_c(pid):
    kernel = ctypes.windll.kernel32
    _ = (
        kernel.FreeConsole()
        and kernel.SetConsoleCtrlHandler(None, True)
        and kernel.AttachConsole(pid)
        and kernel.GenerateConsoleCtrlEvent(0, 0)
    )


def send_sigint(p):
    if IS_WINDOWS:
        if p.poll() is None:
            proc = multiprocessing.Process(target=send_ctrl_c, args=(p.pid,))
            proc.start()
            proc.join()
    else:
        p.send_signal(signal.SIGINT)


# See https://stackoverflow.com/questions/16511337/correct-way-to-try-except-using-python-requests-module
# for background.
# It may be useful to introduce more refined http exception handling in the future.


def requests_get(remote, *args, **kw):
    # A lightweight wrapper around requests.get()
    try:
        result = requests.get(remote, *args, **kw)
        result.raise_for_status()  # also catch return codes >= 400
    except Exception as e:
        print(
            "Exception in requests.get():\n",
            e,
            sep="",
            file=sys.stderr,
        )
        raise WorkerException("Get request to {} failed".format(remote), e=e)

    return result


def requests_post(remote, *args, **kw):
    # A lightweight wrapper around requests.post()
    try:
        result = requests.post(remote, *args, **kw)
    except Exception as e:
        print(
            "Exception in requests.post():\n",
            e,
            sep="",
            file=sys.stderr,
        )
        raise WorkerException("Post request to {} failed".format(remote), e=e)

    return result


def send_api_post_request(api_url, payload, quiet=False):
    t0 = datetime.now(timezone.utc)
    response = requests_post(
        api_url,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=HTTP_TIMEOUT,
    )
    valid_response = True
    try:
        response = response.json()
    except:
        valid_response = False
    if valid_response and not isinstance(response, dict):
        valid_response = False
    if not valid_response:
        message = (
            "The reply to post request {} was not a json encoded dictionary".format(
                api_url
            )
        )
        print(
            "Exception in send_api_post_request():\n",
            message,
            sep="",
            file=sys.stderr,
        )
        raise WorkerException(message)
    if "error" in response:
        print("Error from remote: {}".format(response["error"]))

    t1 = datetime.now(timezone.utc)
    w = 1000 * (t1 - t0).total_seconds()
    s = 1000 * response["duration"]
    log(
        "{:6.2f} ms (s)  {:7.2f} ms (w)  {}".format(
            s,
            w,
            api_url,
        )
    )
    if not quiet:
        if "info" in response:
            print("Info from remote: {}".format(response["info"]))
        print(
            "Post request {} handled in {:.2f}ms (server: {:.2f}ms)".format(
                api_url, w, s
            )
        )
    return response


def github_api(repo):
    """Convert from https://github.com/<user>/<repo>
    To https://api.github.com/repos/<user>/<repo>"""
    return repo.replace("https://github.com", "https://api.github.com/repos")


def required_nets(engine):
    nets = {}
    pattern = re.compile(r"(EvalFile\w*)\s+.*\s+(nn-[a-f0-9]{12}.network)")
    print("Obtaining EvalFile of {} ...".format(os.path.basename(engine)))
    try:
        with subprocess.Popen(
            [engine, "uci"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            for line in iter(p.stdout.readline, ""):
                match = pattern.search(line)
                if match:
                    nets[match.group(1)] = match.group(2)

    except (OSError, subprocess.SubprocessError) as e:
        raise WorkerException(
            "Unable to obtain name for required net. Error: {}".format(str(e))
        )

    if p.returncode != 0:
        raise WorkerException(
            "UCI exited with non-zero code {}".format(format_return_code(p.returncode))
        )

    return nets


def required_value_from_source():
    pattern = re.compile("nn-[a-f0-9]{12}.network")

    with open("src/networks/value.rs", "r") as srcfile:
        for line in srcfile:
            if "ValueFileDefaultName" in line:
                m = pattern.search(line)
                if m:
                    return m.group(0)


def required_policy_from_source():
    pattern = re.compile("nn-[a-f0-9]{12}.network")

    with open("src/networks/policy.rs", "r") as srcfile:
        for line in srcfile:
            if "PolicyFileDefaultName" in line:
                m = pattern.search(line)
                if m:
                    return m.group(0)


def download_net(remote, testing_dir, net):
    url = remote + "/api/nn/" + net
    print("Downloading {}".format(net))
    r = requests_get(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
    (testing_dir / net).write_bytes(r.content)


def validate_net(testing_dir, net):
    hash = hashlib.sha256((testing_dir / net).read_bytes()).hexdigest()
    return hash[:12] == net[3:15]


def establish_validated_net(remote, testing_dir, net):
    if not (testing_dir / net).exists() or not validate_net(testing_dir, net):
        attempt = 0
        while True:
            try:
                attempt += 1
                download_net(remote, testing_dir, net)
                if not validate_net(testing_dir, net):
                    raise WorkerException(
                        "Failed to validate the network: {}".format(net)
                    )
                break
            except FatalException:
                raise
            except WorkerException:
                if attempt > 5:
                    raise
                waitTime = UPDATE_RETRY_TIME * attempt
                print(
                    "Failed to download {} in attempt {}, trying in {} seconds.".format(
                        net, attempt, waitTime
                    )
                )
                time.sleep(waitTime)


def run_single_bench(engine, queue):
    bench_sig = None
    bench_nps = None

    try:
        p = subprocess.Popen(
            [engine, "bench"],
            stderr=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        )

        for line in iter(p.stdout.readline, ""):
            if "Bench: " in line:
                spl = line.split(' ')
                bench_sig = int(spl[1].strip())
                bench_nps = float(spl[3].strip())

        queue.put((bench_sig, bench_nps))
    except:
        queue.put((None, None))


def verify_signature(engine, signature, active_cores):
    queue = multiprocessing.Queue()

    processes = [
        multiprocessing.Process(
            target=run_single_bench,
            args=(engine, queue),
        ) for _ in range(active_cores)
    ]

    for p in processes:
        p.start()

    results = [queue.get() for _ in range(active_cores)]
    bench_nps = 0.0

    for sig, nps in results:
        bench_nps += nps

        if sig is None or bench_nps is None:
            raise RunException(
                "Unable to parse bench output of {}".format(os.path.basename(engine))
            )

        if int(sig) != int(signature):
            message = "Wrong bench in {}, user expected: {} but worker got: {}".format(
                os.path.basename(engine),
                signature,
                sig,
            )
            raise RunException(message)

    bench_nps /= active_cores

    return bench_nps


def download_from_github_raw(
    item, owner="official-stockfish", repo="books", branch="master"
):
    item_url = "{}/{}/{}/{}/{}".format(RAWCONTENT_HOST, owner, repo, branch, item)
    print("Downloading {}".format(item_url))
    return requests_get(item_url, timeout=HTTP_TIMEOUT).content


def download_from_github_api(
    item, owner="official-stockfish", repo="books", branch="master"
):
    item_url = "{}/repos/{}/{}/contents/{}?ref={}".format(
        API_HOST, owner, repo, item, branch
    )
    print("Downloading {}".format(item_url))
    git_url = requests_get(item_url, timeout=HTTP_TIMEOUT).json()["git_url"]
    return b64decode(requests_get(git_url, timeout=HTTP_TIMEOUT).json()["content"])


def download_from_github(
    item, owner="official-stockfish", repo="books", branch="master"
):
    try:
        blob = download_from_github_raw(item, owner=owner, repo=repo, branch=branch)
    except FatalException:
        raise
    except Exception as e:
        print(f"Downloading {item} failed: {str(e)}. Trying the GitHub api.")
        try:
            blob = download_from_github_api(item, owner=owner, repo=repo, branch=branch)
        except Exception as e:
            raise WorkerException(f"Unable to download {item}", e=e)
    return blob


def unzip(blob, save_dir):
    cd = os.getcwd()
    os.chdir(save_dir)
    zipball = io.BytesIO(blob)
    with ZipFile(zipball) as zip_file:
        zip_file.extractall()
        file_list = zip_file.infolist()
    os.chdir(cd)
    return file_list


def convert_book_move_counters(book_file):
    # converts files with complete FENs, leaving others (incl. converted ones) unchanged
    epds = []
    with open(book_file, "r") as file:
        for fen in file:
            fields = fen.split()
            if len(fields) == 6 and fields[4].isdigit() and fields[5].isdigit():
                fields[4] = f"hmvc {fields[4]};"
                fields[5] = f"fmvn {fields[5]};"
                epds.append(" ".join(fields))
            else:
                return

    with open(book_file, "w") as file:
        for epd in epds:
            file.write(epd + "\n")


def setup_engine(
    destination, worker_dir, testing_dir, remote, sha, repo_url
):
    """Download and build sources in a temporary directory then move exe to destination"""
    tmp_dir = Path(tempfile.mkdtemp(dir=worker_dir))

    try:
        item_url = github_api(repo_url) + "/zipball/" + sha
        print("Downloading {}".format(item_url))
        blob = requests_get(item_url).content
        file_list = unzip(blob, tmp_dir)
        prefix = os.path.commonprefix([n.filename for n in file_list])
        os.chdir(tmp_dir / prefix)

        evalfile = required_value_from_source()
        print("Build uses default value net:", evalfile)
        establish_validated_net(remote, testing_dir, evalfile)
        shutil.copyfile(testing_dir / evalfile, evalfile)

        policyfile = required_policy_from_source()
        print("Build uses default policy net:", policyfile)
        establish_validated_net(remote, testing_dir, policyfile)
        shutil.copyfile(testing_dir / policyfile, policyfile)

        cmd = [
            "make",
            f"EXE={destination}",
            f"EVALFILE={evalfile}",
            f"POLICYFILE={policyfile}",
        ]

        if os.path.exists(destination):
            raise FatalException("Another worker is running in the same directory!")

        with subprocess.Popen(
            cmd,
            start_new_session=False if IS_WINDOWS else True,
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
                raise WorkerException(
                    f"Executing {cmd} raised Exception: {type(e).__name__}: {e}",
                    e=e,
                )
        if p.returncode:
            raise WorkerException("Executing {} failed. Error: {}".format(cmd, errors))
    finally:
        os.chdir(worker_dir)
        shutil.rmtree(tmp_dir)


def kill_process(p):
    p_name = os.path.basename(p.args[0])
    print("Killing {} with pid {} ... ".format(p_name, p.pid), end="", flush=True)
    try:
        if IS_WINDOWS:
            # p.kill() doesn't kill subprocesses on Windows.
            subprocess.call(
                ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        else:
            p.kill()
    except Exception as e:
        print(
            "\nException killing {} with pid {}, possibly already terminated:\n".format(
                p_name, p.pid
            ),
            e,
            sep="",
            file=sys.stderr,
        )
    else:
        print("killed", flush=True)


def adjust_tc(tc, factor):
    # Parse the time control in cutechess format.
    chunks = tc.split("+")
    increment = 0.0
    if len(chunks) == 2:
        increment = float(chunks[1])

    chunks = chunks[0].split("/")
    num_moves = 0
    if len(chunks) == 2:
        num_moves = int(chunks[0])

    time_tc = chunks[-1]
    chunks = time_tc.split(":")
    if len(chunks) == 2:
        time_tc = float(chunks[0]) * 60 + float(chunks[1])
    else:
        time_tc = float(chunks[0])

    # Rebuild scaled_tc now: cutechess-cli and stockfish parse 3 decimal places.
    scaled_tc = "{:.3f}".format(time_tc * factor)
    tc_limit = time_tc * factor * 3
    if increment > 0.0:
        scaled_tc += "+{:.3f}".format(increment * factor)
        tc_limit += increment * factor * 200
    if num_moves > 0:
        scaled_tc = "{}/{}".format(num_moves, scaled_tc)
        tc_limit *= 100.0 / num_moves

    print("CPU factor : {} - tc adjusted to {}".format(factor, scaled_tc))
    return scaled_tc, tc_limit


def enqueue_output(stream, queue):
    for line in iter(stream.readline, ""):
        queue.put(line)


def update_pentanomial(line, rounds):
    saved_rounds = copy.deepcopy(rounds)
    saved_line = line

    def result_to_score(_result):
        if _result == "1-0":
            return 2
        elif _result == "0-1":
            return 0
        elif _result == "1/2-1/2":
            return 1
        else:
            return -1

    if "pentanomial" not in rounds.keys():
        rounds["pentanomial"] = 5 * [0]
    if "trinomial" not in rounds.keys():
        rounds["trinomial"] = 3 * [0]

    saved_sum_trinomial = sum(rounds["trinomial"])
    current = {}

    # Parse line like this:
    # Finished game 4 (Base-SHA vs New-SHA): 1/2-1/2 {Draw by adjudication}
    line = line.split()
    if line[0] == "Finished" and line[1] == "game" and len(line) >= 7:
        round_ = int(line[2])
        rounds[round_] = current
        current["white"] = line[3][1:]
        current["black"] = line[5][:-2]
        i = current["result"] = result_to_score(line[6])
        if round_ % 2 == 0:
            if i != -1:
                rounds["trinomial"][2 - i] += 1  # reversed colors
            odd = round_ - 1
            even = round_
        else:
            if i != -1:
                rounds["trinomial"][i] += 1
            odd = round_
            even = round_ + 1
        if odd in rounds.keys() and even in rounds.keys():
            assert rounds[odd]["white"][0:3] == "New"
            assert rounds[odd]["white"] == rounds[even]["black"]
            assert rounds[odd]["black"] == rounds[even]["white"]
            i = rounds[odd]["result"]
            j = rounds[even]["result"]  # even is reversed colors
            if i != -1 and j != -1:
                rounds["pentanomial"][i + 2 - j] += 1
                del rounds[odd]
                del rounds[even]
                rounds["trinomial"][i] -= 1
                rounds["trinomial"][2 - j] -= 1
                assert rounds["trinomial"][i] >= 0
                assert rounds["trinomial"][2 - j] >= 0

    # make sure something happened, but not too much
    # this sometimes fails: we want to understand why
    assertion = (
        current.get("result", -1000) == -1
        or abs(sum(rounds["trinomial"]) - saved_sum_trinomial) == 1
    )
    if not assertion:
        raise WorkerException(
            "update_pentanomial() failed. line={}; rounds before={}; rounds after={}".format(
                saved_line, saved_rounds, rounds
            )
        )


def validate_pentanomial(wld, rounds):
    def results_to_score(results):
        return sum([results[i] * (i / 2.0) for i in range(len(results))])

    LDW = [wld[1], wld[2], wld[0]]
    s3 = results_to_score(LDW)
    s5 = results_to_score(rounds["pentanomial"]) + results_to_score(rounds["trinomial"])
    assert sum(LDW) == 2 * sum(rounds["pentanomial"]) + sum(rounds["trinomial"])
    epsilon = 1e-4
    assert abs(s5 - s3) < epsilon


def parse_cutechess_output(
    p, current_state, remote, result, spsa_tuning, games_to_play, batch_size, tc_limit
):
    hash_pattern = re.compile(r"(Base|New)-[a-f0-9]+")

    def shorten_hash(match):
        word = match.group(0).split("-")
        return "-".join([word[0], word[1][:10]])

    saved_stats = copy.deepcopy(result["stats"])
    rounds = {}

    q = Queue()
    t_output = threading.Thread(target=enqueue_output, args=(p.stdout, q), daemon=True)
    t_output.start()
    t_error = threading.Thread(target=enqueue_output, args=(p.stderr, q), daemon=True)
    t_error.start()

    end_time = datetime.now(timezone.utc) + timedelta(seconds=tc_limit)
    print("TC limit {} End time: {}".format(tc_limit, end_time))

    num_games_updated = 0
    while datetime.now(timezone.utc) < end_time:
        try:
            line = q.get_nowait().strip()
        except Empty:
            if p.poll() is not None:
                break
            time.sleep(1)
            continue

        line = hash_pattern.sub(shorten_hash, line)
        print(line, flush=True)

        # Have we reached the end of the match? Then just exit.
        if "Finished match" in line:
            if num_games_updated == games_to_play:
                print("Finished match cleanly")
            else:
                raise WorkerException("Finished match uncleanly")

        # Parse line like this:
        # Warning: New-SHA doesn't have option ThreatBySafePawn
        if "Warning:" in line and "doesn't have option" in line:
            message = r'Cutechess-cli says: "{}"'.format(line)
            raise RunException(message)

        # Parse line like this:
        # Warning: Invalid value for option P: -354
        if "Warning:" in line and "Invalid value" in line:
            message = r'Cutechess-cli says: "{}"'.format(line)
            raise RunException(message)

        # Parse line like this:
        # Finished game 1 (stockfish vs base): 0-1 {White disconnects}
        if "disconnects" in line or "connection stalls" in line:
            result["stats"]["crashes"] += 1

        if "on time" in line:
            result["stats"]["time_losses"] += 1

        # Parse line like this:
        # Score of stockfish vs base: 0 - 0 - 1  [0.500] 1
        if "Score" in line:
            # Parsing sometimes fails. We want to understand why.
            try:
                chunks = line.split(":")
                chunks = chunks[1].split()
                wld = [int(chunks[0]), int(chunks[2]), int(chunks[4])]
            except:
                raise WorkerException("Failed to parse score line: {}".format(line))

            validate_pentanomial(
                wld, rounds
            )  # check if cutechess-cli result is compatible with
            # our own bookkeeping

            pentanomial = [
                rounds["pentanomial"][i] + saved_stats["pentanomial"][i]
                for i in range(5)
            ]
            result["stats"]["pentanomial"] = pentanomial

            wld_pairs = {}  # trinomial frequencies of completed game pairs

            # rounds['trinomial'] is ordered ldw
            wld_pairs["wins"] = wld[0] - rounds["trinomial"][2]
            wld_pairs["losses"] = wld[1] - rounds["trinomial"][0]
            wld_pairs["draws"] = wld[2] - rounds["trinomial"][1]

            result["stats"]["wins"] = wld_pairs["wins"] + saved_stats["wins"]
            result["stats"]["losses"] = wld_pairs["losses"] + saved_stats["losses"]
            result["stats"]["draws"] = wld_pairs["draws"] + saved_stats["draws"]

            if spsa_tuning:
                spsa = result["spsa"]
                spsa["wins"] = wld_pairs["wins"]
                spsa["losses"] = wld_pairs["losses"]
                spsa["draws"] = wld_pairs["draws"]

            num_games_finished = (
                wld_pairs["wins"] + wld_pairs["losses"] + wld_pairs["draws"]
            )

            assert (
                2 * sum(result["stats"]["pentanomial"])
                == result["stats"]["wins"]
                + result["stats"]["losses"]
                + result["stats"]["draws"]
            )
            assert num_games_finished == 2 * sum(rounds["pentanomial"])
            assert num_games_finished <= num_games_updated + batch_size
            assert num_games_finished <= games_to_play

            # Send an update_task request after a batch is full or if we have played all games.
            if (num_games_finished == num_games_updated + batch_size) or (
                num_games_finished == games_to_play
            ):
                # Attempt to send game results to the server. Retry a few times upon error.
                update_succeeded = False
                for _ in range(5):
                    try:
                        response = send_api_post_request(
                            remote + "/api/update_task", result
                        )
                        if "error" in response:
                            break
                    except Exception as e:
                        print(
                            "Exception calling update_task:\n",
                            e,
                            sep="",
                            file=sys.stderr,
                        )
                        if isinstance(e, FatalException):  # signal
                            raise e
                    else:
                        if not response["task_alive"]:
                            # This task is no longer necessary
                            print(
                                "The server told us that no more games"
                                " are needed for the current task."
                            )
                            return False
                        update_succeeded = True
                        num_games_updated = num_games_finished
                        break
                    time.sleep(UPDATE_RETRY_TIME)
                if not update_succeeded:
                    raise WorkerException("Too many failed update attempts")
                else:
                    current_state["last_updated"] = datetime.now(timezone.utc)

        # Act on line like this:
        # Finished game 4 (Base-SHA vs New-SHA): 1/2-1/2 {Draw by adjudication}
        if line.startswith("Finished game"):
            update_pentanomial(line, rounds)
    else:
        raise WorkerException(
            "{} is past end time {}".format(datetime.now(timezone.utc), end_time)
        )

    return True


def launch_cutechess(
    cmd, current_state, remote, result, spsa_tuning, games_to_play, batch_size, tc_limit
):
    if spsa_tuning:
        # Request parameters for next game.
        req = send_api_post_request(remote + "/api/request_spsa", result)
        if "error" in req:
            raise WorkerException(req["error"])

        if not req["task_alive"]:
            # This task is no longer necessary
            print(
                "The server told us that no more games"
                " are needed for the current task."
            )
            return False

        result["spsa"] = {
            "num_games": games_to_play,
            "wins": 0,
            "losses": 0,
            "draws": 0,
        }

        w_params = req["w_params"]
        b_params = req["b_params"]

    else:
        w_params = []
        b_params = []

    # Run cutechess-cli binary.
    # Stochastic rounding and probability for float N.p: (N, 1-p); (N+1, p)
    idx = cmd.index("_spsa_")
    cmd = (
        cmd[:idx] + [
            "option.{}={}".format(
                x["name"], math.floor(x["value"] + random.uniform(0, 1))
            )
            for x in w_params
        ] + cmd[idx + 1:]
    )
    idx = cmd.index("_spsa_")
    cmd = (
        cmd[:idx] + [
            "option.{}={}".format(
                x["name"], math.floor(x["value"] + random.uniform(0, 1))
            )
            for x in b_params
        ] + cmd[idx + 1:]
    )

    #    print(cmd)
    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            # The next options are necessary to be able to send a CTRL_C_EVENT to this process.
            # https://stackoverflow.com/questions/7085604/sending-c-to-python-subprocess-objects-on-windows
            startupinfo=(
                subprocess.STARTUPINFO(
                    dwFlags=subprocess.STARTF_USESHOWWINDOW,
                    wShowWindow=subprocess.SW_HIDE,
                )
                if IS_WINDOWS
                else None
            ),
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
            close_fds=not IS_WINDOWS,
        ) as p:
            try:
                task_alive = parse_cutechess_output(
                    p,
                    current_state,
                    remote,
                    result,
                    spsa_tuning,
                    games_to_play,
                    batch_size,
                    tc_limit,
                )
            finally:
                # We nicely ask cutechess-cli to stop.
                try:
                    send_sigint(p)
                except Exception as e:
                    print("\nException in send_sigint:\n", e, sep="", file=sys.stderr)
                # now wait...
                print("\nWaiting for cutechess-cli to finish ... ", end="", flush=True)
                try:
                    p.wait(timeout=CUTECHESS_KILL_TIMEOUT)
                except subprocess.TimeoutExpired:
                    print("timeout", flush=True)
                    kill_process(p)
                else:
                    print("done", flush=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(
            "Exception starting cutechess:\n",
            e,
            sep="",
            file=sys.stderr,
        )
        raise WorkerException("Unable to start cutechess. Error: {}".format(str(e)))

    return task_alive


def run_games(
    worker_info, current_state, password, remote, run, task_id, pgn_file, clear_binaries
):
    # This is the main cutechess-cli driver.
    # It is ok, and even expected, for this function to
    # raise exceptions, implicitly or explicitly, if a
    # task cannot be completed.
    # Exceptions will be caught by the caller
    # and handled appropriately.
    # If an immediate exit is necessary then one should
    # raise "FatalException".
    # Explicit exceptions should be raised as
    # "WorkerException". Then they will be recorded
    # on the server.

    task = run["my_task"]

    # Have we run any games on this task yet?

    input_stats = task.get(
        "stats",
        {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": 5 * [0],
        },
    )
    if "pentanomial" not in input_stats:
        input_stats["pentanomial"] = 5 * [0]

    input_total_games = (
        input_stats["wins"] + input_stats["losses"] + input_stats["draws"]
    )

    assert 2 * sum(input_stats["pentanomial"]) == input_total_games

    input_stats["crashes"] = input_stats.get("crashes", 0)
    input_stats["time_losses"] = input_stats.get("time_losses", 0)

    result = {
        "password": password,
        "run_id": str(run["_id"]),
        "task_id": task_id,
        "stats": input_stats,
        "worker_info": worker_info,
    }

    games_remaining = task["num_games"] - input_total_games

    assert games_remaining > 0
    assert games_remaining % 2 == 0

    book = run["args"]["book"]
    book_depth = run["args"]["book_depth"]
    new_options = run["args"]["new_options"]
    base_options = run["args"]["base_options"]
    threads = int(run["args"]["threads"])
    spsa_tuning = "spsa" in run["args"]
    repo_url = run["args"].get("tests_repo")
    worker_concurrency = int(worker_info["concurrency"])
    games_concurrency = worker_concurrency // threads

    opening_offset = task.get("start", task_id * task["num_games"])
    if "start" in task:
        print("Variable task sizes used. Opening offset = {}".format(opening_offset))
    start_game_index = opening_offset + input_total_games
    run_seed = int(hashlib.sha1(run["_id"].encode("utf-8")).hexdigest(), 16) % (2**30)

    # Format options according to cutechess syntax.
    def parse_options(s):
        results = []
        chunks = s.split("=")
        if len(chunks) == 0:
            return results
        param = chunks[0]
        for c in chunks[1:]:
            val = c.split()
            results.append("option.{}={}".format(param, val[0]))
            param = " ".join(val[1:])
        return results

    new_options = parse_options(new_options)
    base_options = parse_options(base_options)

    # Clean up old engines (keeping the num_bkps most recent).
    worker_dir = Path(__file__).resolve().parent
    testing_dir = worker_dir / "testing"
    num_bkps = 0 if clear_binaries else 50
    try:
        engines = sorted(
            testing_dir.glob("monty_*" + EXE_SUFFIX),
            key=os.path.getmtime,
            reverse=True,
        )
    except Exception as e:
        print(
            "Failed to obtain modification time of old engine binary:\n",
            e,
            sep="",
            file=sys.stderr,
        )
    else:
        for old_engine in engines[num_bkps:]:
            try:
                old_engine.unlink()
            except Exception as e:
                print(
                    "Failed to remove an old engine binary {}:\n".format(old_engine),
                    e,
                    sep="",
                    file=sys.stderr,
                )
    # Create new engines.
    sha_new = run["args"]["resolved_new"]
    sha_base = run["args"]["resolved_base"]
    new_engine_name = "monty_" + sha_new
    base_engine_name = "monty_" + sha_base

    new_engine = testing_dir / (new_engine_name + EXE_SUFFIX)
    base_engine = testing_dir / (base_engine_name + EXE_SUFFIX)

    # Build from sources new and base engines as needed.
    if not new_engine.exists():
        setup_engine(
            new_engine,
            worker_dir,
            testing_dir,
            remote,
            sha_new,
            repo_url,
        )
    if not base_engine.exists():
        setup_engine(
            base_engine,
            worker_dir,
            testing_dir,
            remote,
            sha_base,
            repo_url,
        )

    os.chdir(testing_dir)

    # Download the opening book if missing in the directory.
    if not (testing_dir / book).exists() or (testing_dir / book).stat().st_size == 0:
        zipball = book + ".zip"
        blob = download_from_github(zipball)
        unzip(blob, testing_dir)

    # convert .epd containing FENs into .epd containing EPDs with move counters
    # only needed as long as cutechess-cli is the game manager
    if book.endswith(".epd"):
        convert_book_move_counters(testing_dir / book)

    # Clean up the old networks (keeping the num_bkps most recent)
    num_bkps = 10
    for old_net in sorted(
        testing_dir.glob("nn-*.network"), key=os.path.getmtime, reverse=True
    )[num_bkps:]:
        try:
            old_net.unlink()
        except Exception as e:
            print(
                "Failed to remove an old network {}:\n".format(old_net),
                e,
                sep="",
                file=sys.stderr,
            )

    # PGN files output setup.
    pgn_name = "results-" + worker_info["unique_key"] + ".pgn"
    pgn_file[0] = testing_dir / pgn_name
    pgn_file = pgn_file[0]
    try:
        pgn_file.unlink()
    except FileNotFoundError:
        pass

    # Verify that the signatures are correct.
    run_errors = []
    try:
        base_nps = verify_signature(
            base_engine,
            run["args"]["base_signature"],
            games_concurrency * threads,
        )
    except RunException as e:
        run_errors.append(str(e))
    except WorkerException as e:
        raise e

    if not (
        run["args"]["base_signature"] == run["args"]["new_signature"]
        and new_engine == base_engine
    ):
        try:
            verify_signature(
                new_engine,
                run["args"]["new_signature"],
                games_concurrency * threads,
            )
        except RunException as e:
            run_errors.append(str(e))
        except WorkerException as e:
            raise e

    # Handle exceptions if any.
    if run_errors:
        raise RunException("\n".join(run_errors))

    if base_nps < 45541 / (1 + math.tanh((worker_concurrency - 1) / 8)):
        raise FatalException(
            "This machine is too slow ({} nps / thread) to run fishtest effectively - sorry!".format(
                base_nps
            )
        )
    # fishtest with Stockfish 11 had 1.6 Mnps as reference nps and
    # 0.7 Mnps as threshold for the slow worker.
    # also set in rundb.py and delta_update_users.py
    factor = 136622 / base_nps

    # Adjust CPU scaling.
    _, tc_limit_ltc = adjust_tc("60+0.6", factor)
    scaled_tc, tc_limit = adjust_tc(run["args"]["tc"], factor)
    scaled_new_tc = scaled_tc
    if "new_tc" in run["args"]:
        scaled_new_tc, new_tc_limit = adjust_tc(run["args"]["new_tc"], factor)
        tc_limit = (tc_limit + new_tc_limit) / 2

    result["worker_info"]["nps"] = float(base_nps)
    result["worker_info"]["ARCH"] = ""

    threads_cmd = []
    # This is disabled for now because monty doesn't have the Threads option
    # if not any("Threads" in s for s in new_options + base_options):
    #     threads_cmd = ["option.Threads={}".format(threads)]

    # If nodestime is being used, give engines extra grace time to
    # make time losses virtually impossible.
    nodestime_cmd = []
    if any("nodestime" in s for s in new_options + base_options):
        nodestime_cmd = ["timemargin=10000"]

    def make_player(arg):
        return run["args"][arg].split(" ")[0]

    if spsa_tuning:
        tc_limit *= 2

    while games_remaining > 0:
        # Update frequency for NumGames/SPSA test:
        # every 4 games at LTC, or a similar time interval at shorter TCs
        batch_size = games_concurrency * 4 * max(1, round(tc_limit_ltc / tc_limit))

        if spsa_tuning:
            games_to_play = min(batch_size, games_remaining)
            pgnout = []
        else:
            games_to_play = games_remaining
            pgnout = ["-pgnout", pgn_name]

        if "sprt" in run["args"]:
            batch_size = 2 * run["args"]["sprt"].get("batch_size", 1)
            assert games_to_play % batch_size == 0

        assert batch_size % 2 == 0
        assert games_to_play % 2 == 0

        # Handle book or PGN file.
        pgn_cmd = []
        book_cmd = []
        if int(book_depth) <= 0:
            pass
        elif book.endswith(".pgn") or book.endswith(".epd"):
            plies = 2 * int(book_depth)
            pgn_cmd = [
                "-openings",
                "file={}".format(book),
                "format={}".format(book[-3:]),
                "order=random",
                "plies={}".format(plies),
                "start={}".format(1 + start_game_index // 2),
            ]
        else:
            assert False

        # Check for an FRC/Chess960 opening book
        variant = "standard"
        if any(substring in book.upper() for substring in ["FRC", "960"]):
            variant = "fischerandom"

        # Run cutechess binary.
        cutechess = "cutechess-cli" + EXE_SUFFIX
        cmd = (
            [
                os.path.join(testing_dir, cutechess),
                "-recover",
                "-repeat",
                "-games",
                str(int(games_to_play)),
                "-tournament",
                "gauntlet",
            ]
            + pgnout
            + ["-site", "https://montychess.org/tests/view/" + run["_id"]]
            + [
                "-event",
                "Batch {}: {} vs {}".format(
                    task_id, make_player("new_tag"), make_player("base_tag")
                ),
            ]
            + ["-srand", "{}".format(run_seed)]
            + (
                [
                    "-resign",
                    "movecount=3",
                    "score=600",
                    "-draw",
                    "movenumber=34",
                    "movecount=8",
                    "score=20",
                ]
                if run["args"].get("adjudication", True)
                else []
            )
            + ["-variant", "{}".format(variant)]
            + [
                "-concurrency",
                str(int(games_concurrency)),
            ]
            + pgn_cmd
            + [
                "-engine",
                "name=New-" + run["args"]["resolved_new"],
                "tc={}".format(scaled_new_tc),
                "cmd=./{}".format(new_engine_name),
                "dir=.",
            ]
            + new_options
            + ["_spsa_"]
            + [
                "-engine",
                "name=Base-" + run["args"]["resolved_base"],
                "tc={}".format(scaled_tc),
                "cmd=./{}".format(base_engine_name),
                "dir=.",
            ]
            + base_options
            + ["_spsa_"]
            + ["-each", "proto=uci"]
            + nodestime_cmd
            + threads_cmd
            + book_cmd
        )

        task_alive = launch_cutechess(
            cmd,
            current_state,
            remote,
            result,
            spsa_tuning,
            games_to_play,
            batch_size,
            tc_limit * max(8, games_to_play / games_concurrency),
        )

        games_remaining -= games_to_play
        start_game_index += games_to_play

        if not task_alive:
            break

    return
