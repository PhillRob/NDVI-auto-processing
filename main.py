# packages
import ee
import datetime
import json


ee.Authenticate()
ee.Initialize()


# variables
## import AOI
with open('DQ.geojson') as f:
    data = json.load(f)
## set dates for analysis
py_date = datetime.datetime.utcnow()
ee_date = ee.Date(py_date)
print(ee_date)

# Map data
# geometry = data['features'][0]['geometry']['coordinates']
# set startdate and enddate
# function to mask cloud and shadows
# param: image
# return: updated image without cloud and shadows


# function to add NDVI and calculate area
# param: image
# return: image with ndvi

# get image from startdate and end date param: date, geometry return: image
# apply cloud mask to start date and end date image
# apply ndvi function to start date and end date image


# create triplets. what exactly does that mean?
# format function params: table, rowId, colId
# apply format functions to triplets

# merge function params: table, rowId

#sentinelMerged = merge function

# create image from difference between start and end image possibly with the Python Image Library
# save image as png possibly add it to pdf with image results from other timeframes
# send email via smtpd library