# packages
import ee
import datetime
import json


#ee.Authenticate()
ee.Initialize()


# variables
## import AOI
with open('test.json') as f:
    data = json.load(f)
## set dates for analysis
py_date = datetime.datetime.utcnow()
ee_date = ee.Date(py_date)
print(ee_date)


# Map data
