from collections.abc import MutableMapping
from datetime import UTC

from bson.codec_options import CodecOptions
from fishtest.schemas import kvstore_schema
from pymongo import MongoClient
from vtjson import validate


class KeyValueStore(MutableMapping):
    def __init__(self, db=None, db_name=None, collection="kvstore"):
        self.conn = None
        if db is None:
            if db_name is None:
                raise ValueError("You must specify a db or a db name")
            self.conn = MongoClient("localhost")
            codec_options = CodecOptions(tz_aware=True, tzinfo=UTC)
            db = self.conn[db_name].with_options(codec_options=codec_options)
        self.__kvstore = db[collection]

    def __setitem__(self, key, value):
        document = {"_id": key, "value": value}
        validate(kvstore_schema, document)
        self.__kvstore.replace_one({"_id": key}, document, upsert=True)

    def __getitem__(self, key):
        document = self.__kvstore.find_one({"_id": key})
        if document is None:
            raise KeyError(key)
        else:
            return document["value"]

    def __delitem__(self, key):
        d = self.__kvstore.delete_one({"_id": key})
        if d.deleted_count == 0:
            raise KeyError(key)

    def __len__(self):
        return self.__kvstore.count_documents({})

    def __iter__(self):
        documents = self.__kvstore.find({}, {"value": 0, "_id": 1})
        for d in documents:
            yield d["_id"]

    def values(self):
        documents = self.__kvstore.find({}, {"value": 1, "_id": 0})
        for d in documents:
            yield d["value"]

    def items(self):
        documents = self.__kvstore.find()
        for d in documents:
            yield d["_id"], d["value"]

    def clear(self):
        self.__kvstore.delete_many({})

    def close(self):
        """Close the db connection if we own it
        but keep the underlying collection"""
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def drop(self):
        """Destructor!"""
        self.__kvstore.drop()
        self.close()
