from __future__ import absolute_import, print_function

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
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from base64 import b64decode
from zipfile import ZipFile

import requests

try:
    from Queue import Empty, Queue
except ImportError:
    from queue import Empty, Queue  # python 3.x

IS_WINDOWS = "windows" in platform.system().lower()

ARCH = "?"


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


def send_api_post_request(api_url, payload):
    return requests.post(
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
    print("Obtaining EvalFile of %s ..." % (os.path.basename(engine)))
    p = subprocess.Popen(
        [engine, "uci"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    )

    for line in iter(p.stdout.readline, ""):
        if "EvalFile" in line:
            net = line.split(" ")[6].strip()

    p.wait()
    p.stdout.close()

    if p.returncode != 0:
        raise Exception("uci exited with non-zero code %d" % (p.returncode))

    return net

def verify_required_cutechess(cutechess):
    print("Obtaining version info for %s ..." % (os.path.basename(cutechess)))

    p = subprocess.Popen(
        [cutechess, "--version"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    )

    pattern = re.compile("cutechess-cli ([0-9]*).([0-9]*).([0-9]*)")
    for line in iter(p.stdout.readline, ""):
        m = pattern.search(line)
        if m:
           print("Found: ",line)
           major = int(m.group(1))
           minor = int(m.group(2))
           patch = int(m.group(3))

    p.wait()
    p.stdout.close()

    if p.returncode != 0:
        raise Exception("Failed to find cutechess version info" % (p.returncode))

    if major < 1 or (major == 1 and minor < 2):
       raise Exception("Requires cutechess 1.2 or higher, found version doesn't match")


def required_net_from_source():
    """ Parse evaluate.h and ucioption.cpp to find default net"""
    net = None

    # NNUE code after binary embedding (Aug 2020)
    with open("evaluate.h", "r") as srcfile:
        for line in srcfile.readlines():
            if "EvalFileDefaultName" in line and "define" in line:
                p = re.compile("nn-[a-z0-9]{12}.nnue")
                m = p.search(line)
                if m:
                    net = m.group(0)
    if net:
        return net

    # NNUE code before binary embedding (Aug 2020)
    with open("ucioption.cpp", "r") as srcfile:
        for line in srcfile.readlines():
            if "EvalFile" in line and "Option" in line:
                p = re.compile("nn-[a-z0-9]{12}.nnue")
                m = p.search(line)
                if m:
                    net = m.group(0)

    return net


def download_net(remote, testing_dir, net):
    url = remote + "/api/nn/" + net
    r = requests.get(url, allow_redirects=True)
    open(os.path.join(testing_dir, net), "wb").write(r.content)


def validate_net(testing_dir, net):
    content = open(os.path.join(testing_dir, net), "rb").read()
    hash = hashlib.sha256(content).hexdigest()
    return hash[:12] == net[3:15]


def verify_signature(engine, signature, remote, payload, concurrency):
    global ARCH
    if concurrency > 1:
        with open(os.devnull, "wb") as dev_null:
            busy_process = subprocess.Popen(
                [engine],
                stdin=subprocess.PIPE,
                stdout=dev_null,
                universal_newlines=True,
                bufsize=1,
                close_fds=not IS_WINDOWS,
            )
        busy_process.stdin.write(
            "setoption name Threads value {:.0f}\n".format(concurrency - 1)
        )
        busy_process.stdin.write("go infinite\n")
        busy_process.stdin.flush()

    try:
        bench_sig = ""
        print("Verifying signature of %s ..." % (os.path.basename(engine)))
        with open(os.devnull, "wb") as dev_null:
            p = subprocess.Popen(
                [engine, "bench"],
                stderr=subprocess.PIPE,
                stdout=dev_null,
                universal_newlines=True,
                bufsize=1,
                close_fds=not IS_WINDOWS,
            )
            p2 = subprocess.Popen(
                [engine, "compiler"],
                stdout=subprocess.PIPE,
                stderr=dev_null,
                universal_newlines=True,
                bufsize=1,
                close_fds=not IS_WINDOWS,
            )

        for line in iter(p.stderr.readline, ""):
            if "Nodes searched" in line:
                bench_sig = line.split(": ")[1].strip()
            if "Nodes/second" in line:
                bench_nps = float(line.split(": ")[1].strip())
        p.wait()
        p.stderr.close()

        for line in iter(p2.stdout.readline, ""):
            if "settings" in line:
                ARCH = line.split(": ")[1].strip()
        p2.wait()
        p2.stdout.close()

        if p.returncode:
            raise Exception("Bench exited with non-zero code %d" % (p.returncode))
        if p2.returncode:
            raise Exception(
                "Compiler info exited with non-zero code %d" % (p2.returncode)
            )

        if int(bench_sig) != int(signature):
            message = "Wrong bench in %s Expected: %s Got: %s" % (
                os.path.basename(engine),
                signature,
                bench_sig,
            )
            payload["message"] = message
            send_api_post_request(remote + "/api/stop_run", payload)
            raise Exception(message)

    finally:
        if concurrency > 1:
            busy_process.communicate("quit\n")
            busy_process.stdin.close()

    return bench_nps


def setup(item, testing_dir):
    """Download item from FishCooking to testing_dir"""
    tree = requests.get(
        github_api(REPO_URL) + "/git/trees/master", timeout=HTTP_TIMEOUT
    ).json()
    for blob in tree["tree"]:
        if blob["path"] == item:
            print("Downloading %s ..." % (item))
            blob_json = requests.get(blob["url"], timeout=HTTP_TIMEOUT).json()
            with open(os.path.join(testing_dir, item), "wb+") as f:
                f.write(b64decode(blob_json["content"]))
            break
    else:
        raise Exception("Item %s not found" % (item))


def gcc_props():
    """Parse the output of g++ -Q -march=native --help=target and extract the available properties"""
    p = subprocess.Popen(
        ["g++", "-Q", "-march=native", "--help=target"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    )

    flags = []
    arch = "None"
    for line in iter(p.stdout.readline, ""):
        if "[enabled]" in line:
            flags.append(line.split()[0])
        if "-march" in line and len(line.split()) == 2:
            arch = line.split()[1]

    p.wait()
    p.stdout.close()

    if p.returncode != 0:
        raise Exception("g++ target query failed with return code %d" % (p.returncode))

    return {"flags": flags, "arch": arch}


def make_targets():
    """Parse the output of make help and extract the available targets"""
    p = subprocess.Popen(
        ["make", "help"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    )

    targets = []
    read_targets = False

    for line in iter(p.stdout.readline, ""):
        if "Supported compilers:" in line:
            read_targets = False
        if read_targets and len(line.split()) > 1:
            targets.append(line.split()[0])
        if "Supported archs:" in line:
            read_targets = True

    p.wait()
    p.stdout.close()

    if p.returncode != 0:
        raise Exception("make help failed with return code %d" % (p.returncode))

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
            "-mbmi2" in props["flags"]
            and "x86-64-bmi2" in targets
            and not props["arch"] in ["znver1", "znver2"]
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
    print("Available g++/cpu properties : ", props)
    print("Determined the best architecture to be ", res)

    return "ARCH=" + res


def setup_engine(
    destination, worker_dir, testing_dir, remote, sha, repo_url, concurrency
):
    if os.path.exists(destination):
        os.remove(destination)
    """Download and build sources in a temporary directory then move exe to destination"""
    tmp_dir = tempfile.mkdtemp(dir=worker_dir)

    try:
        os.chdir(tmp_dir)
        with open("sf.gz", "wb+") as f:
            f.write(
                requests.get(
                    github_api(repo_url) + "/zipball/" + sha, timeout=HTTP_TIMEOUT
                ).content
            )
        zip_file = ZipFile("sf.gz")
        zip_file.extractall()
        zip_file.close()

        for name in zip_file.namelist():
            if name.endswith("/src/"):
                src_dir = name
        os.chdir(src_dir)

        net = required_net_from_source()
        if net:
            print("Build uses default net: ", net)
            if not os.path.exists(os.path.join(testing_dir, net)) or not validate_net(
                testing_dir, net
            ):
                download_net(remote, testing_dir, net)
                if not validate_net(testing_dir, net):
                    raise Exception("Failed to validate the network: %s " % (net))
            shutil.copyfile(os.path.join(testing_dir, net), net)

        ARCH = find_arch_string()

        subprocess.check_call(
            MAKE_CMD + ARCH + " -j %s" % (concurrency) + " profile-build", shell=True
        )
        try:  # try/pass needed for backwards compatibility with older stockfish, where 'make strip' fails under mingw.
            subprocess.check_call(
                MAKE_CMD + ARCH + " -j %s" % (concurrency) + " strip", shell=True
            )
        except:
            pass

        shutil.move("stockfish" + EXE_SUFFIX, destination)
    except:
        raise Exception("Failed to setup engine for %s" % (sha))
    finally:
        os.chdir(worker_dir)
        shutil.rmtree(tmp_dir)


def kill_process(p):
    try:
        if IS_WINDOWS:
            # Kill doesn't kill subprocesses on Windows
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(p.pid)])
        else:
            p.kill()
    except:
        print(
            "Note: "
            + str(sys.exc_info()[0])
            + " killing the process pid: "
            + str(p.pid)
            + ", possibly already terminated"
        )
    finally:
        p.wait()
        p.stdout.close()


def adjust_tc(tc, base_nps, concurrency):
    factor = (
        1200000.0 / base_nps
    )  # 1.6Mnps is the reference core, also used in fishtest views.
    if base_nps < 500000:
        sys.stderr.write(
            "This machine is too slow to run fishtest effectively - sorry!\n"
        )
        sys.exit(1)

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
    scaled_tc = "%.3f" % (time_tc * factor)
    tc_limit = time_tc * factor * 3
    if increment > 0.0:
        scaled_tc += "+%.3f" % (increment * factor)
        tc_limit += increment * factor * 200
    if num_moves > 0:
        scaled_tc = "%d/%s" % (num_moves, scaled_tc)
        tc_limit *= 100.0 / num_moves

    print("CPU factor : %f - tc adjusted to %s" % (factor, scaled_tc))
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

    if not "pentanomial" in rounds.keys():
        rounds["pentanomial"] = 5 * [0]
    if not "trinomial" in rounds.keys():
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
            line = q.get_nowait()
        except Empty:
            if p.poll() is not None:
                break
            time.sleep(1)
            continue

        sys.stdout.write(line)
        sys.stdout.flush()

        # Have we reached the end of the match?  Then just exit
        if "Finished match" in line:
            # The following assertion will fail if there are games without result.
            # Does this ever happen?
            assert num_games_updated == games_to_play
            print("Finished match cleanly")

        # Parse line like this:
        # Warning: New-eb6a21875e doesn't have option ThreatBySafePawn
        if "Warning:" in line and "doesn't have option" in line:
            message = r'Cutechess-cli says: "%s"' % line.strip()
            result["message"] = message
            send_api_post_request(remote + "/api/stop_run", result)
            raise Exception(message)

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
                    try:
                        t0 = datetime.datetime.utcnow()
                        response = send_api_post_request(
                            remote + "/api/update_task", result
                        ).json()
                        print(
                            "  Task updated successfully in %ss"
                            % ((datetime.datetime.utcnow() - t0).total_seconds())
                        )
                        if not response["task_alive"]:
                            # This task is no longer necessary
                            print("Server told us task is no longer needed")
                            return response
                        update_succeeded = True
                        num_games_updated = num_games_finished
                        break
                    except Exception as e:
                        sys.stderr.write("Exception from calling update_task:\n")
                        print(e)
                        # traceback.print_exc(file=sys.stderr)
                    time.sleep(HTTP_TIMEOUT)
                if not update_succeeded:
                    print("Too many failed update attempts")
                    break

        # act on line like this
        # Finished game 4 (Base-5446e6f vs New-1a68b26): 1/2-1/2 {Draw by adjudication}
        if "Finished game" in line:
            update_pentanomial(line, rounds)

    now = datetime.datetime.now()
    if now >= end_time:
        print("{} is past end time {}".format(now, end_time))

    return {"task_alive": True}


def launch_cutechess(
    cmd, remote, result, spsa_tuning, games_to_play, batch_size, tc_limit
):
    spsa = {"w_params": [], "b_params": [], "num_games": games_to_play}

    if spsa_tuning:
        # Request parameters for next game
        t0 = datetime.datetime.utcnow()
        req = send_api_post_request(remote + "/api/request_spsa", result).json()
        print(
            "Fetched SPSA parameters successfully in %ss"
            % ((datetime.datetime.utcnow() - t0).total_seconds())
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
        + ["option.%s=%d" % (x["name"], round(x["value"])) for x in w_params]
        + cmd[idx + 1 :]
    )
    idx = cmd.index("_spsa_")
    cmd = (
        cmd[:idx]
        + ["option.%s=%d" % (x["name"], round(x["value"])) for x in b_params]
        + cmd[idx + 1 :]
    )

    print(cmd)
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    )

    task_state = {"task_alive": False}
    try:
        task_state = parse_cutechess_output(
            p, remote, result, spsa, spsa_tuning, games_to_play, batch_size, tc_limit
        )
    except Exception as e:
        print("Exception running games")
        traceback.print_exc(file=sys.stderr)

    kill_process(p)
    return task_state


def run_games(worker_info, password, remote, run, task_id):
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
    if not "pentanomial" in input_stats:
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

    start_game_index = task_id * task["num_games"] + input_total_games
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
            results.append("option.%s=%s" % (param, val[0]))
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
            except:
                print("Note: failed to remove an old engine binary " + str(old_engine))
                pass

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
            zipball = "cutechess-cli-linux-%s.zip" % (platform.architecture()[0])
        setup(zipball, testing_dir)
        zip_file = ZipFile(zipball)
        zip_file.extractall()
        zip_file.close()
        os.remove(zipball)
        os.chmod(cutechess, os.stat(cutechess).st_mode | stat.S_IEXEC)

    # verify that an available cutechess matches the required minimum version
    verify_required_cutechess(cutechess)

    # clean up old networks (keeping the 20 most recent)
    networks = glob.glob(os.path.join(testing_dir, "nn-*.nnue"))
    if len(networks) > 20:
        networks.sort(key=os.path.getmtime)
        for old_net in networks[:-20]:
            try:
                os.remove(old_net)
            except:
                print("Note: failed to remove an old network " + str(old_net))
                pass

    # Add EvalFile with full path to cutechess options, and download networks if not already existing
    net_base = required_net(base_engine)
    if net_base:
        base_options = base_options + [
            "option.EvalFile=%s" % (os.path.join(testing_dir, net_base))
        ]
    net_new = required_net(new_engine)
    if net_new:
        new_options = new_options + [
            "option.EvalFile=%s" % (os.path.join(testing_dir, net_new))
        ]

    for net in [net_base, net_new]:
        if net:
            if not os.path.exists(os.path.join(testing_dir, net)) or not validate_net(
                testing_dir, net
            ):
                download_net(remote, testing_dir, net)
                if not validate_net(testing_dir, net):
                    raise Exception("Failed to validate the network: %s " % (net))

    # pgn output setup
    pgn_name = "results-" + worker_info["unique_key"] + ".pgn"
    if os.path.exists(pgn_name):
        os.remove(pgn_name)
    pgnfile = os.path.join(testing_dir, pgn_name)

    # Verify signatures are correct
    verify_signature(
        new_engine,
        run["args"]["new_signature"],
        remote,
        result,
        games_concurrency * threads,
    )
    base_nps = verify_signature(
        base_engine,
        run["args"]["base_signature"],
        remote,
        result,
        games_concurrency * threads,
    )

    # Benchmark to adjust cpu scaling
    scaled_tc, tc_limit = adjust_tc(
        run["args"]["tc"], base_nps, int(worker_info["concurrency"])
    )
    result["nps"] = base_nps
    result["ARCH"] = ARCH

    print("Running %s vs %s" % (run["args"]["new_tag"], run["args"]["base_tag"]))

    threads_cmd = []
    if not any("Threads" in s for s in new_options + base_options):
        threads_cmd = ["option.Threads=%d" % (threads)]

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

        batch_size = games_concurrency * 32  # update frequency

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
                "file=%s" % (book),
                "format=%s" % (book[-3:]),
                "order=random",
                "plies=%d" % (plies),
                "start=%d" % (1 + start_game_index // 2),
            ]
        else:
            assert False

        # Run cutechess-cli binary
        cmd = (
            [
                cutechess,
                "-repeat",
                "-rounds",
                str(int(games_to_play / 2)),
                "-games",
                " 2",
                "-tournament",
                "gauntlet",
            ]
            + pgnout
            + ["-site", "https://tests.stockfishchess.org/tests/view/" + run["_id"]]
            + [
                "-event",
                "Batch %d: %s vs %s"
                % (task_id, make_player("new_tag"), make_player("base_tag")),
            ]
            + ["-srand", "%d" % run_seed]
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
                "cmd=%s" % (new_engine_name),
            ]
            + new_options
            + ["_spsa_"]
            + [
                "-engine",
                "name=Base-" + run["args"]["resolved_base"][:10],
                "cmd=%s" % (base_engine_name),
            ]
            + base_options
            + ["_spsa_"]
            + ["-each", "proto=uci", "tc=%s" % (scaled_tc)]
            + nodestime_cmd
            + threads_cmd
            + book_cmd
        )

        task_status = launch_cutechess(
            cmd,
            remote,
            result,
            spsa_tuning,
            games_to_play,
            batch_size,
            tc_limit * games_to_play / min(games_to_play, games_concurrency),
        )
        if not task_status.get("task_alive", False):
            break

        games_remaining -= games_to_play
        start_game_index += games_to_play

    return pgnfile
