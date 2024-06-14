import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import requests

start_dir = Path().cwd()

WORKER_URL = "https://github.com/official-monty/montytest/archive/master.zip"


def do_restart():
    """Restarts the worker, using the same arguments"""
    args = sys.argv[:]
    args.insert(0, sys.executable)
    if sys.platform == "win32":
        args = ['"{}"'.format(arg) for arg in args]

    os.chdir(start_dir)
    os.execv(sys.executable, args)  # This does not return!


def update(restart=True, test=False):
    worker_dir = Path(__file__).resolve().parent
    update_dir = Path(tempfile.mkdtemp(dir=worker_dir))
    worker_zip = update_dir / "wk.zip"

    try:
        response = requests.get(WORKER_URL)
        response.raise_for_status()
    except Exception as e:
        print(
            "Failed to download {}:\n".format(WORKER_URL),
            e,
            sep="",
            file=sys.stderr,
        )
        shutil.rmtree(update_dir)
        return None
    else:
        with open(worker_zip, "wb+") as f:
            f.write(response.content)

    with ZipFile(worker_zip) as zip_file:
        zip_file.extractall(update_dir)
    prefix = os.path.commonprefix([n.filename for n in zip_file.infolist()])
    worker_src = update_dir / prefix / "worker"
    from worker import (  # we do the import here to avoid issues with circular imports
        verify_sri,
    )

    if not verify_sri(worker_src):
        shutil.rmtree(update_dir)
        return None
    if not test:
        # Delete the "packages" folder to only have new files after an upgrade.
        packages_dir = worker_dir / "packages"
        if packages_dir.exists():
            try:
                shutil.rmtree(packages_dir)
            except Exception as e:
                print(
                    "Failed to delete the folder {}:\n".format(packages_dir),
                    e,
                    sep="",
                    file=sys.stderr,
                )
        if sys.version_info < (3, 8):
            from distutils.dir_util import copy_tree

            copy_tree(str(worker_src), str(worker_dir))
        else:
            shutil.copytree(worker_src, worker_dir, dirs_exist_ok=True)

    else:
        file_list = os.listdir(worker_src)
    shutil.rmtree(update_dir)

    # Rename the testing_dir to backup possible user custom files
    # and to trigger the download of updated files.
    # The worker runs games from the "testing" folder so change the folder.
    os.chdir(worker_dir)
    testing_dir = worker_dir / "testing"
    if testing_dir.exists():
        time_stamp = str(datetime.now(timezone.utc).timestamp())
        bkp_testing_dir = worker_dir / ("_testing_" + time_stamp)
        testing_dir.replace(bkp_testing_dir)
        testing_dir.mkdir()
        # Delete old engine binaries
        for engine in bkp_testing_dir.glob("monty_*"):
            try:
                engine.unlink()
            except Exception as e:
                print(
                    "Failed to delete the engine binary {}:\n".format(engine),
                    e,
                    sep="",
                    file=sys.stderr,
                )
        # Delete old networks.
        for network in bkp_testing_dir.glob("nn-*.network"):
            try:
                network.unlink()
            except Exception as e:
                print(
                    "Failed to delete the network file {}:\n".format(network),
                    e,
                    sep="",
                    file=sys.stderr,
                )
        # Clean up old folder backups (keeping the num_bkps most recent).
        num_bkps = 3
        for old_bkp_dir in sorted(
            worker_dir.glob("_testing_*"), key=os.path.getmtime, reverse=True
        )[num_bkps:]:
            try:
                shutil.rmtree(old_bkp_dir)
            except Exception as e:
                print(
                    "Failed to remove the old backup folder {}:\n".format(old_bkp_dir),
                    e,
                    sep="",
                    file=sys.stderr,
                )

    print("start_dir: {}".format(start_dir))
    if restart:
        do_restart()

    if test:
        return file_list


if __name__ == "__main__":
    update(False)
