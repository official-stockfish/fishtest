#!/usr/bin/env python3

import bz2

import requests
from bson.binary import Binary
from pymongo import ASCENDING, MongoClient
from urllib.parse import urljoin

# fish_host = 'http://localhost:6543'
fish_host = "http://94.198.98.239"  # 'http://tests.stockfishchess.org'

conn = MongoClient("localhost")

# conn.drop_database('fish_clone')

db = conn["fish_clone"]

pgndb = db["pgns"]
runs = db["runs"]

pgndb.ensure_index([("run_id", ASCENDING)])


def main():
    """clone a fishtest database with PGNs and runs with the REST API"""

    skip = 0
    count = 0
    in_sync = False
    loaded = {}
    while True:
        api_url = urljoin(fish_host, f"/api/pgn_100/{skip}")
        pgn_list = requests.get(api_url).json()

        for pgn_file in pgn_list:
            print(pgn_file)
            if pgndb.find_one({"run_id": pgn_file}):
                print("Already copied: {}".format(pgn_file))
                if pgn_file not in loaded:
                    in_sync = True
                    break
            else:
                run_id = pgn_file.split("-")[0]
                if not runs.find_one({"_id": run_id}):
                    print("New run: " + run_id)
                    run_url = urljoin(fish_host, f"/api/get_run/{run_id}")
                    run = requests.get(api_url).json()
                    runs.insert(run)
                pgn_url = urljoin(fish_host, f"/api/pgn/{pgn_file}")
                pgn = requests.get(api_url)
                pgndb.insert(
                    dict(pgn_bz2=Binary(bz2.compress(pgn.content)), run_id=pgn_file)
                )
                loaded[pgn_file] = True
                count += 1
        skip += len(pgn_list)
        if in_sync or len(pgn_list) < 100:
            break

    print("Copied:  {:6d} PGN files (~ {:8d} games)".format(count, 250 * count))
    count = pgndb.count()
    print("Database:{:6d} PGN files (~ {:8d} games)".format(count, 250 * count))
    count = runs.count()
    print("Database:{:6d} runs".formt(count))


if __name__ == "__main__":
    main()
