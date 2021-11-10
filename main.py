# packages
import ee
import datetime
import json
import sys
import numpy as np
from PIL import Image
import urllib
import folium
import io
# import FireHR for high resolution images; install of package only works on linux
# get timeframe through command line arguments
timeframe = 'nov_2016'
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
if timeframe == 'two_weeks':
    start_date = ee.Date(py_date - datetime.timedelta(days=14))
    end_date = ee_date
elif timeframe =='one_year':
    current_year = py_date.year
    start_date = ee.Date(py_date.replace(year=current_year-1))
    end_date = ee_date
elif timeframe == 'nov_2016':
    start_date = ee.Date(py_date.replace(year=2016, month=11))
    end_date = ee.Date(py_date.replace(month=11))
elif timeframe == 'july_2016':
    start_date = ee.Date(py_date.replace(year=2016, month=7))
    end_date = ee.Date(py_date.replace(month=7))
else:
    print(f'Command { timeframe } not found.')


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

    img1.save(f'growth_decline_{ timeframe }.jpg')

def get_veg_stats(image):
    date = image.get('system:time_start')
    name = image.get('name')
    pixelArea = ee.Image.pixelArea()
    fixArea = 5961031705.843
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi')
    image = image.addBands(ndvi)

    ndvi02 = ndvi.gte(0.2).rename('ndvi02')
    image = image.addBands(ndvi02).updateMask(ndvi02)

    NDVIstats = image.select('ndvi02').reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=geometry,
        scale=10,
        maxPixels=1e29
    )
    NDVIarea = ee.Number(NDVIstats.get('ndvi02')).multiply(100)

    return ee.Feature(None, {
        'NDVIarea': NDVIarea,
        'name': name,
        'system:time_start': date})


# download image collection for the whole range of dates
collection = (ee.ImageCollection('COPERNICUS/S2')
              .filterDate(start_date, end_date)
              .filterBounds(geometry)
              .map(lambda image: image.clip(geometry))
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 1)))

latest_image = ee.Image(collection.toList(collection.size()).get(collection.size().subtract(1)))
latest_image_date = latest_image.date().format("YYYY-MM-dd").getInfo()
new_report = False
# compare date of latest image with last recorded image
# if there is new data it will set new_report to True
json_file_name = 'data.json'

# with open(json_file_name, 'r', encoding='utf-8')as f:
#     date_data = json.load(f)
#     if timeframe not in data:
#         print('Timeframe not yet covered. Will be generated.')
#         new_report = True
#         date_data[timeframe] = latest_image_date
#     elif datetime.datetime.strptime(latest_image_date, '%Y-%m-%d') > datetime.datetime.strptime(date_data[timeframe],'%Y-%m-%d'):
#         print('New data. Updating File.')
#         new_report = True
#         date_data[timeframe] = latest_image_date
#     else:
#         print('No new data.')
#
# with open(json_file_name, 'w', encoding='utf-8') as f:
#     json.dump(data, f)

if new_report:
    # select images from collection
    ndvi_collection = collection.map(add_NDVI)
    ndvi_img_start = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(0))
    ndvi_img_end = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(ndvi_collection.size().subtract(1)))

    # calculate difference between the two datasets
    # growth_img = ndvi_img_start.select('thres').subtract(ndvi_img_end.select('thres'))
    # update mask  with eq(0)
    decline_img = ndvi_img_end.select('thres').subtract(ndvi_img_start.select('thres'))
    decline_img_mask = decline_img.neq(0)
    decline_img = decline_img.updateMask(decline_img_mask)
    # get the images from GEE? in from of URLS
    # growth_url = growth_img.getDownloadURL({'format': 'NPY'})
    decline_url = decline_img.getDownloadURL({'format': 'NPY'})


    # save JPG's
    save_as_jpg(decline_url, 'decline')
    # save_as_jpg(growth_url, 'growth')
    # change color of jpg's
    change_image_color_and_merge(['growth.jpg', 'decline.jpg'], [(0, 255, 0), (255, 0, 0)])

def add_ee_layer(self, ee_image_object, vis_params, name):
    """Adds a method for displaying Earth Engine image tiles to folium map."""
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; <a href="https://earthengine.google.com/">Google Earth Engine</a>',
        name=name,
        overlay=True,
        control=True
    ).add_to(self)
growth_vis_params = {
    'palette': ['00FF00', 'FF0000']
}
# latest_image_viz_params = {
#     'bands': ['B5', 'B4', 'B3'],
#     'min': 0,
#     'max': 0.5,
#     'gamma': [0.95, 1.1, 1]
# }
# Add Earth Engine drawing method to folium.
folium.Map.add_ee_layer = add_ee_layer

# Define the center of our map.
lat, lon = 24.67883191972247, 46.639354896561784
basemaps = {
    'Google Maps': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Maps',
        overlay = True,
        control = True
    ),
    'Google Satellite': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Satellite',
        overlay = True,
        control = True
    ),
    'Google Terrain': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Terrain',
        overlay = True,
        control = True
    ),
    'Google Satellite Hybrid': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Satellite',
        overlay = True,
        control = True
    ),
    'Esri Satellite': folium.TileLayer(
        tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr = 'Esri',
        name = 'Esri Satellite',
        overlay = True,
        control = True
    )
}

# TODO: Boundary of DQ to be added
# TODO: Change resolution
# TODO: Add statistics
my_map = folium.Map(location=[lat, lon], zoom_start=14, width=750, height=500, control_scale=True, zoom_control=False)
basemaps['Google Satellite'].add_to(my_map)
my_map.add_ee_layer(decline_img, growth_vis_params, 'Growth')
# my_map.add_ee_layer(latest_image, latest_image_viz_params, 'Growth')
img_data = my_map._to_png(1)
img = Image.open(io.BytesIO(img_data))
# rgb_img = img.convert('RGB')
img.save('map_growth_01.png')
my_map

# TODO: if new data then do analysis condition
# TODO: run analysis over the 4 data sets with the dynamic dates
# TODO: save output maps and stats to disk but discard raw data
# TODO: chart changes changes over time
# TODO: export as jpg. We need to generate a JPG map in a d good resolution.
# TODO: get scalebar
# desired output is: 300DPI, A5, basemap google satellite without labels, increase and decrease overlays.

basemaps['Google Maps'].add_to(my_map)

