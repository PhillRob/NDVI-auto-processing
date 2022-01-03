# !/usr/bin/python3
# -*- coding: UTF-8 -*-
# packages package
import logging

import datetime
import ee
import folium
import json
import logging
import os
import PIL
from fpdf import FPDF
import selenium.webdriver
from selenium.webdriver.firefox.options import Options
import time
from send_email import *
import sys


local_test_run = False
email_test_run = False

if len(sys.argv) >= 2:
    # if test run is declared true through the command line we just run local tests
    local_test_run = int(sys.argv[1])
if len(sys.argv) >= 3:
    email_test_run = int(sys.argv[2])

logging.basicConfig(filename='ndvi-report-mailer.log', level=logging.DEBUG)

if local_test_run:
    GEOJSON_PATH = 'Diplomatic Quarter.geojson'
    JSON_FILE_NAME = '../output/data.json'
    SCREENSHOT_SAVE_NAME = f'../output/growth_decline_'
    PDF_PATH = f'../output/pdf_growth_decline_{datetime.utcnow().strftime("%d.%m.%Y")}.pdf'
    CREDENTIALS_PATH = '../credentials/credentials.json'
else:
    GEOJSON_PATH = 'NDVI-auto-processing/Diplomatic Quarter.geojson'
    JSON_FILE_NAME = 'output/data.json'
    SCREENSHOT_SAVE_NAME = f'output/growth_decline_'
    PDF_PATH = f'output/pdf_growth_decline_{datetime.utcnow().strftime("%d.%m.%Y")}.pdf'
    CREDENTIALS_PATH = 'credentials/credentials.json'

# ee.Authenticate()
ee.Initialize()

# variables
# import AOI and set geometry
with open(GEOJSON_PATH) as f:
    geo_data = json.load(f)
geometry = geo_data['features'][0]['geometry']


# set dates for analysis
py_date = datetime.utcnow()
ee_date = ee.Date(py_date)
# print(ee_date)
start_date = ee.Date(py_date.replace(year=2016, month=7, day=1))
end_date = ee_date

# 2018-03-12 has clouds
timeframes = {
    'two_weeks': {'start_date': (ee.Date(py_date - timedelta(days=14))), 'end_date': end_date},
    'one_year': {'start_date': ee.Date(py_date - timedelta(days=365)), 'end_date': end_date},
    'since_2016': {'start_date': ee.Date(py_date - timedelta(days=(365 * 5))), 'end_date': ee.Date(py_date)},
    'nov_2016': {'start_date': ee.Date(py_date.replace(year=2016, month=11, day=1)), 'end_date': ee.Date(py_date.replace(month=11))},
    'july_2016': {'start_date': ee.Date(py_date.replace(year=2016, month=7, day=1)), 'end_date': ee.Date(py_date.replace(month=7))},
}
head_text = {
    'two_weeks': 'Short-term: One-week',
    'one_year': 'Medium-term: One-year',
    'since_2016': 'Long-term: Five-year',
    'nov_2016': 'Winter long-term: Five-year winter',
    'july_2016': 'Summer long-term: Five-year summer',
}
body_text = {
    'two_weeks': [
        '    - Compares current and previous data ',
        '    - Indicates immediate maintenance and construction challenges, and results',
        '    - Immediate irrigation and maintenance control, and private greening efforts',
        '    - Focus on managed vegetation (parks, roads,...)'
    ],
    'one_year': [
        '    - Compares current and last year\'s data',
        '    - Indicates medium-term trends for the same month (season)',
        '    - Shows trends in maintenance performance (irrigation, pruning, etc), and construction',
        '    - Indicative of environmental changes (weather, ground water, ...)'
    ],
    'since_2016': [
        '    - Compares current data with the first available data of the same month (season)',
        '    - Long-term trends in construction, maintenance, greening and environmental changes',
    ],
    'nov_2016': [
        '    - Compares current November data with first available November ',
        '    - Best-case setting: natural vegetation flourishes in November (lower temperature, ',
        '      increased rainfall probability) ',
        '    - Shows long term trends natural vegetation relating to environmental conditions and ',
        '      construction and long-term maintenance efforts ',
    ],
    'july_2016': [
        '    - Compares last July data with first available July',
        '    - Worst-case setting: water and heat stress peaks in July',
        '    - Shows long-term trends in managed vegetation ',
    ],
}

logos = ['static/bpla_logo_blau.png']

# cloud masking function
def maskS2clouds(image):
  qa = image.select('QA60')

  cloudBitMask = 1 << 10
  cirrusBitMask = 1 << 11

  mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))

  return image.updateMask(mask).divide(10000)


def get_project_area(image):
    date = image.get('system:time_start')
    name = image.get('name')
    project_stats = image.select('B1').reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=geometry,
        scale=10,
        maxPixels=1e29
    )
    project_area_size = ee.Number(project_stats.get('B1')).multiply(100)
    return ee.Feature(None, {
        'project_area_size': project_area_size,
        'name': name,
        'system:time_start': date
        }
    )


def get_cloud_stats(image):
    date = image.get('system:time_start')
    name = image.get('name')

    CloudStats = image.select('B1').reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=geometry,
        scale=10,
        maxPixels=1e29
    )
    nonCloudArea = ee.Number(CloudStats.get('B1')).multiply(100)
    # CALC DIFF
    return ee.Feature(None, {
        'nonCloudArea': nonCloudArea,
        'name': name,
        'system:time_start': date})


# NDVI function
def add_NDVI(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi')
    ndvi02 = ndvi.gt(0.2)
    #ndvi_img = image.addBands(ndvi).updateMask(ndvi02)  # TODO: low priority:vars not used
    ndvi02_area = ndvi02.multiply(ee.Image.pixelArea()).rename('ndvi02_area')

    # adding area of vegetation as a band
    #ndvi_img = ndvi_img.addBands(ndvi02_area)  # TODO: low priority:vars not used

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

    except Exception as e:
        print(f"Could not display {name}. Exception: {e}")
def footer(self):
    # Go to 1.5 cm from bottom
    self.set_y(-15)
    # Select Arial italic 8
    self.set_font('Arial', 'I', 8)
    if self.page_no() != 1:
        pdf.cell(txt=f'BPLA GmbH', ln=0, w=0)
        pdf.cell(txt=f'{self.page_no() - 1}', ln=0, w=0, align='C')
def pdf_add_image(pdf, image, pos, size):
    try:
        pdf.image(image, x=pos[0], y=pos[1], w=size[0], h=size[1])
    except Exception as e:
        print(f'Could not add image {image}. Error: {e}')


def generate_pdf(pdf, data, pdf_name, logos, head_text, body_text):
    # equates to one cm
    cm_in_pt = 28.3464566929
    font_size_normal = 11
    font_size_heading = 14
    font_size_intro_heading = 18
    line_space = font_size_normal/2 - 1
    logo_size = (int(cm_in_pt * 5.76), int(cm_in_pt * 2.4))
    # set starting point
    x = cm_in_pt
    y = cm_in_pt
    # intro page
    pdf.add_page()
    pdf.set_font('Arial', 'B', size=font_size_intro_heading)
    pdf_add_image(pdf, logos[0], (x, y), logo_size)
    y += logo_size[1] + font_size_intro_heading * 2
    pdf.set_xy(x, y)
    pdf.cell(txt=f'{geo_data["name"]}', ln=1, w=0)
    y += font_size_intro_heading * 2
    pdf.set_xy(x, y)
    pdf.cell(
        txt=f'Vegetation Cover Change Report',
        ln=1, w=0)
    y += font_size_intro_heading * 2
    pdf.set_xy(x, y)
    pdf.set_font('Arial', size=font_size_normal)
    pdf.cell(txt=f'{processing_date}',ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    pdf.cell(txt=f'v0.1', ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    pdf.cell(txt=f'To whom it may concern,',ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    pdf.cell(txt=f'Here we report the changes of vegetation cover in the Diplomatic', ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    pdf.cell(txt=f'Quarter. This report localises vegetation changes for five time periods by comparing vegetation',ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    pdf.cell(txt=f'maps of two dates and is published every 7 to 10 days based on new available data. The maps ', ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    pdf.cell(txt=f'show:',ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    first_point = f'    -Vegetation gain is green and vegetation loss is shown in read.'
    pdf.cell(txt=first_point,ln=1, w=0)
    y += font_size_normal * 2
    pdf.set_xy(x, y)
    second_point = f'    -Transparent areas have not changed between the two assessment dates.'
    pdf.cell(txt=second_point,ln=1, w=0)
    y = pdf.h / 2
    pdf.set_xy(x, y)
    for timeframe in data.keys():
        pdf.cell(
            txt=f'{head_text[timeframe]} vegetation evaluation ({data[timeframe]["start_date_satellite"]} to {data[timeframe]["end_date_satellite"]})',
            ln=1, w=0)
        y += font_size_normal + line_space
        pdf.set_xy(x, y)
        for text in body_text[timeframe]:
            pdf.cell(
                txt=f'{text}',
                ln=1, w=0)
            y += font_size_normal + line_space
            pdf.set_xy(x, y)
    pdf.add_page()
    y = cm_in_pt
    pdf.set_xy(x, y)
    pdf_add_image(pdf, logos[0], (x, y), logo_size)
    y += logo_size[1] + font_size_intro_heading * 2
    pdf.set_xy(x, y)

    FPDF.footer = footer
    for timeframe in data.keys():
        pdf.add_page()
        pdf.set_font('Arial', 'B',  size=font_size_heading)
        y = cm_in_pt
        pdf.set_xy(x, y)
        pdf_add_image(pdf, logos[0], (x, y), logo_size)
        y += logo_size[1] + font_size_heading * 2
        pdf.set_xy(x, y)
        pdf.multi_cell(
            txt=f'{data[timeframe]["project_name"]} {head_text[timeframe]} vegetation evaluation ({data[timeframe]["start_date_satellite"]} to {data[timeframe]["end_date_satellite"]})',
            w=0, h=font_size_heading+line_space)
        y += font_size_heading * 3
        pdf.set_xy(x, y)
        pdf.set_font('Arial', size=font_size_normal)
        pdf.cell(txt=f'Project area: {data[timeframe]["project_area"]:.2f} km²', ln=1, w=0)
        y += font_size_normal + line_space
        pdf.set_xy(x, y)
        pdf.cell(
            txt=f'Vegetation cover ({data[timeframe]["start_date"]}): {data[timeframe]["vegetation_start"]:,} m² ({data[timeframe]["vegetation_share_start"]:.2f}%)',
            ln=1, w=0)
        y += font_size_normal + line_space
        pdf.set_xy(x, y)
        pdf.cell(
            txt=f'Vegetation cover ({data[timeframe]["end_date"]}): {data[timeframe]["vegetation_end"]:,} m² ({data[timeframe]["vegetation_share_end"]:.2f}%)',
            ln=1, w=0)
        y += font_size_normal + line_space
        pdf.set_xy(x, y)
        pdf.cell(
            txt=f'Net vegetation change: {data[timeframe]["area_change"]:,} m² ({data[timeframe]["vegetation_share_change"]:.2f}%)',
            ln=1, w=0)
        y += font_size_normal + line_space
        pdf.set_xy(x, y)
        pdf.cell(
            txt=f'Vegetation gain (green): {data[timeframe]["vegetation_gain"]:,} m² ({data[timeframe]["vegetation_gain_relative"]:.2f}%)',
            ln=1, w=0)
        y += font_size_normal + line_space
        pdf.set_xy(x,y)
        pdf.cell(
            txt=f'Vegetation loss (red): {data[timeframe]["vegetation_loss"]:,} m² ({data[timeframe]["vegetation_loss_relative"]:.2f}%)',
            ln=1, w=0)
        y += font_size_normal + line_space
        pdf.set_xy(x,y)
        pdf.image(data[timeframe]["path"], x=cm_in_pt, y=y, w=pdf.w-(cm_in_pt * 2), h=pdf.w-(cm_in_pt * 2))
    pdf.output(pdf_name)

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

cloud_vis_params = {
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
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 3))
              )
ndvi_collection = collection.map(add_NDVI)
# select images from collection
cloud_mask_collection = collection.map(maskS2clouds)
cloud_collection = cloud_mask_collection.map(get_cloud_stats)
image_list = []

processing_date = py_date.strftime('%d.%m.%Y')
with open(JSON_FILE_NAME, 'r', encoding='utf-8') as f:
    data = json.load(f)
    if processing_date not in data.keys():
        data[processing_date] = {}
with open(JSON_FILE_NAME, 'w', encoding='utf-8') as f:
    json.dump(data, f)

# loop through available data sets
for timeframe in timeframes:
    timeframe_collection = collection.filterDate(timeframes[timeframe]['start_date'], timeframes[timeframe]['end_date'])
    ndvi_timeframe_collection = timeframe_collection.map(add_NDVI)
    ndvi_img_start = ee.Image(ndvi_timeframe_collection.toList(ndvi_timeframe_collection.size()).get(0))
    ndvi_img_end = ee.Image(ndvi_timeframe_collection.toList(ndvi_timeframe_collection.size()).get(ndvi_timeframe_collection.size().subtract(1)))

    # if there is no different image within that timeframe just take the next best
    if timeframe_collection.size().getInfo() != 0:
        latest_image = ee.Image(timeframe_collection.toList(timeframe_collection.size()).get(timeframe_collection.size().subtract(1)))
        first_image = ee.Image(timeframe_collection.toList(timeframe_collection.size()).get(0))

        latest_image_date = latest_image.date().format("dd.MM.YYYY").getInfo()
        first_image_date = first_image.date().format("dd.MM.YYYY").getInfo()
    else:
        latest_image = ee.Image(collection.toList(collection.size()).get(collection.size().subtract(1)))
        first_image = ee.Image(collection.toList(collection.size()).get(collection.size().subtract(3)))

        latest_image_date = latest_image.date().format("dd.MM.YYYY").getInfo()
        first_image_date = first_image.date().format("dd.MM.YYYY").getInfo()

        ndvi_img_start = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(
            ndvi_timeframe_collection.size().subtract(2)))
        ndvi_img_end = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(
            ndvi_timeframe_collection.size().subtract(1)))




    project_area = get_project_area(first_image).getInfo()['properties']['project_area_size']

    vegetation_start = get_veg_stats(first_image).getInfo()["properties"]["NDVIarea"]
    vegetation_end = get_veg_stats(latest_image).getInfo()["properties"]["NDVIarea"]
    area_change = vegetation_end - vegetation_start

    relative_change = 100 - (vegetation_end/vegetation_start) * 100
    vegetation_share_start = (vegetation_start/project_area) * 100
    vegetation_share_end = (vegetation_end/project_area) * 100
    vegetation_share_change = vegetation_share_end - vegetation_share_start

    cloud_image_first = maskS2clouds(first_image)
    cloud_image_latest = maskS2clouds(latest_image)

    # calculate both cloud images together
    cloud_first_image_mask = cloud_image_first.eq(0)
    cloud_latest_image_mask = cloud_image_latest.eq(0)
    first_cloud_masked_image = first_image.updateMask(cloud_first_image_mask)
    first_cloud_masked_image = first_cloud_masked_image.updateMask(cloud_latest_image_mask)
    latest_cloud_masked_image = latest_image.updateMask(cloud_first_image_mask)
    latest_cloud_masked_image = latest_cloud_masked_image.updateMask(cloud_latest_image_mask)

    # calculate difference between the two datasets
    growth_decline_img = ndvi_img_end.select('thres').subtract(ndvi_img_start.select('thres'))
    growth_decline_img_mask = growth_decline_img.neq(0)
    growth_mask = growth_decline_img.eq(1)
    decline_mask = growth_decline_img.eq(-1)
    growth_img = growth_decline_img.updateMask(growth_mask)
    decline_img = growth_decline_img.updateMask(decline_mask)
    growth_decline_img = growth_decline_img.updateMask(growth_decline_img_mask)

    vegetation_loss = ee.Number(decline_img.reduceRegion(reducer=ee.Reducer.count())).getInfo()['thres'] * 100
    vegetation_gain = ee.Number(growth_img.reduceRegion(reducer=ee.Reducer.count())).getInfo()['thres'] * 100
    vegetation_loss_relative = -vegetation_loss/project_area * 100
    vegetation_gain_relative = vegetation_gain / project_area * 100

    if area_change < 0:
        relative_change = -relative_change

    new_report = False

    # compare date of latest image with last recorded image
    # if there is new data it will set new_report to True
    json_file_name = JSON_FILE_NAME
    screenshot_save_name = f'{SCREENSHOT_SAVE_NAME}_{processing_date}_{timeframe}.png'

    with open(json_file_name, 'r', encoding='utf-8')as f:
        data = json.load(f)

        if timeframe not in data[processing_date].keys():
            print(f'Timeframe {timeframe} not yet covered. Will be generated.')
            new_report = True
            data[processing_date][timeframe] = {}
            data[processing_date][timeframe]['start_date'] = timeframes[timeframe]['start_date'].format("dd.MM.YYYY").getInfo()
            data[processing_date][timeframe]['end_date'] = timeframes[timeframe]['end_date'].format("dd.MM.YYYY").getInfo()
            data[processing_date][timeframe]['start_date_satellite'] = first_image_date
            data[processing_date][timeframe]['end_date_satellite'] = latest_image_date
            data[processing_date][timeframe]['vegetation_start'] = vegetation_start
            data[processing_date][timeframe]['vegetation_end'] = vegetation_end
            data[processing_date][timeframe]['vegetation_share_start'] = vegetation_share_start
            data[processing_date][timeframe]['vegetation_share_end'] = vegetation_share_end
            data[processing_date][timeframe]['vegetation_share_change'] = vegetation_share_change
            data[processing_date][timeframe]['project_area'] = project_area/(1000*1000)
            data[processing_date][timeframe]['area_change'] = area_change
            data[processing_date][timeframe]['relative_change'] = relative_change
            data[processing_date][timeframe]['vegetation_gain'] = vegetation_gain
            data[processing_date][timeframe]['vegetation_loss'] = vegetation_loss
            data[processing_date][timeframe]['vegetation_gain_relative'] = vegetation_gain_relative
            data[processing_date][timeframe]['vegetation_loss_relative'] = vegetation_loss_relative
            data[processing_date][timeframe]['path'] = screenshot_save_name
            data[processing_date][timeframe]['project_name'] = geo_data['name']
        else:
            print(f'All data for {timeframe} is up to date')
    with open(json_file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    # Define center of our map
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
        my_map.add_ee_layer(first_cloud_masked_image.select('B1'), cloud_vis_params, 'Cloudcover image')

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
    pdf = FPDF(orientation='P', format='A4', unit='pt')
    generate_pdf(pdf, data[processing_date], PDF_PATH, logos, head_text, body_text)

if not local_test_run:
    if new_report:
        sendEmail(sendtest, open_project_date(JSON_FILE_NAME)[processing_date], CREDENTIALS_PATH, PDF_PATH)
        logging.debug(f'New email sent on {str(datetime.today())}')
    else:
        logging.debug(f'No new email on {str(datetime.today())}')

if email_test_run:
    sendEmail(sendtest, open_project_date(JSON_FILE_NAME)[processing_date], CREDENTIALS_PATH, PDF_PATH)
# loop to find the areas that have different cloud cover
# for i in cloud_collection.getInfo()['features']:
#     if i['properties']['nonCloudArea'] != 6769200:
#         print(i['properties']['nonCloudArea'])
# 2018-03-12 has clouds
# 2019-03-22
# 2019-04-01 nr 179
# 6769200
# TODO: add vegetation gain and loss to pdf / test on server
# TODO: remove clouds from calculation
# TODO: chart changes changes over time
# TODO: interactive map in html email