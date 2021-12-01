# !/usr/bin/python3
# -*- coding: UTF-8 -*-
# packages package
import logging

import ee
import os
import folium
from send_email import *
import selenium.webdriver
from selenium.webdriver.firefox.options import Options
import time

logging.basicConfig(filename='ndvi-report-mailer.log', level=logging.DEBUG)

# ee.Authenticate()
ee.Initialize()

# variables
# import AOI and set geometry
with open('NDVI-auto-processing/Diplomatic Quarter.geojson') as f:
    geo_data = json.load(f)
geometry = geo_data['features'][0]['geometry']


# set dates for analysis
py_date = datetime.utcnow()
ee_date = ee.Date(py_date)
# print(ee_date)
start_date = ee.Date(py_date.replace(year=2016, month=7, day=1))
end_date = ee_date


july_2016_end = ee.Date(py_date.replace(month=7))

timeframes = {
    'two_weeks': {'start_date': (ee.Date(py_date - timedelta(days=14))), 'end_date': end_date},
    'one_year': {'start_date': ee.Date(py_date.replace(year=py_date.year - 1)), 'end_date': end_date},
    'nov_2016': {'start_date': ee.Date(py_date.replace(year=2016, month=11, day=1)), 'end_date': ee.Date(py_date.replace(month=11))},
    'july_2016': {'start_date': ee.Date(py_date.replace(year=2016, month=7, day=1)), 'end_date': ee.Date(py_date.replace(month=7))},
    'since_2016': {'start_date': ee.Date(py_date.replace(year=2016)), 'end_date': ee.Date(py_date)},
}


# cloud masking function
def maskS2clouds(image):
  qa = image.select('QA60')

  cloudBitMask = 1 << 10
  cirrusBitMask = 1 << 11

  mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))

  return image.updateMask(mask).divide(10000)

def get_cloud_stats(image):
    date = image.get('system:time_start')
    name = image.get('name')
    CloudStats = image.select('QA60').reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=geometry,
        scale=10,
        maxPixels=1e29
    )
    nonCloudArea = ee.Number(CloudStats.get('QA60')).multiply(100)
    return nonCloudArea
    # CALC DIFF
    # return ee.Feature(None, {
    #     'NDVIarea': NDVIarea,
    #     'name': name,
    #     'system:time_start': date})

# NDVI function
def add_NDVI(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi')
    ndvi02 = ndvi.gt(0.2)
    ndvi_img = image.addBands(ndvi).updateMask(ndvi02)  # TODO: low priority:vars not used
    ndvi02_area = ndvi02.multiply(ee.Image.pixelArea()).rename('ndvi02_area')

    # adding area of vegetation as a band
    ndvi_img = ndvi_img.addBands(ndvi02_area)  # TODO: low priority:vars not used

    # calculate ndvi > 0.2 area
    ndviStats = ndvi02_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=10,
        maxPixels=1e29
    )

    image = image.set(ndviStats)

    # calculate area of AOI
    area = image.select('B1').multiply(0).add(1).multiply(ee.Image.pixelArea()).rename('area')

    # calculate area
    img_stats = area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=10,
        maxPixels=1e29
    )
    image = image.set(img_stats)

    a = image.getNumber('ndvi02_area').divide(image.getNumber('area')).multiply(100)
    b = image.getNumber('ndvi02_area')

    # TODO: low priority: refactor! this is clunky and costly in terms of processing and storage. We do not need to have a band with a constant pixel value accorss the data set.
    rel_cover = image.select('B1').multiply(0).add(a).rename('rel_ndvi')
    image = image.addBands(rel_cover)
    image = image.addBands(ndvi)

    thres = ndvi.gte(0.2).rename('thres')  #TODO: low priority: clean up this is the same as on line 60
    image = image.addBands(thres)
    image = image.addBands(b)
    return image


def get_veg_stats(image):
    date = image.get('system:time_start')
    name = image.get('name')

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
    # the above is better area stats. so something similar for the overall area in the add_NDVI function


def add_ee_layer(self, ee_object, vis_params, name):
    """Adds a method for displaying Earth Engine image tiles to folium map."""
    try:
        # display ee.Image()
        if isinstance(ee_object, ee.image.Image):
            map_id_dict = ee.Image(ee_object).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name=name,
                overlay=True,
                control=True
            ).add_to(self)
        # display ee.ImageCollection()
        elif isinstance(ee_object, ee.imagecollection.ImageCollection):
            ee_object_new = ee_object.mosaic()
            map_id_dict = ee.Image(ee_object_new).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name=name,
                overlay=True,
                control=True
            ).add_to(self)
        # display ee.Geometry()
        elif isinstance(ee_object, ee.geometry.Geometry):
            folium.GeoJson(
                data=ee_object.getInfo(),
                name=name,
                overlay=True,
                control=True
            ).add_to(self)
        # display ee.FeatureCollection()
        elif isinstance(ee_object, ee.featurecollection.FeatureCollection):
            ee_object_new = ee.Image().paint(ee_object, 0, 2)
            map_id_dict = ee.Image(ee_object_new).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name=name,
                overlay=True,
                control=True
            ).add_to(self)

    except:
        print("Could not display {}".format(name))


# Add Earth Engine drawing method to folium.
folium.Map.add_ee_layer = add_ee_layer

growth_vis_params = {
    'min': -1,
    'max': 1,
    'palette': ['FF0000', '00FF00'],
}

geo_vis_params = {
    'opacity': 0.5,
    'palette': ['FFFFFF'],
}

# swap the coordinates because folium takes them the other way around
swapped_coords = [[x[1], x[0]] for x in geometry['coordinates'][0][0]]

basemaps = {
    'Google Maps': folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Maps',
        overlay=True,
        control=True,
    ),
    'Google Satellite': folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Satellite',
        overlay=True,
        control=True,
        control_scale=True,
    ),
    'Google Terrain': folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Terrain',
        overlay=True,
        control=True
    ),
    'Google Satellite Hybrid': folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Satellite',
        overlay=True,
        control=True
    ),
    'Esri Satellite': folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Esri Satellite',
        overlay=True,
        control=True
    )
}

# download image collection for the whole range of dates
collection = (ee.ImageCollection('COPERNICUS/S2')
              .filterDate(start_date, end_date)
              .filterBounds(geometry)
              .map(lambda image: image.clip(geometry))
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 1))
              )
print('Generating NDVI')

# select images from collection
ndvi_collection = collection.map(add_NDVI).map(maskS2clouds)

image_list = []
for timeframe in timeframes:
    timeframe_collection = collection.filterDate(timeframes[timeframe]['start_date'], timeframes[timeframe]['end_date'])
    ndvi_timeframe_collection = timeframe_collection.map(add_NDVI)
    ndvi_img_start = ee.Image(ndvi_timeframe_collection.toList(ndvi_timeframe_collection.size()).get(0))
    ndvi_img_end = ee.Image(ndvi_timeframe_collection.toList(ndvi_timeframe_collection.size()).get(ndvi_timeframe_collection.size().subtract(1)))

    latest_image = ee.Image(timeframe_collection.toList(timeframe_collection.size()).get(timeframe_collection.size().subtract(1)))
    first_image = ee.Image(timeframe_collection.toList(timeframe_collection.size()).get(0))

    latest_image_date = latest_image.date().format("dd.MM.YYYY").getInfo()
    first_image_date = first_image.date().format("dd.MM.YYYY").getInfo()

    polygon = ee.Geometry.Polygon(geometry['coordinates'][0][0])
    project_area = round(polygon.area().getInfo())

    cloud_image_first = maskS2clouds(ndvi_img_start)
    cloud_image_latest = maskS2clouds(ndvi_img_end)

    cloud_area_first = project_area - get_cloud_stats(cloud_image_first).getInfo()
    cloud_area_latest = project_area - get_cloud_stats(cloud_image_latest).getInfo()

    vegetation_start = get_veg_stats(first_image).getInfo()["properties"]["NDVIarea"]
    vegetation_end = get_veg_stats(latest_image).getInfo()["properties"]["NDVIarea"]
    area_change = vegetation_end - vegetation_start
    relative_change = 100 - (vegetation_end/vegetation_start) * 100
    vegetation_share_start = (vegetation_start/project_area) * 100
    vegetation_share_end = (vegetation_end/project_area) * 100
    vegetation_share_change = vegetation_share_end - vegetation_share_start

    # calculate difference between the two datasets
    growth_decline_img = ndvi_img_end.select('thres').subtract(ndvi_img_start.select('thres'))
    growth_decline_img_mask = growth_decline_img.neq(0)
    growth_decline_img = growth_decline_img.updateMask(growth_decline_img_mask)

    if area_change < 0:
        relative_change = -relative_change

    new_report = False
    # compare date of latest image with last recorded image
    # if there is new data it will set new_report to True
    json_file_name = 'output/data.json'
    screenshot_save_name = f'output/growth_decline_{timeframe}.png'
    with open(json_file_name, 'r', encoding='utf-8')as f:
        data = json.load(f)
        if timeframe not in data.keys():
            print(f'Timeframe {timeframe} not yet covered. Will be generated.')
            new_report = True
            data[timeframe] = {}
            data[timeframe]['start_date'] = timeframes[timeframe]['start_date'].format("dd.MM.YYYY").getInfo()
            data[timeframe]['end_date'] = timeframes[timeframe]['end_date'].format("dd.MM.YYYY").getInfo()
            data[timeframe]['start_date_satellite'] = first_image_date
            data[timeframe]['end_date_satellite'] = latest_image_date
            data[timeframe]['vegetation_start'] = vegetation_start
            data[timeframe]['vegetation_end'] = vegetation_end
            data[timeframe]['vegetation_share_start'] = vegetation_share_start
            data[timeframe]['vegetation_share_end'] = vegetation_share_end
            data[timeframe]['vegetation_share_change'] = vegetation_share_change
            data[timeframe]['project_area'] = project_area/(1000*1000)
            data[timeframe]['area_change'] = area_change
            data[timeframe]['relative_change'] = relative_change
            data[timeframe]['path'] = screenshot_save_name
            data[timeframe]['project_name'] = geo_data['name']

        elif datetime.strptime(latest_image_date, '%d.%m.%Y') > datetime.strptime(data[timeframe]['end_date'],'%d.%m.%Y'):
            print('New data. Updating File.')
            logging.debug(f'New data in timeframe: {timeframe}')
            new_report = True
            data[timeframe]['end_date'] = latest_image_date.format("dd.MM.YYYY").getInfo()
            data[timeframe]['start_date'] = first_image_date.format("dd.MM.YYYY").getInfo()
            data[timeframe]['start_date_satellite'] = first_image_date
            data[timeframe]['end_date_satellite'] = latest_image_date
            data[timeframe]['vegetation_start'] = vegetation_start
            data[timeframe]['vegetation_end'] = vegetation_end
            data[timeframe]['vegetation_share_start'] = vegetation_share_start
            data[timeframe]['vegetation_share_end'] = vegetation_share_end
            data[timeframe]['vegetation_share_change'] = vegetation_share_change
            data[timeframe]['project_area'] = project_area/(1000*1000)
            data[timeframe]['area_change'] = area_change
            data[timeframe]['relative_change'] = relative_change
            data[timeframe]['path'] = screenshot_save_name
            data[timeframe]['project_name'] = geo_data['name']
        else:
            print(f'All data for {timeframe} is up to date')
    with open(json_file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    # Define middle point of our map
    if new_report:
        html_map = 'map.html'

        centroid = ee.Geometry(geometry).centroid().getInfo()['coordinates']
        # get coordinates from centroid for folium
        lat, lon = centroid[1], centroid[0]
        my_map = folium.Map(location=[lat, lon], zoom_control=False, control_scale=True)
        basemaps['Google Satellite'].add_to(my_map)

        white_polygon = ee.geometry.Geometry(geo_json=geometry)

        my_map.add_ee_layer(white_polygon, geo_vis_params, 'Half opaque polygon')
        my_map.add_ee_layer(growth_decline_img, growth_vis_params, 'Growth and decline image')

        # fit bounds for optimal zoom level
        my_map.fit_bounds(swapped_coords)

        my_map.save(html_map)
        my_map

        options = Options()
        options.add_argument('--headless')

        driver = selenium.webdriver.Firefox(options=options)
        driver.set_window_size(1200, 1200)

        image_list.append(screenshot_save_name)
        driver.get(f'file:///{os.path.dirname(os.path.abspath("map.html"))}\\map.html')
        time.sleep(3)
        driver.save_screenshot(screenshot_save_name)
        driver.quit()
        # discard temporary data
        os.remove(html_map)
if new_report:
    sendEmail(sendtest, open_project_date('output/data.json'))
    logging.debug(f'New email sent on {str(datetime.today())}')
else:
    logging.debug(f'No new email on {str(datetime.today())}')

# TODO: current dataset with dataset 2016
# TODO: remove clouds from calculation
# TODO: chart changes changes over time