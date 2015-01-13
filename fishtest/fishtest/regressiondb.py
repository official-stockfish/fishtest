import json, csv, datetime
from bson import ObjectId

class RegressionDb:
  def __init__(self, db):
    self.db = db
    self.regression_data = self.db['regression_data']

  def get(self, test_type, json_output=False):
    data = self.regression_data.find({"test_type": test_type})
    if data:
      arr = []
      for d in data:
        if not json_output:
          arr.append({"_id": d["_id"], "data": d["data"]})
        else:
          arr.append(d["data"])

      return arr
    else:
      return None
  
  def parse_jl_csv(self, data):
    arr = []
    for d in csv.reader(data, delimiter=","):
      obj = {}
      obj["sha"] = d[0].strip()
      obj["date_committed"] = d[1].strip()
      obj["elo"] = d[2].strip()
      obj["error"] = d[3].strip()
      obj["points"] = d[4].strip()
      arr.append(obj)

    return arr

  def save(self, test_type, data, username):
    if test_type == "jl":
      data["data"] = self.parse_jl_csv(data["data"].split("\n"))

    data["date_saved"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    
    self.regression_data.save(
      {"test_type": test_type,
       "data": data})

  def delete(self, _id):
    self.regression_data.remove({"_id": ObjectId(_id)})
