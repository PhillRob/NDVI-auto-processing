# packages
import ee
import datetime
import json
import numpy as np
from PIL import Image
import urllib
# import FireHR for high resolution images; install of package only works on linux

RED = (255, 0, 0)
GREEN = (0, 255, 0)

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
    img_jpg.show()

def change_image_color_and_merge(images, colors):
    img1 = Image.open(images[0])
    img2 = Image.open(images[1])
    img1 = img1.convert("RGB")
    img2 = img2.convert("RGB")

    data1 = img1.getdata()
    data2 = img2.getdata()
    new_image_data = []
    for item1, item2 in zip(data1, data2):
        # change all white (also shades of whites) pixels to yellow
        if 190 < item1[0] < 256:
            new_image_data.append(colors[0])
        elif 190 < item2[0] < 256:
            new_image_data.append(colors[1])
        else:
            new_image_data.append(item1)
    # update image data
    img1.putdata(new_image_data)

    # show image in preview
    # img1.show()

    img1.save('growth_decline.jpg')


# download image collection for the whole range of dates
collection = (ee.ImageCollection('COPERNICUS/S2')
              .filterDate(start_date, end_date)
              .filterBounds(geometry)
              .map(lambda image: image.clip(geometry))
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 1)))
latest_image = ee.Image(collection.toList(collection.size()).get(collection.size().subtract(1)))
latest_image_date = latest_image.date().format("YYYY-MM-dd").getInfo()


# compare date of latest image with last recorded image
# not complete yet
# with open('data.json', 'r+', encoding='utf-8') as f:
#     d = json.load(f)
#     if 'latest_image' in d:
#         previous_image_date = datetime.datetime.strptime(d['latest_image'], '%Y-%m-%d')
#     else:
#         print('No new data available.')
#     if datetime.datetime.strptime(latest_image_date, '%Y-%m-%d') > previous_image_date:
#         print('New data available.')
#         data = {'latest_image': latest_image_date}
#         json.dump(data, f, ensure_ascii=False, indent=4)
#     f.close()
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
save_as_jpg(growth_url, 'growth')
# change color of jpg's
change_image_color_and_merge(['growth.jpg', 'decline.jpg'], [(0, 255, 0), (255, 0, 0)])



# TODO: if new data then do analysis condition
# TODO: run analayis over the 4 data sets with the dynamic dates
# TODO: save output maps and stats to disk but discard raw data
# TODO: chart changes changes over time
