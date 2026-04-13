import random
import zlib

import numpy as np

from fishtest.spsa_workflow import (
    apply_spsa_result_updates,
    build_spsa_chart_payload,
    build_spsa_worker_step,
    clip_spsa_param_value,
    get_spsa_history_period,
)


def _pack_flips(flips):
    """
    This transforms a list of +-1 into a sequence of bytes
    with the meaning of the individual bits being 1:1, 0:-1.
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


def _generate_data(spsa, iter=None):
    result = {"w_params": [], "b_params": []}

    if iter is None:
        iter = spsa["iter"]

    for param in spsa["params"]:
        flip = random.choice((-1, 1))
        worker_step = build_spsa_worker_step(
            spsa,
            param,
            iter_value=iter,
            flip=flip,
        )
        result["w_params"].append(
            {
                "name": param["name"],
                "value": clip_spsa_param_value(param, worker_step["c"] * flip),
                **worker_step,
            }
        )
        result["b_params"].append(
            {
                "name": param["name"],
                "value": clip_spsa_param_value(param, -worker_step["c"] * flip),
            }
        )

    return result


def _add_to_history(spsa, num_games, w_params):
    n_params = len(spsa["params"])
    period = get_spsa_history_period(num_iter=num_games / 2, param_count=n_params)

    if len(spsa["params"]) != len(w_params):
        msg = (
            "SPSA history length mismatch: "
            f"{len(spsa['params'])} params, {len(w_params)} worker params"
        )
        raise ValueError(msg)

    if period <= 0:
        return

    if "param_history" not in spsa:
        spsa["param_history"] = []
    if len(spsa["param_history"]) + 1 <= spsa["iter"] / period:
        summary = [
            {"theta": spsa_param["theta"], "R": w_param["R"], "c": w_param["c"]}
            for spsa_param, w_param in zip(spsa["params"], w_params)
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

        result = spsa_results["wins"] - spsa_results["losses"]
        game_pairs = spsa_results["num_games"] // 2
        spsa["iter"] += game_pairs

        apply_spsa_result_updates(
            spsa,
            w_params,
            result=result,
            game_pairs=game_pairs,
        )

        _add_to_history(spsa, run["args"]["num_games"], w_params)

        self.buffer(run)

    def get_spsa_data(self, run_id):
        run = self.get_run(run_id)
        return build_spsa_chart_payload(run["args"].get("spsa"))
