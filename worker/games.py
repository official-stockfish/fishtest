import copy
import datetime
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from base64 import b64decode
from contextlib import ExitStack
from queue import Empty, Queue
from zipfile import ZipFile

import requests

IS_WINDOWS = "windows" in platform.system().lower()

ARCH = "?"


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


def is_windows_64bit():
    if "PROCESSOR_ARCHITEW6432" in os.environ:
        return True
    return os.environ["PROCESSOR_ARCHITECTURE"].endswith("64")


def is_64bit():
    if IS_WINDOWS:
        return is_windows_64bit()
    return "64" in platform.architecture()[0]


HTTP_TIMEOUT = 15.0

REPO_URL = "https://github.com/official-stockfish/books"
EXE_SUFFIX = ".exe" if IS_WINDOWS else ""
MAKE_CMD = "make COMP=mingw " if IS_WINDOWS else "make COMP=gcc "


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
        result.raise_for_status()  # also catch return codes >= 400
    except Exception as e:
        print(
            "Exception in requests.post():\n",
            e,
            sep="",
            file=sys.stderr,
        )
        raise WorkerException("Post request to {} failed".format(remote), e=e)

    return result


def send_api_post_request(api_url, payload):
    return requests_post(
        api_url,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=HTTP_TIMEOUT,
    )


def github_api(repo):
    """Convert from https://github.com/<user>/<repo>
    To https://api.github.com/repos/<user>/<repo>"""
    return repo.replace("https://github.com", "https://api.github.com/repos")


def required_net(engine):
    net = None
    print("Obtaining EvalFile of {} ...".format(os.path.basename(engine)))
    with subprocess.Popen(
        [engine, "uci"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    ) as p:
        for line in iter(p.stdout.readline, ""):
            if "EvalFile" in line:
                net = line.split(" ")[6].strip()

    if p.returncode != 0:
        raise WorkerException("UCI exited with non-zero code {}".format(p.returncode))

    return net


def verify_required_cutechess(cutechess):
    print("Obtaining version info for {} ...".format(os.path.basename(cutechess)))
    try:
        with subprocess.Popen(
            [cutechess, "--version"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        ) as p:
            pattern = re.compile("cutechess-cli ([0-9]*).([0-9]*).([0-9]*)")
            for line in iter(p.stdout.readline, ""):
                m = pattern.search(line)
                if m:
                    print("Found: ", line.strip())
                    major = int(m.group(1))
                    minor = int(m.group(2))
                    patch = int(m.group(3))
    except (OSError, subprocess.SubprocessError) as e:
        print("Exception running cutechess-cli:\n", e, sep="", file=sys.stderr)
        raise FatalException("Not working cutechess-cli - sorry!")

    if p.returncode != 0:
        raise FatalException("Failed to find cutechess version info")

    if (major, minor) < (1, 2):
        raise FatalException(
            "Requires cutechess 1.2 or higher, found version doesn't match"
        )


def required_net_from_source():
    """Parse evaluate.h and ucioption.cpp to find default net"""
    net = None

    # NNUE code after binary embedding (Aug 2020)
    with open("evaluate.h", "r") as srcfile:
        for line in srcfile:
            if "EvalFileDefaultName" in line and "define" in line:
                p = re.compile("nn-[a-z0-9]{12}.nnue")
                m = p.search(line)
                if m:
                    net = m.group(0)
    if net:
        return net

    # NNUE code before binary embedding (Aug 2020)
    with open("ucioption.cpp", "r") as srcfile:
        for line in srcfile:
            if "EvalFile" in line and "Option" in line:
                p = re.compile("nn-[a-z0-9]{12}.nnue")
                m = p.search(line)
                if m:
                    net = m.group(0)

    return net


def download_net(remote, testing_dir, net):
    url = remote + "/api/nn/" + net
    print("Downloading {}".format(net))
    r = requests_get(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
    with open(os.path.join(testing_dir, net), "wb") as f:
        f.write(r.content)


def validate_net(testing_dir, net):
    with open(os.path.join(testing_dir, net), "rb") as f:
        content = f.read()
    hash = hashlib.sha256(content).hexdigest()
    return hash[:12] == net[3:15]


def verify_signature(engine, signature, remote, payload, concurrency, worker_info):
    global ARCH
    with subprocess.Popen(
        [engine, "compiler"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    ) as p:
        for line in iter(p.stdout.readline, ""):
            if "settings" in line:
                ARCH = line.split(": ")[1].strip()
    if p.returncode:
        raise WorkerException(
            "Compiler info exited with non-zero code {}".format(p.returncode)
        )

    with ExitStack() as stack:
        if concurrency > 1:
            busy_process = stack.enter_context(
                subprocess.Popen(
                    [engine],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    universal_newlines=True,
                    bufsize=1,
                    close_fds=not IS_WINDOWS,
                )
            )
            busy_process.stdin.write(
                "setoption name Threads value {}\n".format(concurrency - 1)
            )
            busy_process.stdin.write("go infinite\n")
            busy_process.stdin.flush()

        bench_sig = ""
        print("Verifying signature of {} ...".format(os.path.basename(engine)))
        p = stack.enter_context(
            subprocess.Popen(
                [engine, "bench"],
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                universal_newlines=True,
                bufsize=1,
                close_fds=not IS_WINDOWS,
            )
        )
        for line in iter(p.stderr.readline, ""):
            if "Nodes searched" in line:
                bench_sig = line.split(": ")[1].strip()
            if "Nodes/second" in line:
                bench_nps = float(line.split(": ")[1].strip())

        if p.returncode:
            raise WorkerException(
                "Bench exited with non-zero code {}".format(p.returncode)
            )

        if int(bench_sig) != int(signature):
            message = "{}-{}cores-{}: Wrong bench in {} Expected: {} Got: {}".format(
                worker_info["username"],
                worker_info["concurrency"],
                worker_info["unique_key"].split("-")[0],
                os.path.basename(engine),
                signature,
                bench_sig,
            )
            payload["message"] = message
            send_api_post_request(remote + "/api/stop_run", payload)
            # Use a more compact message for "/api/failed_task".
            # Note that if the previous /api/stop_run succeeded
            # (i.e. if the user has sufficient CPU hours) then
            # /api/failed_task will have no effect since the current
            # task has already been set to inactive.
            message = "Wrong bench in {}... Expected: {} Got: {}".format(
                os.path.basename(engine)[:16], signature, bench_sig
            )
            raise WorkerException(message)

        if concurrency > 1:
            busy_process.communicate("quit\n")
            busy_process.stdin.close()

    return bench_nps


def setup(item, testing_dir):
    """Download item from FishCooking to testing_dir"""
    tree = requests_get(
        github_api(REPO_URL) + "/git/trees/master", timeout=HTTP_TIMEOUT
    ).json()
    for blob in tree["tree"]:
        if blob["path"] == item:
            print("Downloading {} ...".format(item))
            blob_json = requests_get(blob["url"], timeout=HTTP_TIMEOUT).json()
            with open(os.path.join(testing_dir, item), "wb+") as f:
                f.write(b64decode(blob_json["content"]))
            break
    else:
        raise WorkerException("Item {} not found".format(item))


def gcc_props():
    """Parse the output of g++ -Q -march=native --help=target and extract the available properties"""
    with subprocess.Popen(
        ["g++", "-Q", "-march=native", "--help=target"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    ) as p:
        flags = []
        arch = "None"
        for line in iter(p.stdout.readline, ""):
            if "[enabled]" in line:
                flags.append(line.split()[0])
            if "-march" in line and len(line.split()) == 2:
                arch = line.split()[1]

    if p.returncode != 0:
        raise WorkerException(
            "g++ target query failed with return code {}".format(p.returncode)
        )

    return {"flags": flags, "arch": arch}


def make_targets():
    """Parse the output of make help and extract the available targets"""
    with subprocess.Popen(
        ["make", "help"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    ) as p:
        targets = []
        read_targets = False

        for line in iter(p.stdout.readline, ""):
            if "Supported compilers:" in line:
                read_targets = False
            if read_targets and len(line.split()) > 1:
                targets.append(line.split()[0])
            if "Supported archs:" in line:
                read_targets = True

    if p.returncode != 0:
        raise WorkerException(
            "make help failed with return code {}".format(p.returncode)
        )

    return targets


def find_arch_string():
    """Find the best ARCH=... string based on the cpu/g++ capabilities and Makefile targets"""

    targets = make_targets()

    props = gcc_props()

    if is_64bit():
        if (
            "-mavx512vnni" in props["flags"]
            and "-mavx512dq" in props["flags"]
            and "-mavx512f" in props["flags"]
            and "-mavx512bw" in props["flags"]
            and "-mavx512vl" in props["flags"]
            and "x86-64-vnni256" in targets
        ):
            res = "x86-64-vnni256"
        elif (
            "-mavx512f" in props["flags"]
            and "-mavx512bw" in props["flags"]
            and "x86-64-avx512" in targets
        ):
            res = "x86-64-avx512"
            res = "x86-64-bmi2"  # use bmi2 until avx512 performance becomes actually better
        elif (
            "-mbmi2" in props["flags"]
            and "x86-64-bmi2" in targets
            and props["arch"] not in ["znver1", "znver2"]
        ):
            res = "x86-64-bmi2"
        elif "-mavx2" in props["flags"] and "x86-64-avx2" in targets:
            res = "x86-64-avx2"
        elif (
            "-mpopcnt" in props["flags"]
            and "-msse4.1" in props["flags"]
            and "x86-64-modern" in targets
        ):
            res = "x86-64-modern"
        elif "-mssse3" in props["flags"] and "x86-64-ssse3" in targets:
            res = "x86-64-ssse3"
        elif (
            "-mpopcnt" in props["flags"]
            and "-msse3" in props["flags"]
            and "x86-64-sse3-popcnt" in targets
        ):
            res = "x86-64-sse3-popcnt"
        else:
            res = "x86-64"
    else:
        if (
            "-mpopcnt" in props["flags"]
            and "-msse4.1" in props["flags"]
            and "x86-32-sse41-popcnt" in targets
        ):
            res = "x86-32-sse41-popcnt"
        elif "-msse2" in props["flags"] and "x86-32-sse2" in targets:
            res = "x86-32-sse2"
        else:
            res = "x86-32"

    print("Available Makefile architecture targets: ", targets)
    print("Available g++/cpu properties: ", props)
    print("Determined the best architecture to be ", res)

    return "ARCH=" + res


def setup_engine(
    destination, worker_dir, testing_dir, remote, sha, repo_url, concurrency
):
    """Download and build sources in a temporary directory then move exe to destination"""
    tmp_dir = tempfile.mkdtemp(dir=worker_dir)

    try:
        os.chdir(tmp_dir)
        with open("sf.gz", "wb+") as f:
            f.write(
                requests_get(
                    github_api(repo_url) + "/zipball/" + sha, timeout=HTTP_TIMEOUT
                ).content
            )
        zip_file = ZipFile("sf.gz")
        zip_file.extractall()
        zip_file.close()
        prefix = os.path.commonprefix([n.filename for n in zip_file.infolist()])
        os.chdir(os.path.join(tmp_dir, prefix, "src"))

        net = required_net_from_source()
        if net:
            print("Build uses default net: ", net)
            if not os.path.exists(os.path.join(testing_dir, net)) or not validate_net(
                testing_dir, net
            ):
                download_net(remote, testing_dir, net)
                if not validate_net(testing_dir, net):
                    raise WorkerException(
                        "Failed to validate the network: {}".format(net)
                    )
            shutil.copyfile(os.path.join(testing_dir, net), net)

        ARCH = find_arch_string()

        cmd = MAKE_CMD + ARCH + " -j {}".format(concurrency) + " profile-build"
        env = dict(os.environ, CXXFLAGS="-DNNUE_EMBEDDING_OFF")
        try:
            subprocess.check_call(
                cmd,
                shell=True,
                env=env,
            )
        except Exception as e:
            print("Exception during main make command:\n", e, sep="", file=sys.stderr)
            raise WorkerException("Executing {} failed".format(cmd), e=e)

        # try/pass needed for backwards compatibility with older stockfish,
        # where 'make strip' fails under mingw. TODO: check if still needed
        try:
            subprocess.check_call(
                MAKE_CMD + ARCH + " -j {}".format(concurrency) + " strip", shell=True
            )
        except Exception as e:
            print("Exception stripping binary:\n", e, sep="", file=sys.stderr)

        # We called setup_engine() because the engine was not cached.
        # Only another worker running in the same folder can have built the engine.
        if os.path.exists(destination):
            raise FatalException("Another worker is running in the same directory!")
        else:
            shutil.move("stockfish" + EXE_SUFFIX, destination)
    finally:
        os.chdir(worker_dir)
        shutil.rmtree(tmp_dir)


def kill_process(p):
    p_name = os.path.basename(p.args[0])
    print("\nKilling {} with pid {} ... ".format(p_name, p.pid), end="")
    try:
        if IS_WINDOWS:
            # Kill doesn't kill subprocesses on Windows
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
        print("killed")


def adjust_tc(tc, factor, concurrency):
    # Parse the time control in cutechess format
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

    # Rebuild scaled_tc now: cutechess-cli and stockfish parse 3 decimal places
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


def enqueue_output(out, queue):
    for line in iter(out.readline, ""):
        queue.put(line)


w_params = None
b_params = None


def update_pentanomial(line, rounds):
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
    # Finished game 4 (Base-5446e6f vs New-1a68b26): 1/2-1/2 {Draw by adjudication}
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
    assert (
        current.get("result", -1000) == -1
        or abs(sum(rounds["trinomial"]) - saved_sum_trinomial) == 1
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
    p, remote, result, spsa, spsa_tuning, games_to_play, batch_size, tc_limit
):
    saved_stats = copy.deepcopy(result["stats"])
    rounds = {}

    q = Queue()
    t = threading.Thread(target=enqueue_output, args=(p.stdout, q))
    t.daemon = True
    t.start()

    end_time = datetime.datetime.now() + datetime.timedelta(seconds=tc_limit)
    print("TC limit {} End time: {}".format(tc_limit, end_time))

    num_games_updated = 0
    while datetime.datetime.now() < end_time:
        try:
            line = q.get_nowait().strip()
        except Empty:
            if p.poll() is not None:
                break
            time.sleep(1)
            continue

        print(line, flush=True)

        # Have we reached the end of the match?  Then just exit
        if "Finished match" in line:
            if num_games_updated == games_to_play:
                print("Finished match cleanly")
            else:
                raise WorkerException("Finished match uncleanly")

        # Parse line like this:
        # Warning: New-eb6a21875e doesn't have option ThreatBySafePawn
        if "Warning:" in line and "doesn't have option" in line:
            message = r'Cutechess-cli says: "{}"'.format(line)
            result["message"] = message
            send_api_post_request(remote + "/api/stop_run", result)
            message = r'Cutechess-cli says: "{}"'.format(line)
            raise WorkerException(message)

        # Parse line like this:
        # Finished game 1 (stockfish vs base): 0-1 {White disconnects}
        if "disconnects" in line or "connection stalls" in line:
            result["stats"]["crashes"] += 1

        if "on time" in line:
            result["stats"]["time_losses"] += 1

        # Parse line like this:
        # Score of stockfish vs base: 0 - 0 - 1  [0.500] 1
        if "Score" in line:
            chunks = line.split(":")
            chunks = chunks[1].split()
            wld = [int(chunks[0]), int(chunks[2]), int(chunks[4])]

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

            # Send an update_task request after a batch is full or if we have played all games
            if (num_games_finished == num_games_updated + batch_size) or (
                num_games_finished == games_to_play
            ):
                # Attempt to send game results to the server. Retry a few times upon error
                update_succeeded = False
                for _ in range(5):
                    t0 = datetime.datetime.utcnow()
                    try:
                        response = send_api_post_request(
                            remote + "/api/update_task", result
                        ).json()
                    except Exception as e:
                        print(
                            "Exception calling update_task:\n",
                            e,
                            sep="",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            "  Task updated successfully in {}s".format(
                                (datetime.datetime.utcnow() - t0).total_seconds()
                            )
                        )
                        if not response["task_alive"]:
                            # This task is no longer necessary
                            print("Server told us task is no longer needed")
                            return False
                        update_succeeded = True
                        num_games_updated = num_games_finished
                        break
                    time.sleep(HTTP_TIMEOUT)
                if not update_succeeded:
                    raise WorkerException("Too many failed update attempts")
                    break

        # act on line like this
        # Finished game 4 (Base-5446e6f vs New-1a68b26): 1/2-1/2 {Draw by adjudication}
        if "Finished game" in line:
            update_pentanomial(line, rounds)

    now = datetime.datetime.now()
    if now >= end_time:
        raise WorkerException("{} is past end time {}".format(now, end_time))

    return True


def launch_cutechess(
    cmd, remote, result, spsa_tuning, games_to_play, batch_size, tc_limit
):
    spsa = {"w_params": [], "b_params": [], "num_games": games_to_play}

    if spsa_tuning:
        # Request parameters for next game
        t0 = datetime.datetime.utcnow()
        req = send_api_post_request(remote + "/api/request_spsa", result).json()
        print(
            "Fetched SPSA parameters successfully in {}s".format(
                (datetime.datetime.utcnow() - t0).total_seconds()
            )
        )

        global w_params, b_params
        w_params = req["w_params"]
        b_params = req["b_params"]

        result["spsa"] = spsa
    else:
        w_params = []
        b_params = []

    # Run cutechess-cli binary
    idx = cmd.index("_spsa_")
    cmd = (
        cmd[:idx]
        + ["option.{}={}".format(x["name"], round(x["value"])) for x in w_params]
        + cmd[idx + 1 :]
    )
    idx = cmd.index("_spsa_")
    cmd = (
        cmd[:idx]
        + ["option.{}={}".format(x["name"], round(x["value"])) for x in b_params]
        + cmd[idx + 1 :]
    )

    print(cmd)
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    ) as p:
        try:
            task_alive = parse_cutechess_output(
                p,
                remote,
                result,
                spsa,
                spsa_tuning,
                games_to_play,
                batch_size,
                tc_limit,
            )
        finally:
            if p.poll() is None:
                kill_process(p)

    return task_alive


def run_games(worker_info, password, remote, run, task_id, pgn_file):
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
        "username": worker_info["username"],
        "password": password,
        "unique_key": worker_info["unique_key"],
        "run_id": str(run["_id"]),
        "task_id": task_id,
        "stats": input_stats,
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
    repo_url = run["args"].get("tests_repo", REPO_URL)
    games_concurrency = int(worker_info["concurrency"]) // threads

    opening_offset = task.get("start", task_id * task["num_games"])
    if "start" in task:
        print("Variable task sizes used. Opening offset = {}".format(opening_offset))
    start_game_index = opening_offset + input_total_games
    run_seed = int(hashlib.sha1(run["_id"].encode("utf-8")).hexdigest(), 16) % (2 ** 30)

    # Format options according to cutechess syntax
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

    # Setup testing directory if not already exsisting
    worker_dir = os.path.dirname(os.path.realpath(__file__))
    testing_dir = os.path.join(worker_dir, "testing")
    if not os.path.exists(testing_dir):
        os.makedirs(testing_dir)

    # clean up old engines (keeping the 50 most recent)
    engines = glob.glob(os.path.join(testing_dir, "stockfish_*" + EXE_SUFFIX))
    if len(engines) > 50:
        engines.sort(key=os.path.getmtime)
        for old_engine in engines[:-50]:
            try:
                os.remove(old_engine)
            except Exception as e:
                print(
                    "Failed to remove an old engine binary {}:\n".format(old_engine),
                    e,
                    sep="",
                    file=sys.stderr,
                )

    # create new engines
    sha_new = run["args"]["resolved_new"]
    sha_base = run["args"]["resolved_base"]
    new_engine_name = "stockfish_" + sha_new
    base_engine_name = "stockfish_" + sha_base

    new_engine = os.path.join(testing_dir, new_engine_name + EXE_SUFFIX)
    base_engine = os.path.join(testing_dir, base_engine_name + EXE_SUFFIX)
    cutechess = os.path.join(testing_dir, "cutechess-cli" + EXE_SUFFIX)

    # Build from sources new and base engines as needed
    if not os.path.exists(new_engine):
        setup_engine(
            new_engine,
            worker_dir,
            testing_dir,
            remote,
            sha_new,
            repo_url,
            worker_info["concurrency"],
        )
    if not os.path.exists(base_engine):
        setup_engine(
            base_engine,
            worker_dir,
            testing_dir,
            remote,
            sha_base,
            repo_url,
            worker_info["concurrency"],
        )

    os.chdir(testing_dir)

    # Download book if not already existing
    if (
        not os.path.exists(os.path.join(testing_dir, book))
        or os.stat(os.path.join(testing_dir, book)).st_size == 0
    ):
        zipball = book + ".zip"
        setup(zipball, testing_dir)
        zip_file = ZipFile(zipball)
        zip_file.extractall()
        zip_file.close()
        os.remove(zipball)

    # Download cutechess if not already existing
    if not os.path.exists(cutechess):
        if len(EXE_SUFFIX) > 0:
            zipball = "cutechess-cli-win.zip"
        else:
            zipball = "cutechess-cli-linux-{}.zip".format(platform.architecture()[0])
        setup(zipball, testing_dir)
        zip_file = ZipFile(zipball)
        zip_file.extractall()
        zip_file.close()
        os.remove(zipball)
        os.chmod(cutechess, os.stat(cutechess).st_mode | stat.S_IEXEC)

    # verify that an available cutechess matches the required minimum version
    verify_required_cutechess(cutechess)

    # clean up old networks (keeping the 10 most recent)
    networks = glob.glob(os.path.join(testing_dir, "nn-*.nnue"))
    if len(networks) > 10:
        networks.sort(key=os.path.getmtime)
        for old_net in networks[:-10]:
            try:
                os.remove(old_net)
            except Exception as e:
                print(
                    "Failed to remove an old network {}:\n".format(old_net),
                    e,
                    sep="",
                    file=sys.stderr,
                )

    # Add EvalFile with full path to cutechess options, and download networks if not already existing
    net_base = required_net(base_engine)
    if net_base:
        base_options = base_options + [
            "option.EvalFile={}".format(os.path.join(testing_dir, net_base))
        ]
    net_new = required_net(new_engine)
    if net_new:
        new_options = new_options + [
            "option.EvalFile={}".format(os.path.join(testing_dir, net_new))
        ]

    for net in [net_base, net_new]:
        if net:
            if not os.path.exists(os.path.join(testing_dir, net)) or not validate_net(
                testing_dir, net
            ):
                download_net(remote, testing_dir, net)
                if not validate_net(testing_dir, net):
                    raise WorkerException(
                        "Failed to validate the network: {}".format(net)
                    )

    # pgn output setup
    pgn_name = "results-" + worker_info["unique_key"] + ".pgn"
    pgn_file[0] = os.path.join(testing_dir, pgn_name)
    pgn_file = pgn_file[0]
    if os.path.exists(pgn_file):
        os.remove(pgn_file)

    # Verify signatures are correct
    verify_signature(
        new_engine,
        run["args"]["new_signature"],
        remote,
        result,
        games_concurrency * threads,
        worker_info,
    )
    base_nps = verify_signature(
        base_engine,
        run["args"]["base_signature"],
        remote,
        result,
        games_concurrency * threads,
        worker_info,
    )

    if base_nps < 350000:  # lowered from 450000 - dirty fix for some slow workers
        raise FatalException(
            "This machine is too slow to run fishtest effectively - sorry!"
        )

    factor = (
        1080000.0 / base_nps
    )  # 1080000nps is the reference core, also used in fishtest views.

    # Benchmark to adjust cpu scaling
    scaled_tc, tc_limit = adjust_tc(
        run["args"]["tc"], factor, int(worker_info["concurrency"])
    )
    scaled_new_tc = scaled_tc
    if "new_tc" in run["args"]:
        scaled_new_tc, new_tc_limit = adjust_tc(
            run["args"]["new_tc"], factor, int(worker_info["concurrency"])
        )
        tc_limit = (tc_limit + new_tc_limit) / 2

    result["nps"] = base_nps
    result["ARCH"] = ARCH

    print("Running {} vs {}".format(run["args"]["new_tag"], run["args"]["base_tag"]))

    threads_cmd = []
    if not any("Threads" in s for s in new_options + base_options):
        threads_cmd = ["option.Threads={}".format(threads)]

    # If nodestime is being used, give engines extra grace time to
    # make time losses virtually impossible
    nodestime_cmd = []
    if any("nodestime" in s for s in new_options + base_options):
        nodestime_cmd = ["timemargin=10000"]

    def make_player(arg):
        return run["args"][arg].split(" ")[0]

    if spsa_tuning:
        tc_limit *= 2

    while games_remaining > 0:

        batch_size = games_concurrency * 4  # update frequency

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

        # Handle book or pgn file
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

        # Run cutechess-cli binary
        cmd = (
            [
                cutechess,
                "-repeat",
                "-games",
                str(int(games_to_play)),
                "-tournament",
                "gauntlet",
            ]
            + pgnout
            + ["-site", "https://tests.stockfishchess.org/tests/view/" + run["_id"]]
            + [
                "-event",
                "Batch {}: {} vs {}".format(
                    task_id, make_player("new_tag"), make_player("base_tag")
                ),
            ]
            + ["-srand", "{}".format(run_seed)]
            + [
                "-resign",
                "movecount=3",
                "score=400",
                "-draw",
                "movenumber=34",
                "movecount=8",
                "score=20",
                "-concurrency",
                str(int(games_concurrency)),
            ]
            + pgn_cmd
            + [
                "-engine",
                "name=New-" + run["args"]["resolved_new"][:10],
                "tc={}".format(scaled_new_tc),
                "cmd={}".format(new_engine_name),
            ]
            + new_options
            + ["_spsa_"]
            + [
                "-engine",
                "name=Base-" + run["args"]["resolved_base"][:10],
                "tc={}".format(scaled_tc),
                "cmd={}".format(base_engine_name),
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
            remote,
            result,
            spsa_tuning,
            games_to_play,
            batch_size,
            tc_limit * games_to_play / min(games_to_play, games_concurrency),
        )

        games_remaining -= games_to_play
        start_game_index += games_to_play

        if not task_alive:
            break

    return
