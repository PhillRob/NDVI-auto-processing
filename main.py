# packages
import ee
import datetime
import json
import numpy as np
from PIL import Image
import urllib
# import FireHR for high resolution images; install of package does not work yet

# ee.Authenticate()
ee.Initialize()

# variables
## import AOI and set geometry
with open('DQ.geojson') as f:
    data = json.load(f)
geometry = data['features'][0]['geometry']

## set dates for analysis
py_date = datetime.datetime.utcnow()
ee_date = ee.Date(py_date)
# print(ee_date)
start_date = ee.Date(py_date - datetime.timedelta(days=150))
end_date = ee_date


# cloud masking function
def mask_cloud_and_shadows(image):
    qa = image.select('QA60')

    # Bits 10 and 11 are clouds and cirrus
    cloud_bitmask = 1 << 10
    cirrus_bitmask = 1 << 11

    # Both flags should be set to zero, indicating clear conditions
    mask = qa.bitwiseAnd(cloud_bitmask).eq(0).And(qa.bitwiseAnd(cirrus_bitmask).eq(0))

    return image.updatemask(mask).divide(10000).copyProperties(image, ['system:time_start'])

# NDVI function
def add_NDVI(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi')
    ndvi02 = ndvi.gt(0.2)
    ndvi_img = image.addBands(ndvi).updateMask(ndvi02)
    ndvi02_area = ndvi02.multiply(ee.Image.pixelArea()).rename('ndvi02_area')

    # adding area of vegetation as a band
    ndvi_img = ndvi_img.addBands(ndvi02_area)

    # calculate ndvi > 0.2 area
    ndviStats = ndvi02_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=10,
        maxPixels=10**13
    )

    image = image.set(ndviStats)

    # calculate area of AOI
    area = image.select('B1').multiply(0).add(1).multiply(ee.Image.pixelArea()).rename('area')

    # calculate area
    img_stats = area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=10,
        maxPixels=10**13
    )
    image = image.set(img_stats)

    a = image.getNumber('ndvi02_area').divide(image.getNumber('area')).multiply(100)
    b = image.getNumber('ndvi02_area')

    rel_cover = image.select('B1').multiply(0).add(a).rename('rel_ndvi')
    image = image.addBands(rel_cover)
    image = image.addBands(ndvi)

    thres = ndvi.gte(0.2).rename('thres')
    image = image.addBands(thres)
    image = image.addBands(b)
    return image

# save as function: takes download url of a npy file and saves it as jpg
def save_as_jpg(url, filename):
    array_file = urllib.request.urlretrieve(url, filename)
    img_array = np.load(array_file[0])
    img_jpg = Image.fromarray(img_array.astype(np.uint8))
    img_jpg.save(f'{ filename }.jpg')

# download image collection for the whole range of dates
collection = (ee.ImageCollection('COPERNICUS/S2')
              .filterDate(start_date, end_date)
              .filterBounds(geometry)
              .map(lambda image: image.clip(geometry))
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 1)))

# select images from collection
ndvi_collection = collection.map(add_NDVI)
ndvi_img_start = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(0))
ndvi_img_end = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(ndvi_collection.size().subtract(1)))

# calculate difference between the two datasets
decline_img = ndvi_img_start.select('thres').subtract(ndvi_img_end.select('thres'))
growth_img = ndvi_img_end.select('thres').subtract(ndvi_img_start.select('thres'))
#TODO: export as jpg. We need to generate a JPG map in a d good resolution.
# desired output is: 300DPI, A5, basemap google satellite without labels, increase and decrease overlays.

# get the images from GEE? in from of URLS
growth_url = growth_img.getDownloadURL({'format': 'NPY'})
decline_url = decline_img.getDownloadURL({'format': 'NPY'})

# save JPG's
save_as_jpg(decline_url, 'decline')


# TODO: if new data then do analysis condition
# TODO: run analayis over the 4 data sets with the dynamic dates
# TODO: save output maps and stats to disk but discard raw data
# TODO: chart changes changes over time


### SCRAP!!!!####
# def format_function(table, row_id, col_id):
#     rows = table.distinct(row_id)
#     joined = ee.Join.saveAll('matches').apply(
#         primary=rows,
#         secondary=table,
#         condition=ee.Filter.equals(
#             leftField=row_id,
#             rightField=row_id
#         )
#     )
#     return joined.map(lambda row: ((value := ee.List(row.get('matches'))
#                                     .map(lambda feature: (feature := ee.Feature(feature),
#                                                           [feature.get(col_id), feature.get('ndvi')])[-1])))[-1])
# def merge_function(table, row_id):
#     return table.map(lambda feature: (id := feature.get(row_id),
#                                       all_keys := feature.toDictionary().keys().remove(row_id),
#                                       substr_keys := ee.List(all_keys.map(lambda val: ee.String(val).slice(0, 8))),
#                                       unique_keys := substr_keys.distinct(),
#                                       pairs := unique_keys.map(lambda key: (matches := feature.toDictionary().select(all_keys)))))

# ------> ee.Reducer  not recognized by by Python <-----
# triplets = ndvi_collection.map(lambda image: image.select('ndvi').reduceRegions(
#     collection=geometry,
#     reducer=ee.Reducer.first().setOutputs(['ndvi']),
#     scale=10
# )).map(lambda feature: (ndvi := ee.List([feature.get('ndvi'), -9999])).reduce(ee.Reducer.firstNonNull(),
#                                                                               feature.set(
#                                                                                   {'ndvi': ndvi,
#                                                                                    'imageID': image.id()}
#                                                                               )))[-1].flatten()

# format = format_function
# sentinelResults = format(triplets, 'id', 'imageID')


# Map data
# geometry = data['features'][0]['geometry']['coordinates']

# get timeframe specified by user as variable
# possible options:
## july 2016, november 2016, last year, two weeks

# function get newest date from month
# parameter: month, region
## return latest image date

# function new image data available
# params (timeframe identifier if july 2016, november 2016, last year, two weeks); data file; region
# TODO
## if identifier july2016
#### compare newest july data to last july data from file; return true/false
## if identifier november2016
#### compare newest november data to last july data from file; return true/false
## if identifier last year
#### compare last year to most recent date in file return true/false

## if identifier two weeks
#### compare newest date to most recent date in file return true/false

# function get satellite pictures to compare
# parameters: (identifier if july 2016, november 2016, last year, two weeks); data file; region
## if new image data available
#### if identifier july2016
###### update datafile
###### return july 2016 and current july
#### if identifier november2016
###### update datafile
###### return november2016 and current november
#### if identifier last year
###### update datafile
###### return last year image and newest image
#### if identifier two weeks
###### update datafile
###### return image two weeks ago and newest image


# function to mask cloud and shadows
# param: image
# return: updated image without cloud and shadows

# function to add NDVI and calculate area
# param: image
# return: image with ndvi

# TODO
# function get cloud cover
# parameter image
## return cloud cover percentage

# check if new image data available with the according function
# if no new satellite data:
## do nothing
# if new satellite data:
## get satellite pictures to compare and save them in variables

# TODO
# call cloud cover function
# if cloud cover  over 30%:
## no report
# else  comment cloud cover percentage in report

# get satellite pictures to compare
# apply ndvi function to start date and end date image
# apply cloud mask to start date and end date image
# create triplets
# format triplets
# merge images

# calculate cover in %
# calculate change
# data tables of the raw numbers in the report probably with pandas

# create image from difference between start and end image possibly with the Python Image Library
# or with the thumbnail function in gee

# save image as png save the filename to the data file so we can later generate a pdf from the generated images

# send email with pdf via smtpd library
