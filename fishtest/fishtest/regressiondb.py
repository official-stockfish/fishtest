class RegressionDb:
  def __init__(self, db):
    self.db = db
    self.regression_data = self.db['regression_data']

  def get(self, test_type):
  	data = self.regression_data.find_one({"test_type": test_type})
  	if data:
  		return data["data"]
	else:
		return None
  	
  def save(self, test_type, data):
  	self.regression_data.update({"test_type": test_type}, 
  		{"test_type": test_type, "data": data}, True)