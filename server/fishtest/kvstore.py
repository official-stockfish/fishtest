from fishtest.schemas import kvstore_schema
from vtjson import validate


class KeyValueStore:
    def __init__(self, db, collection="kvstore"):
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

    def get(self, key, default):
        try:
            return self[key]
        except KeyError:
            return default
