#!/usr/bin/env python3

from pymongo import MongoClient

conn = MongoClient("localhost")

db = conn["fishtest_new"]

db.drop_collection("pgns")

db.create_collection("pgns", capped=True, size=50000)
