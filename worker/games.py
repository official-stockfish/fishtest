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
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from base64 import b64decode
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Queue
from zipfile import ZipFile

try:
    import requests
except ImportError:
    from packages import requests

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
FASTCHESS_KILL_TIMEOUT = 15.0
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


def format_returncode(r):
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


def cache_read(cache, name):
    """Read a binary blob of data from a global cache on disk, None if not available"""
    if cache == "":
        return None

    try:
        return (Path(cache) / name).read_bytes()
    except Exception:
        return None


def cache_write(cache, name, data):
    """Write a binary blob of data to a global cache on disk in an atomic way, skip if not available"""
    if cache == "":
        return

    try:
        temp_file = tempfile.NamedTemporaryFile(dir=cache, delete=False)
        temp_file.write(data)
        temp_file.flush()
        os.fsync(temp_file.fileno())  # Ensure data is written to disk
        temp_file.close()

        # try linking, which is atomic, and will fail if the file exists
        try:
            os.link(temp_file.name, Path(cache) / name)
        except OSError:
            pass

        # Remove the temporary file
        os.remove(temp_file.name)
    except Exception:
        return


def cache_remove(cache, name):
    """Remove a file from the global cache on disk"""
    if cache == "":
        return

    try:
        (Path(cache) / name).unlink()
    except Exception:
        return


# For background see:
# https://stackoverflow.com/questions/16511337/correct-way-to-try-except-using-python-requests-module
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
    except json.JSONDecodeError:
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
    pattern = re.compile(r"(EvalFile\w*)\s+.*\s+(nn-[a-f0-9]{12}.nnue)")
    print("Obtaining EvalFile of {}...".format(engine.name))
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
            "UCI exited with non-zero code {}".format(format_returncode(p.returncode))
        )

    return nets


def required_nets_from_source():
    """Parse evaluate.h and ucioption.cpp to find default nets"""
    nets = []
    pattern = re.compile("nn-[a-f0-9]{12}.nnue")
    # NNUE code after binary embedding (Aug 2020)
    with open("evaluate.h", "r") as srcfile:
        for line in srcfile:
            if "EvalFileDefaultName" in line and "define" in line:
                m = pattern.search(line)
                if m:
                    nets.append(m.group(0))
    if nets:
        return nets

    # NNUE code before binary embedding (Aug 2020)
    with open("ucioption.cpp", "r") as srcfile:
        for line in srcfile:
            if "EvalFile" in line and "Option" in line:
                m = pattern.search(line)
                if m:
                    nets.append(m.group(0))

    return nets


def fetch_validated_net(remote, testing_dir, net, global_cache):
    content = cache_read(global_cache, net)

    if content is None:
        url = f"{remote}/api/nn/{net}"
        print(f"Downloading {net}")
        content = requests_get(url, allow_redirects=True, timeout=HTTP_TIMEOUT).content
        if not is_valid_net(content, net):
            return False
        cache_write(global_cache, net, content)
    else:
        if not is_valid_net(content, net):
            print(f"Removing invalid {net} from global cache")
            cache_remove(global_cache, net)
            return False
        print(f"Using {net} from global cache")

    (testing_dir / net).write_bytes(content)
    return True


def is_valid_net(content, net):
    hash = hashlib.sha256(content).hexdigest()
    return hash[:12] == net[3:15]


def validate_net(testing_dir, net):
    content = (testing_dir / net).read_bytes()
    return is_valid_net(content, net)


def establish_validated_net(remote, testing_dir, net, global_cache):
    if (testing_dir / net).exists() and validate_net(testing_dir, net):
        return

    attempt = 0
    while True:
        attempt += 1
        try:
            if fetch_validated_net(remote, testing_dir, net, global_cache):
                return
            else:
                raise WorkerException(f"Failed to validate the network: {net}")
        except FatalException:
            raise
        except WorkerException:
            if attempt > 5:
                raise
            waitTime = UPDATE_RETRY_TIME * attempt
            print(
                f"Failed to fetch {net} in attempt {attempt},",
                f"trying in {waitTime} seconds",
            )
            time.sleep(waitTime)


def compute_bench_statistics(results, threads, depth, *, bench_nps=False):
    bench_nodes_values = [bn for _, bn in results]
    bench_time_values = [bt for bt, _ in results]
    bench_nps_values = [1000 * bn / bt / threads for bt, bn in results]

    mean_nodes = statistics.mean(bench_nodes_values)
    mean_time = statistics.mean(bench_time_values)
    mean_nps = statistics.mean(bench_nps_values)
    min_nps = min(bench_nps_values)
    max_nps = max(bench_nps_values)
    median_nps = statistics.median(bench_nps_values)
    std_nps = statistics.stdev(bench_nps_values) if len(bench_nps_values) > 1 else 0

    print(
        f"Bench for {'nps' if bench_nps else 'nodes'}\n"
        f"{'Concurrency':<15}: {len(results):15.2f}\n"
        f"{'Threads':<15}: {threads:15.2f}\n"
        f"{'Depth':<15}: {depth:15.2f}\n"
        f"{'Mean nodes':<15}: {mean_nodes:15.2f}\n"
        f"{'Mean time (ms)':<15}: {mean_time:15.2f}\n"
        f"{'Mean nps':<15}: {mean_nps:15.2f}\n"
        f"{'Median nps':<15}: {median_nps:15.2f}\n"
        f"{'Min nps':<15}: {min_nps:15.2f}\n"
        f"{'Max nps':<15}: {max_nps:15.2f}\n"
        f"{'Std nps':<15}: {std_nps:15.2f}\n"
        f"{'Std (%)':<15}: {100 * std_nps / mean_nps:15.2f}"
    )

    return mean_nps if bench_nps else None


def run_single_bench(engine, threads, depth):
    bench_time, bench_nodes = None, None

    try:
        p = subprocess.Popen(
            [engine, "bench", "16", str(threads), str(depth), "default", "depth"],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            universal_newlines=True,
            bufsize=1,
            close_fds=not IS_WINDOWS,
        )

        for line in iter(p.stderr.readline, ""):
            if "Total time (ms)" in line:
                bench_time = float(line.split(": ")[1].strip())
            if "Nodes searched" in line:
                bench_nodes = float(line.split(": ")[1].strip())

        p.wait()
    except (OSError, subprocess.SubprocessError) as e:
        raise e

    if bench_time is None or bench_nodes is None:
        message = f"Unable to parse bench output of {engine.name}"
        raise RunException(message)

    return bench_time, bench_nodes


def run_parallel_benches(engine, concurrency, threads, depth):
    with ProcessPoolExecutor(max_workers=concurrency) as executor:
        try:
            results = list(
                executor.map(
                    run_single_bench,
                    [engine] * concurrency,
                    [threads] * concurrency,
                    [depth] * concurrency,
                )
            )
        except Exception as e:
            message = f"Failed to run engine bench: {str(e)}"
            raise WorkerException(message, e=e)

    return results


def verify_signature(engine, signature, games_concurrency, threads):
    cpu_features = "?"
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
                cpu_features = line.split(": ")[1].strip()
    if p.returncode != 0:
        message = (
            f"Compiler info exited with non-zero code {format_returncode(p.returncode)}"
        )
        raise WorkerException(message)

    # Validate the signature with threads = 1 and depth = 13
    # Preload also the CPU before the bench for NPS
    results_for_nodes = run_parallel_benches(engine, games_concurrency * threads, 1, 13)
    bench_nodes = results_for_nodes[0][1]

    if int(bench_nodes) != int(signature):
        message = (
            f"Wrong bench in {engine.name}, "
            f"user expected: {signature} but worker got: {int(bench_nodes)}"
        )
        raise RunException(message)

    # Get the NPS with the required number of threads and depth
    results_for_nps = run_parallel_benches(engine, games_concurrency, threads, 13)

    # Compute the statistics
    print(f"Statistics for {engine.name}:")
    compute_bench_statistics(results_for_nodes, 1, 13)
    bench_nps = compute_bench_statistics(results_for_nps, threads, 13, bench_nps=True)

    return bench_nps, cpu_features


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
    cd = Path.cwd()
    os.chdir(save_dir)
    zipball = io.BytesIO(blob)
    with ZipFile(zipball) as zip_file:
        zip_file.extractall()
        file_list = zip_file.infolist()
    os.chdir(cd)
    return file_list


def clang_props():
    """Parse the output of clang++ -E - -march=native -### and extract the available clang properties"""
    with subprocess.Popen(
        ["clang++", "-E", "-", "-march=native", "-###"],
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        close_fds=not IS_WINDOWS,
    ) as p:
        for line in iter(p.stderr.readline, ""):
            if "cc1" in line:
                tokens = line.split('" "')
                arch = [
                    tokens[i + 1]
                    for i, token in enumerate(tokens)
                    if token == "-target-cpu"
                ]
                arch = arch[0] if len(arch) else "None"
                flags = [
                    tokens[i + 1]
                    for i, token in enumerate(tokens)
                    if token == "-target-feature"
                ]
                flags = [flag[1:] for flag in flags if flag[0] == "+"]

    if p.returncode != 0:
        raise FatalException(
            "clang++ target query failed with return code {}".format(
                format_returncode(p.returncode)
            )
        )

    return {"flags": flags, "arch": arch}


def gcc_props():
    """Parse the output of g++ -Q -march=native --help=target and extract the available gcc properties"""
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
                flags.append(line.split()[0][2:])
            if "-march" in line and len(line.split()) == 2:
                arch = line.split()[1]

    if p.returncode != 0:
        raise FatalException(
            "g++ target query failed with return code {}".format(
                format_returncode(p.returncode)
            )
        )

    return {"flags": flags, "arch": arch}


def make_targets():
    """Parse the output of make help and extract the available targets"""
    try:
        with subprocess.Popen(
            ["make", "help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
            for line in iter(p.stderr.readline, ""):
                if "native" in targets and "get_native_properties.sh" in line:
                    targets.remove("native")
                    break

    except (OSError, subprocess.SubprocessError) as e:
        print("Exception while executing make help:\n", e, sep="", file=sys.stderr)
        raise FatalException("It appears 'make' is not properly installed")

    if p.returncode != 0:
        raise WorkerException(
            "make help failed with return code {}".format(
                format_returncode(p.returncode)
            )
        )

    return targets


def find_arch(compiler):
    """Find the best arch string based on the cpu/g++ capabilities and Makefile targets"""
    targets = make_targets()

    # recent SF support a native target
    if "native" in targets:
        print("Using native target architecture")
        return "native"

    # older SF will need to fall back to this implementation
    props = gcc_props() if compiler == "g++" else clang_props()

    if is_64bit():
        if (
            IS_MACOS
            and ("armv8" in props["arch"] or "apple-" in props["arch"])
            and "apple-silicon" in targets
        ):
            arch = "apple-silicon"
        elif (
            "avx512vnni" in props["flags"]
            and "avx512dq" in props["flags"]
            and "avx512f" in props["flags"]
            and "avx512bw" in props["flags"]
            and "avx512vl" in props["flags"]
            and "x86-64-vnni256" in targets
        ):
            arch = "x86-64-vnni256"
        elif (
            "avx512f" in props["flags"]
            and "avx512bw" in props["flags"]
            and "x86-64-avx512" in targets
        ):
            arch = "x86-64-avx512"
            arch = "x86-64-bmi2"  # use bmi2 until avx512 performance becomes actually better
        elif "avxvnni" in props["flags"] and "x86-64-avxvnni" in targets:
            arch = "x86-64-avxvnni"
        elif (
            "bmi2" in props["flags"]
            and "x86-64-bmi2" in targets
            and props["arch"] not in ["znver1", "znver2"]
        ):
            arch = "x86-64-bmi2"
        elif "avx2" in props["flags"] and "x86-64-avx2" in targets:
            arch = "x86-64-avx2"
        elif (
            "popcnt" in props["flags"]
            and "sse4.1" in props["flags"]
            and "x86-64-sse41-popcnt" in targets
        ):
            arch = "x86-64-sse41-popcnt"
        elif "ssse3" in props["flags"] and "x86-64-ssse3" in targets:
            arch = "x86-64-ssse3"
        elif (
            "popcnt" in props["flags"]
            and "sse3" in props["flags"]
            and "x86-64-sse3-popcnt" in targets
        ):
            arch = "x86-64-sse3-popcnt"
        else:
            if props["arch"] in targets:
                arch = props["arch"]
            else:
                arch = "x86-64"
    else:
        if (
            "popcnt" in props["flags"]
            and "sse4.1" in props["flags"]
            and "x86-32-sse41-popcnt" in targets
        ):
            arch = "x86-32-sse41-popcnt"
        elif "sse2" in props["flags"] and "x86-32-sse2" in targets:
            arch = "x86-32-sse2"
        else:
            arch = "x86-32"

    print("Available Makefile architecture targets: ", targets)
    print("Available g++/cpu properties: ", props)
    print("Determined the best architecture to be ", arch)

    return arch


def setup_engine(
    engine_path,
    remote,
    sha,
    repo_url,
    concurrency,
    compiler,
    global_cache,
    env,
):
    """Download and build sources in a temporary directory then move exe as engine_path"""
    worker_dir = engine_path.parents[1]
    testing_dir = engine_path.parent
    tmp_dir = Path(tempfile.mkdtemp(dir=worker_dir))

    try:
        blob = cache_read(global_cache, sha + ".zip")

        if blob is None:
            item_url = github_api(repo_url) + "/zipball/" + sha
            print("Downloading {}".format(item_url))
            blob = requests_get(item_url).content
            blob_needs_write = True
        else:
            blob_needs_write = False
            print("Using {} from global cache".format(sha + ".zip"))

        file_list = unzip(blob, tmp_dir)
        # once unzipped without error we can write as needed
        if blob_needs_write:
            cache_write(global_cache, sha + ".zip", blob)

        build_dir = (
            tmp_dir / os.path.commonprefix([n.filename for n in file_list]) / "src"
        )
        os.chdir(build_dir)

        for net in required_nets_from_source():
            print("Build uses default net:", net)
            establish_validated_net(remote, testing_dir, net, global_cache)
            shutil.copyfile(testing_dir / net, net)

        arch = find_arch(compiler)

        if compiler == "g++":
            comp = "mingw" if IS_WINDOWS else "gcc"
        elif compiler == "clang++":
            comp = "clang"

        # skip temporary the profiled build for apple silicon, see
        # https://stackoverflow.com/questions/71580631/how-can-i-get-code-coverage-with-clang-13-0-1-on-mac
        make_cmd = "build" if arch == "apple-silicon" else "profile-build"
        cmd = [
            "make",
            f"-j{concurrency}",
            f"{make_cmd}",
            f"ARCH={arch}",
            f"COMP={comp}",
        ]

        with subprocess.Popen(
            cmd,
            env=env,
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
        if p.returncode != 0:
            raise WorkerException("Executing {} failed. Error: {}".format(cmd, errors))

        cmd = ["make", "strip", f"COMP={comp}"]
        try:
            p = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise FatalException(
                f"Executing {' '.join(cmd)} raised Exception: {type(e).__name__}: {e}",
                e=e,
            )
        if p.returncode != 0:
            raise FatalException(
                f"Executing {' '.join(cmd)} failed. Error: {p.stderr.decode().strip()}",
            )

        # We called setup_engine() because the engine was not cached.
        # Only another worker running in the same folder can have built the engine.
        if engine_path.exists():
            raise FatalException("Another worker is running in the same directory!")
        else:
            (build_dir / "stockfish").with_suffix(EXE_SUFFIX).replace(engine_path)
    finally:
        os.chdir(worker_dir)
        shutil.rmtree(tmp_dir)


def kill_process(p):
    p_name = os.path.basename(p.args[0])
    print("Killing {} with PID {}... ".format(p_name, p.pid), end="", flush=True)
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
            "\nException killing {} with PID {}, possibly already terminated:\n".format(
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


def parse_fastchess_output(
    p,
    current_state,
    remote,
    result,
    spsa_tuning,
    games_to_play,
    batch_size,
    tc_limit,
    pgn_file,
):
    finished_task_message = (
        "The server told us that no more games are needed for the current task."
    )
    hash_pattern = re.compile(r"(Base|New)-[a-f0-9]+")

    def shorten_hash(match):
        word = match.group(0).split("-")
        return "-".join([word[0], word[1][:10]])

    saved_stats = copy.deepcopy(result["stats"])

    # patterns used to obtain fastchess WLD and ptnml results from the following block of info:
    # --------------------------------------------------
    # Results of New-e443b2459e vs Base-e443b2459e (0.601+0.006, 1t, 16MB, UHO_Lichess_4852_v1.epd):
    # Elo: -9.20 +/- 20.93, nElo: -11.50 +/- 26.11
    # LOS: 19.41 %, DrawRatio: 42.35 %, PairsRatio: 0.88
    # Games: 680, Wins: 248, Losses: 266, Draws: 166, Points: 331.0 (48.68 %)
    # Ptnml(0-2): [43, 61, 144, 55, 37], WL/DD Ratio: 4.76
    # --------------------------------------------------
    pattern_WLD = re.compile(
        r"Games: ([0-9]+), Wins: ([0-9]+), Losses: ([0-9]+), Draws: ([0-9]+), Points: ([0-9.]+) \("
    )
    pattern_ptnml = re.compile(
        r"Ptnml\(0-2\): \[([0-9]+), ([0-9]+), ([0-9]+), ([0-9]+), ([0-9]+)\]"
    )
    fastchess_WLD_results = None
    fastchess_ptnml_results = None
    patterns_fastchess_error = (
        # Warning; New-SHA doesn't have option ThreatBySafePawn
        re.compile(r"Warning;.*doesn't have option"),
        # Warning; Invalid value for option P: -354
        re.compile(r"Warning;.*Invalid value"),
        # Warning; Illegal move e2e4 played by ...
        re.compile(r"Warning;.*Illegal move"),
        # Warning; Illegal pv move e2e4 pv; ...
        re.compile(r"Warning;.*Illegal pv move"),
    )

    q = Queue()
    t_output = threading.Thread(target=enqueue_output, args=(p.stdout, q), daemon=True)
    t_output.start()
    t_error = threading.Thread(target=enqueue_output, args=(p.stderr, q), daemon=True)
    t_error.start()

    end_time = datetime.now(timezone.utc) + timedelta(seconds=tc_limit)
    print("TC limit {} End time: {}".format(tc_limit, end_time))

    num_games_updated = 0
    while datetime.now(timezone.utc) < end_time:
        if current_state["task_id"] is None:
            # This task is no longer necessary
            print(finished_task_message)
            return False
        try:
            line = q.get_nowait().strip()
        except Empty:
            if p.poll() is not None:
                break
            time.sleep(0.1)
            continue

        line = hash_pattern.sub(shorten_hash, line)
        print(line, flush=True)

        # Do we have a pgn crc?
        if "has CRC32:" in line:
            pgn_file["CRC"] = line.split()[-1]

        # Have we reached the end of the match? Then just exit.
        if "Finished match" in line:
            if num_games_updated == games_to_play:
                print("Finished match cleanly")
            else:
                raise WorkerException(
                    "Finished match uncleanly {} vs. required {}".format(
                        num_games_updated, games_to_play
                    )
                )

        # Check line for fastchess errors.
        if any(pattern.search(line) for pattern in patterns_fastchess_error):
            message = r"fastchess says: '{}'".format(line)
            raise RunException(message)

        # Parse line like this:
        # Finished game 1 (stockfish vs base): 0-1 {White disconnects}
        if "disconnect" in line or "stall" in line:
            result["stats"]["crashes"] += 1

        if "on time" in line or "timeout" in line:
            result["stats"]["time_losses"] += 1

        # fastchess WLD and pentanomial output parsing.
        m = pattern_WLD.search(line)
        if m:
            try:
                fastchess_WLD_results = {
                    "games": int(m.group(1)),
                    "wins": int(m.group(2)),
                    "losses": int(m.group(3)),
                    "draws": int(m.group(4)),
                    "points": float(m.group(5)),
                }
            except Exception as e:
                raise WorkerException(
                    "Failed to parse WLD line: {} leading to: {}".format(line, str(e))
                )

        m = pattern_ptnml.search(line)
        if m:
            try:
                fastchess_ptnml_results = [int(m.group(i)) for i in range(1, 6)]
            except Exception as e:
                raise WorkerException(
                    "Failed to parse ptnml line: {} leading to: {}".format(line, str(e))
                )

        # If we have parsed the block properly let's update results.
        if (fastchess_ptnml_results is not None) and (
            fastchess_WLD_results is not None
        ):
            result["stats"]["pentanomial"] = [
                fastchess_ptnml_results[i] + saved_stats["pentanomial"][i]
                for i in range(5)
            ]

            result["stats"]["wins"] = (
                fastchess_WLD_results["wins"] + saved_stats["wins"]
            )
            result["stats"]["losses"] = (
                fastchess_WLD_results["losses"] + saved_stats["losses"]
            )
            result["stats"]["draws"] = (
                fastchess_WLD_results["draws"] + saved_stats["draws"]
            )

            if spsa_tuning:
                spsa = result["spsa"]
                spsa["wins"] = fastchess_WLD_results["wins"]
                spsa["losses"] = fastchess_WLD_results["losses"]
                spsa["draws"] = fastchess_WLD_results["draws"]

            num_games_finished = fastchess_WLD_results["games"]

            assert (
                2 * sum(result["stats"]["pentanomial"])
                == result["stats"]["wins"]
                + result["stats"]["losses"]
                + result["stats"]["draws"]
            )
            assert num_games_finished == 2 * sum(fastchess_ptnml_results)
            assert num_games_finished <= num_games_updated + batch_size
            assert num_games_finished <= games_to_play

            fastchess_ptnml_results = None
            fastchess_WLD_results = None

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
                            print(finished_task_message)
                            return False
                        update_succeeded = True
                        num_games_updated = num_games_finished
                        break
                    time.sleep(UPDATE_RETRY_TIME)
                if not update_succeeded:
                    raise WorkerException("Too many failed update attempts")
                else:
                    current_state["last_updated"] = datetime.now(timezone.utc)

                if (Path(__file__).resolve().parent / "fish.exit").is_file():
                    raise WorkerException("Task stopped by 'fish.exit'")

    else:
        raise WorkerException(
            "{} is past end time {}".format(datetime.now(timezone.utc), end_time)
        )

    return True


def launch_fastchess(
    cmd,
    current_state,
    remote,
    result,
    spsa_tuning,
    games_to_play,
    batch_size,
    tc_limit,
    pgn_file,
):
    if spsa_tuning:
        # Request parameters for next game.
        req = send_api_post_request(remote + "/api/request_spsa", result)
        if "error" in req:
            raise WorkerException(req["error"])

        if not req["task_alive"]:
            # This task is no longer necessary
            print(
                "The server told us that no more games are needed for the current task."
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

    # Run fastchess binary.
    # Stochastic rounding and probability for float N.p: (N, 1-p); (N+1, p)
    idx = cmd.index("_spsa_")
    cmd = (
        cmd[:idx]
        + [
            "option.{}={}".format(
                x["name"], math.floor(x["value"] + random.uniform(0, 1))
            )
            for x in w_params
        ]
        + cmd[idx + 1 :]
    )
    idx = cmd.index("_spsa_")
    cmd = (
        cmd[:idx]
        + [
            "option.{}={}".format(
                x["name"], math.floor(x["value"] + random.uniform(0, 1))
            )
            for x in b_params
        ]
        + cmd[idx + 1 :]
    )

    # print(cmd)
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
                task_alive = parse_fastchess_output(
                    p,
                    current_state,
                    remote,
                    result,
                    spsa_tuning,
                    games_to_play,
                    batch_size,
                    tc_limit,
                    pgn_file,
                )
            finally:
                # We nicely ask fastchess to stop.
                try:
                    send_sigint(p)
                except Exception as e:
                    print("\nException in send_sigint:\n", e, sep="", file=sys.stderr)
                # now wait...
                print("\nWaiting for fastchess to finish... ", end="", flush=True)
                try:
                    p.wait(timeout=FASTCHESS_KILL_TIMEOUT)
                except subprocess.TimeoutExpired:
                    print("timeout", flush=True)
                    kill_process(p)
                else:
                    print("done", flush=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(
            "Exception starting fastchess:\n",
            e,
            sep="",
            file=sys.stderr,
        )
        raise WorkerException("Unable to start fastchess. Error: {}".format(str(e)))

    return task_alive


def run_games(
    worker_info,
    current_state,
    password,
    remote,
    run,
    task_id,
    pgn_file,
    global_cache,
):
    # This is the main fastchess driver.
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
    run_seed = int(hashlib.sha1(run["_id"].encode("utf-8")).hexdigest(), 16) % (2**64)

    def format_fastchess_options(options):
        return [
            f"option.{key}={value}"
            for token in options.split()
            for key, value in [token.split("=")]
        ]

    new_options = format_fastchess_options(new_options)
    base_options = format_fastchess_options(base_options)

    # Clean up old engines (keeping the num_bkps most recent).
    worker_dir = Path(__file__).resolve().parent
    testing_dir = worker_dir / "testing"
    num_bkps = 50
    try:
        engines = sorted(
            testing_dir.glob("stockfish_*" + EXE_SUFFIX),
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

    def create_environment():
        # OS and TEMP are necessary for msys2
        white_set = {"PATH", "OS", "TEMP"}
        env = {k: v for k, v in os.environ.items() if k in white_set}
        env["CXXFLAGS"] = "-DNNUE_EMBEDDING_OFF"

        # Do not hash directories such as PATH and TEMP
        hash_set = {"OS", "CXXFLAGS"}
        hashed_env = {k: v for k, v in env.items() if k in hash_set}

        env_hash = hashlib.sha256(str(hashed_env).encode()).hexdigest()[0:10]
        return env, env_hash

    env, env_hash = create_environment()

    # build signature
    bs = (
        worker_info["compiler"]
        + "_"
        + str(".".join([str(s) for s in worker_info["gcc_version"]]))
        + "_env_"
        + env_hash
    )
    # Create new engines.
    sha_new = run["args"]["resolved_new"]
    sha_base = run["args"]["resolved_base"]

    new_engine_name = "stockfish_" + sha_new + "_" + bs
    base_engine_name = "stockfish_" + sha_base + "_" + bs

    new_engine = (testing_dir / new_engine_name).with_suffix(EXE_SUFFIX)
    base_engine = (testing_dir / base_engine_name).with_suffix(EXE_SUFFIX)

    # Build from sources new and base engines as needed.
    if not new_engine.exists():
        setup_engine(
            new_engine,
            remote,
            sha_new,
            repo_url,
            worker_info["concurrency"],
            worker_info["compiler"],
            global_cache,
            env,
        )
    if not base_engine.exists():
        setup_engine(
            base_engine,
            remote,
            sha_base,
            repo_url,
            worker_info["concurrency"],
            worker_info["compiler"],
            global_cache,
            env,
        )

    os.chdir(testing_dir)

    # Download the opening book if missing in the directory.
    if not (testing_dir / book).exists() or (testing_dir / book).stat().st_size == 0:
        zipball = book + ".zip"
        blob = download_from_github(zipball)
        unzip(blob, testing_dir)

    # Clean up the old networks (keeping the num_bkps most recent)
    num_bkps = 10
    for old_net in sorted(
        testing_dir.glob("nn-*.nnue"), key=os.path.getmtime, reverse=True
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

    # Add EvalFile* with full path to fastchess options, and download the networks if missing.
    for option, net in required_nets(base_engine).items():
        base_options.append("option.{}={}".format(option, net))
        establish_validated_net(remote, testing_dir, net, global_cache)

    for option, net in required_nets(new_engine).items():
        new_options.append("option.{}={}".format(option, net))
        establish_validated_net(remote, testing_dir, net, global_cache)

    # PGN files output setup.
    pgn_name = "results-" + worker_info["unique_key"] + ".pgn"
    pgn_file["name"] = testing_dir / pgn_name
    pgn_file["CRC"] = None
    try:
        pgn_file["name"].unlink()
    except FileNotFoundError:
        pass

    # Verify that the signatures are correct.
    print("Benchmarking worker and verifying signature...", flush=True)
    run_errors = []
    try:
        base_nps, cpu_features = verify_signature(
            base_engine,
            run["args"]["base_signature"],
            games_concurrency,
            threads,
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
                games_concurrency,
                threads,
            )
        except RunException as e:
            run_errors.append(str(e))
        except WorkerException as e:
            raise e

    # Handle exceptions if any.
    if run_errors:
        raise RunException("\n".join(run_errors))

    if base_nps < 208082 / (1 + 3 * math.tanh((worker_concurrency - 1) / 8)):
        message = (
            f"This machine is too slow ({base_nps} nps / thread) "
            f"to run fishtest effectively - sorry!"
        )
        raise FatalException(message)
    # fishtest with Stockfish 11 had 1.6 Mnps as reference nps and
    # 0.7 Mnps as threshold for the slow worker.
    # also set in rundb.py and delta_update_users.py
    factor = 691680 / base_nps

    # Adjust CPU scaling.
    _, tc_limit_ltc = adjust_tc("60+0.6", factor)
    scaled_tc, tc_limit = adjust_tc(run["args"]["tc"], factor)
    scaled_new_tc = scaled_tc
    if "new_tc" in run["args"]:
        scaled_new_tc, new_tc_limit = adjust_tc(run["args"]["new_tc"], factor)
        tc_limit = (tc_limit + new_tc_limit) / 2

    result["worker_info"]["nps"] = float(base_nps)
    result["worker_info"]["ARCH"] = cpu_features

    threads_cmd = []
    if not any("Threads" in s for s in new_options + base_options):
        threads_cmd = ["option.Threads={}".format(threads)]

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

        # Run fastchess binary.
        fastchess_path = (testing_dir / "fastchess").with_suffix(EXE_SUFFIX)
        cmd = (
            [
                str(fastchess_path),
                "-recover",
                "-repeat",
                "-games",
                "2",
                "-rounds",
                str(int(games_to_play) // 2),
            ]
            + [
                "-ratinginterval",
                "1",
                "-scoreinterval",
                "1",
                "-autosaveinterval",
                "0",
                "-report",
                "penta=true",
            ]
            + pgnout
            + ["-crc32", "pgn=true"]
            + [
                "-site",
                f"{remote.replace(':80', '').replace(':443', '')}/tests/view/"
                + run["_id"],
            ]
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
                "cmd={}".format(new_engine),
                "dir=.",
            ]
            + new_options
            + ["_spsa_"]
            + [
                "-engine",
                "name=Base-" + run["args"]["resolved_base"],
                "tc={}".format(scaled_tc),
                "cmd={}".format(base_engine),
                "dir=.",
            ]
            + base_options
            + ["_spsa_"]
            + ["-each", "proto=uci"]
            + nodestime_cmd
            + threads_cmd
            + book_cmd
        )

        task_alive = launch_fastchess(
            cmd,
            current_state,
            remote,
            result,
            spsa_tuning,
            games_to_play,
            batch_size,
            tc_limit * max(8, games_to_play / games_concurrency),
            pgn_file,
        )

        games_remaining -= games_to_play
        start_game_index += games_to_play

        if not task_alive:
            break

    return
