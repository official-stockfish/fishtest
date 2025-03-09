import random
import zlib

import numpy as np


def _pack_flips(flips):
    """
    This transforms a list of +-1 into a sequence of bytes
    with the meaning of the indivual bits being 1:1, 0:-1.
    """
    return np.packbits(np.array(flips, dtype=np.int8) == 1).tobytes() if flips else b""


def _unpack_flips(packed_flips, length=None):
    """
    The inverse function.
    """
    if not packed_flips:
        return []
    bits = np.unpackbits(np.frombuffer(packed_flips, dtype=np.uint8))
    flips = np.where(bits, 1, -1)
    return flips.tolist() if length is None else flips[:length].tolist()


def _param_clip(param, increment):
    return min(max(param["theta"] + increment, param["min"]), param["max"])


def _generate_data(spsa, iter=None):
    result = {"w_params": [], "b_params": []}

    if iter is None:
        iter = spsa["iter"]

    # Generate a set of tuning parameters
    iter_local = iter + 1  # start from 1 to avoid division by zero
    for param in spsa["params"]:
        c = param["c"] / iter_local ** spsa["gamma"]
        flip = random.choice((-1, 1))
        result["w_params"].append(
            {
                "name": param["name"],
                "value": _param_clip(param, c * flip),
                "R": param["a"] / (spsa["A"] + iter_local) ** spsa["alpha"] / c**2,
                "c": c,
                "flip": flip,
            }
        )
        # These are only used by the worker
        result["b_params"].append(
            {
                "name": param["name"],
                "value": _param_clip(param, -c * flip),
            }
        )

    return result


def _add_to_history(spsa, num_games, w_params):
    # Compute the update frequency so that the required storage does not depend
    # on the the number of parameters. We have to recompute this every time since
    # the user may have modified the run.
    n_params = len(spsa["params"])
    samples = 100 if n_params < 100 else 10000 / n_params if n_params < 1000 else 1
    period = num_games / 2 / samples

    # Now update if the time has come...
    if "param_history" not in spsa:
        spsa["param_history"] = []
    if len(spsa["param_history"]) + 1 <= spsa["iter"] / period:
        summary = [
            {"theta": spsa_param["theta"], "R": w_param["R"], "c": w_param["c"]}
            for w_param, spsa_param in zip(w_params, spsa["params"])
        ]
        spsa["param_history"].append(summary)


class SPSAHandler:
    def __init__(self, rundb):
        self.get_run = rundb.get_run
        if rundb.is_primary_instance():
            self.buffer = rundb.buffer
        self.active_run_lock = rundb.active_run_lock

    def request_spsa_data(self, run_id, task_id):
        with self.active_run_lock(run_id):
            return self.__request_spsa_data(run_id, task_id)

    def __request_spsa_data(self, run_id, task_id):
        run = self.get_run(run_id)
        task = run["tasks"][task_id]
        spsa = run["args"]["spsa"]

        # Check if the worker is still working on this task.
        if not task["active"]:
            info = "request_spsa_data: task {}/{} is not active".format(run_id, task_id)
            print(info, flush=True)
            return {"task_alive": False, "info": info}

        result = _generate_data(spsa)
        packed_flips = _pack_flips([w_param["flip"] for w_param in result["w_params"]])
        task["spsa_params"] = {}
        task["spsa_params"]["iter"] = spsa["iter"]
        task["spsa_params"]["packed_flips"] = packed_flips
        self.buffer(run)
        # The signature defends against server crashes and worker bugs
        sig = zlib.crc32(packed_flips)
        result["sig"] = sig
        result["task_alive"] = True
        return result

    def update_spsa_data(self, run_id, task_id, spsa_results):
        with self.active_run_lock(run_id):
            return self.__update_spsa_data(run_id, task_id, spsa_results)

    def __update_spsa_data(self, run_id, task_id, spsa_results):
        run = self.get_run(run_id)
        task = run["tasks"][task_id]
        spsa = run["args"]["spsa"]

        # Catch some issues which may occur after a server crash
        if "spsa_params" not in task:
            print(
                f"update_spsa_data: spsa_params not found for {run_id}/{task_id}. Skipping update...",
                flush=True,
            )
            return
        task_spsa_params = task["spsa_params"]
        # Make sure we cannot call update_spsa_data again with these data
        del task["spsa_params"]

        sig = spsa_results.get("sig", 0)
        if sig != zlib.crc32(task_spsa_params["packed_flips"]):
            print(
                f"update_spsa_data: spsa_params for {run_id}/{task_id}",
                "do not match the signature sent by the worker.",
                "Skipping update...",
                flush=True,
            )
            return

        # Reconstruct spsa data from the task data
        w_params = _generate_data(spsa, iter=task_spsa_params["iter"])["w_params"]
        flips = _unpack_flips(task_spsa_params["packed_flips"], length=len(w_params))
        for idx, w_param in enumerate(w_params):
            w_param["flip"] = flips[idx]
            del w_param["value"]  # for safety!

        # Update the current theta based on the results from the worker
        result = spsa_results["wins"] - spsa_results["losses"]
        spsa["iter"] += spsa_results["num_games"] // 2

        for idx, param in enumerate(spsa["params"]):
            R = w_params[idx]["R"]
            c = w_params[idx]["c"]
            flip = w_params[idx]["flip"]
            param["theta"] = _param_clip(param, R * c * result * flip)

        _add_to_history(spsa, run["args"]["num_games"], w_params)

        self.buffer(run)

    def get_spsa_data(self, run_id):
        run = self.get_run(run_id)
        return run["args"].get("spsa", {})
