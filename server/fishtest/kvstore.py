from datetime import UTC

from bson.codec_options import CodecOptions
from fishtest.schemas import kvstore_schema
from pymongo import MongoClient
from vtjson import validate

_missing_default = object()


class KeyValueStore:
    def __init__(self, db=None, db_name=None, collection="kvstore"):
        if db is None:
            conn = MongoClient("localhost")
            codec_options = CodecOptions(tz_aware=True, tzinfo=UTC)
            db = conn[db_name].with_options(codec_options=codec_options)
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

    def __contains__(self, key):
        try:
            self[key]
        except KeyError:
            return False
        return True

    def get(self, key, default=_missing_default):
        try:
            return self[key]
        except KeyError:
            if default != _missing_default:
                return default
            else:
                raise

    def pop(self, key, default=_missing_default):
        try:
            value = self[key]
            del self[key]
            return value
        except KeyError:
            if default != _missing_default:
                return default
            else:
                raise

    def items(self):
        documents = self.__kvstore.find()
        for d in documents:
            yield d["_id"], d["value"]

    def keys(self):
        for i in self.items():
            yield i[0]

    def values(self):
        for i in self.items():
            yield i[1]
