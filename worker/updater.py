import datetime
import glob
import os
import platform
import shutil
import sys
from distutils.dir_util import copy_tree
from zipfile import ZipFile

import requests

start_dir = os.getcwd()

WORKER_URL = "https://github.com/glinscott/fishtest/archive/master.zip"


def do_restart():
    """Restarts the worker, using the same arguments"""
    args = sys.argv[:]
    args.insert(0, sys.executable)
    if sys.platform == "win32":
        args = ['"{}"'.format(arg) for arg in args]

    os.chdir(start_dir)
    os.execv(sys.executable, args)  # This does not return!


def update(restart=True, test=False):
    worker_dir = os.path.dirname(os.path.realpath(__file__))
    update_dir = os.path.join(worker_dir, "update")
    if not os.path.exists(update_dir):
        os.makedirs(update_dir)

    worker_zip = os.path.join(update_dir, "wk.zip")
    with open(worker_zip, "wb+") as f:
        f.write(requests.get(WORKER_URL).content)

    with ZipFile(worker_zip) as zip_file:
        zip_file.extractall(update_dir)
    prefix = os.path.commonprefix([n.filename for n in zip_file.infolist()])
    worker_src = os.path.join(update_dir, prefix, "worker")
    if not test:
        # Delete the "packages" folder to only have new files after an upgrade.
        packages_dir = os.path.join(worker_dir, "packages")
        if os.path.exists(packages_dir):
            try:
                shutil.rmtree(packages_dir)
            except Exception as e:
                print(
                    "Failed to delete the folder {}:\n".format(packages_dir),
                    e,
                    sep="",
                    file=sys.stderr,
                )
        copy_tree(worker_src, worker_dir)
    else:
        file_list = os.listdir(worker_src)
    shutil.rmtree(update_dir)

    # Rename the testing_dir to backup possible user custom files
    # and to trigger the download of updated files.
    # The worker runs games from the "testing" folder so change the folder.
    os.chdir(worker_dir)
    testing_dir = os.path.join(worker_dir, "testing")
    if os.path.exists(testing_dir):
        time_stamp = str(datetime.datetime.timestamp(datetime.datetime.utcnow()))
        bkp_testing_dir = os.path.join(worker_dir, "_testing_" + time_stamp)
        shutil.move(testing_dir, bkp_testing_dir)
        os.makedirs(testing_dir)
        # Delete old engine binaries
        engines = glob.glob(os.path.join(bkp_testing_dir, "stockfish_*"))
        for engine in engines:
            try:
                os.remove(engine)
            except Exception as e:
                print(
                    "Failed to delete the engine binary {}:\n".format(engine),
                    e,
                    sep="",
                    file=sys.stderr,
                )
        # Delete old networks.
        networks = glob.glob(os.path.join(bkp_testing_dir, "nn-*.nnue"))
        for network in networks:
            try:
                os.remove(network)
            except Exception as e:
                print(
                    "Failed to delete the network file {}:\n".format(network),
                    e,
                    sep="",
                    file=sys.stderr,
                )
        # Clean up old folder backups (keeping the num_bkps most recent).
        bkp_dirs = glob.glob(os.path.join(worker_dir, "_testing_*"))
        num_bkps = 3
        if len(bkp_dirs) > num_bkps:
            bkp_dirs.sort(key=os.path.getmtime)
            for old_bkp_dir in bkp_dirs[:-num_bkps]:
                try:
                    shutil.rmtree(old_bkp_dir)
                except Exception as e:
                    print(
                        "Failed to remove the old backup folder {}:\n".format(
                            old_bkp_dir
                        ),
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
