# GenDb is used to store general name/value pairs

class GenDb:
  def __init__(self, db):
    self.db = db
    self.general = self.db['general']

  def get(self, name):
    q['name'] = name
    return self.general.find(q, limit=1)

  def delete(self, name):
    self.general.delete_one({'name', name})

  def update(self, name, value):
    result = self.general.update_one(
        {"name" : name},
        {"$set": {'value' : value}},
        upsert=True)
    return result

