# !/usr/bin/python3
# -*- coding: UTF-8 -*-

# import packages
import logging
import bs4
# import datetime
import ee
import folium
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import selenium.webdriver
from selenium.webdriver.firefox.options import Options
import time
from send_email import *
import sys
from xhtml2pdf import pisa


local_test_run = False
email_test_run = False

if len(sys.argv) >= 2:
    # if test run is declared true through the command line we just run local tests
    local_test_run = int(sys.argv[1])
if len(sys.argv) >= 3:
    email_test_run = int(sys.argv[2])

logging.basicConfig(filename='ndvi-report-mailer.log', level=logging.DEBUG)


if local_test_run:
    GEOJSON_PATH = 'KKRS.geojson'
    JSON_FILE_NAME = '../output/data.json'
    SCREENSHOT_SAVE_NAME = f'../output/growth_decline_'
    CREDENTIALS_PATH = '../credentials/credentials.json'
    REPORT_HTML = 'report.html'
else:
    GEOJSON_PATH = 'KKRS/NDVI-auto-processing/KKRS.geojson'
    JSON_FILE_NAME = 'KKRS/output/data.json'
    SCREENSHOT_SAVE_NAME = f'KKRS/output/growth_decline_'
    CREDENTIALS_PATH = 'KKRS/credentials/credentials.json'
    REPORT_HTML = '/KKRS/NDVI-auto-processing/report.html'

# variables
# import AOI and set geometry
with open(GEOJSON_PATH) as f:
    geo_data = json.load(f)

geometry = geo_data['features'][0]['geometry']

if local_test_run:
    PDF_PATH = f'../output/{datetime.utcnow().strftime("%Y%m%d")}-{geo_data["name"]}-Vegetation-Cover-Report.pdf'
else:
    PDF_PATH = f'KKRS/output/{datetime.utcnow().strftime("%Y%m%d")}-{geo_data["name"]}-Vegetation-Cover-Report.pdf'


# ee.Authenticate()
ee.Initialize()
geometry_feature = ee.FeatureCollection(geo_data)


# open html for pdf generation
with open(REPORT_HTML, 'r') as html_text:
    source_html = html_text.read()

logo = Path('static/bpla_logo_blau.png').resolve()

soup = bs4.BeautifulSoup(source_html, features="html5lib")
html_logo = soup.new_tag('img', src=logo, id="header_content")
soup.body.append(html_logo)

# set dates for analysis
py_date = datetime.utcnow()
ee_date = ee.Date(py_date)
# print(ee_date)
one_year_timedelta = timedelta(days=365)
five_year_timedelta = timedelta(days=(365*5))
start_date = ee.Date(py_date.replace(year=2016, month=7, day=1))
end_date = ee_date


timeframes = {
    'two_weeks': {'start_date': (ee.Date(py_date - timedelta(days=7))), 'end_date': end_date},
    'one_year': {'start_date': ee.Date(py_date - one_year_timedelta), 'end_date': end_date},
    'since_2016': {'start_date': ee.Date(py_date - five_year_timedelta), 'end_date': ee.Date(py_date)},
    'nov_2016': {'start_date': ee.Date(
        py_date.replace(year=py_date.year - 5, month=11, day=1) if py_date.replace(month=11, day=1) <= py_date else py_date.replace(year=py_date.year-6, month=11, day=1)
    ), 'end_date': ee.Date(
        py_date.replace(month=11, day=1) if py_date.replace(month=11, day=1) <= py_date else py_date.replace(year=py_date.year-1, month=11, day=1)
    )},
    'july_2016': {'start_date': ee.Date(
        py_date.replace(year=py_date.year - 5, month=7, day=1) if py_date.replace(month=7, day=1) <= py_date else py_date.replace(year=py_date.year-6, month=7, day=1)
    ), 'end_date': ee.Date(
        py_date.replace(month=7, day=1) if py_date.replace(month=7, day=1) <= py_date else py_date.replace(year=py_date.year-1, month=7, day=1)
    )},
}

head_text = {
    'two_weeks': 'Short-term: One-week',
    'one_year': 'Medium-term: One-year',
    'since_2016': 'Long-term: Five-year',
    'nov_2016': 'Long-term: Five-year winter',
    'july_2016': 'Long-term: Five-year summer',
}

body_text = {
    'two_weeks': [
        'Direct irrigation, pruning and maintenance control for last two weeks',
        'Focus on areas under maintenance (parks, roads)'
    ],
    'one_year': [
        ' Trends in maintenance performance and construction for one year',
        ' Indicative of environmental changes (weather, groundwater)'
    ],
    'since_2016': [
        'Long-term trends in maintenance, construction, and environmental changes'
    ],
    'nov_2016': [
        ' Long-term trends in natural and managed vegetation in favourable weather'
    ],
    'july_2016': [
        'Long-term trends in natural and managed vegetation in heat and water stress'
    ]
}


##  Function to mask clouds using the Sentinel-2 QA band param {ee.Image} image Sentinel-2 image @return {ee.Image} cloud masked Sentinel-2 image
#image = collection.first()

def maskS2clouds(image):
    qa = image.select('QA60')

    # Bits 10 and 11 are clouds and cirrus, respectively.
    cloudBitMask = ee.Number(2).pow(10).int()
    cirrusBitMask = ee.Number(2).pow(11).int()

    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))

    image = image.updateMask(mask)
    return image

def get_project_area(image):
    # made some changes here, pls check
    date = image.get('system:time_start')
    name = image.get('name')

    # calculate from polygon
    area = image.select('B1').multiply(0).add(1).multiply(ee.Image.pixelArea()).rename('area')
    project_stats = area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry_feature,
        scale=10,
        maxPixels=1e29
    )
    project_area_size = {'area': ee.Number(ee.FeatureCollection(geo_data).first().geometry().area()).getInfo()}
    #project_area_size = ee.Number(project_stats.get('B1')).multiply(100)

    return ee.Feature(None, {
        'project_area_size': project_area_size,
        'name': name,
        'system:time_start': date
        }
    )

def get_project_size(image):
    area = image.select('B1').multiply(0).add(1).multiply(ee.Image.pixelArea()).rename('area')
    project_stats = area.reduceRegion(
        reducer = ee.Reducer.sum(),
        geometry = geometry_feature,
        scale = 10,
        maxPixels = 1e29
    )
    project_stats = {'area': project_stats.get('area')}
    image = image.set(project_stats)
    return image


def get_cloud_stats(image):
    noncloud_area = image.select('B1').multiply(0).add(1).multiply(ee.Image.pixelArea()).rename('noncloud_area')
    cloud_stats = noncloud_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry_feature,
        scale=10,
        maxPixels=1e29
    )
    image = image.set({'noncloud_area': cloud_stats.get('noncloud_area')})
    image = image.set({'cloudArea': image.getNumber('area').subtract(image.getNumber('noncloud_area'))})
    image = image.set({'RelCloudArea': image.getNumber('cloudArea').divide(image.getNumber('area')).multiply(100)})
    return image

# NDVI function
def add_NDVI(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi')
    ndvi02 = ndvi.gte(0.2)
    ndviImg = image.addBands(ndvi).updateMask(ndvi02)
    ndvi02_area = ndvi02.multiply(ee.Image.pixelArea()).rename('ndvi02_area')

    # calculate ndvi > 0.2 area
    ndviStats = ndvi02_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry_feature,
        scale=10,
        maxPixels=1e29
    )

    image = image.set(ndviStats)

    # calculate area of AOI
    area = image.select('B1').multiply(0).add(1).multiply(ee.Image.pixelArea()).rename('area')

    # calculate area
    img_stats = area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry_feature,
        scale=10,
        maxPixels=1e29
    )
    image = image.set(img_stats)

    a = image.getNumber('ndvi02_area').divide(image.getNumber('area')).multiply(100)
    b = image.getNumber('ndvi02_area')

    # TODO: low priority: refactor! this is clunky and costly in terms of processing and storage. We do not need to have a band with a constant pixel value across the data set.
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
        geometry=geometry_feature,
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

def add_data_to_html(soup, data, head_text, body_text, processing_date):
    project_name = data[list(data.keys())[0]]['project_name']
    headline = soup.new_tag('p', id="intro_headline")
    headline.string = project_name
    soup.body.append(headline)
    headline_two = soup.new_tag('p', id="intro_headline")
    headline_two.string = 'Vegetation Cover Change Report'
    soup.body.append(headline_two)
    date = soup.new_tag('p')
    date.string = processing_date
    soup.body.append(date)
    version = soup.new_tag('p', **{'class': 'version'})
    version.string = 'v1.1'
    soup.body.append(version)
    dear_all = soup.new_tag('p')
    dear_all.string = 'Dear all,'
    soup.body.append(dear_all)
    intro_text = soup.new_tag('p', **{'class': 'title_padding_under_intro'})
    intro_text.string = 'This report localises changes in vegetation health for five time periods, based on \
    available data. The maps show positive vegetation health changes gain in green, negative ones in red.'
    soup.body.append(intro_text)
    for timeframe in data.keys():
        bulletpoint_headline = soup.new_tag('p', id="bulletpoint_headline")
        bulletpoint_headline.string = f'{head_text[timeframe]} comparison \
        ({data[timeframe]["start_date_satellite"]} to {data[timeframe]["end_date_satellite"]})'
        soup.body.append(bulletpoint_headline)
        ul = soup.new_tag('ul')
        for bulletpoint in body_text[timeframe]:
            li = soup.new_tag('li')
            li.string = bulletpoint
            ul.append(li)
        soup.body.append(ul)
    regards = soup.new_tag('p', **{'class': 'kind_regards'})
    regards.string = 'Kind regards,'
    soup.body.append(regards)
    regards = soup.new_tag('p')
    regards.string = 'Boedeker Systems'
    soup.body.append(regards)
    # necessary for page break
    new_page = soup.new_tag('p', **{'class': 'new-page'})
    soup.body.append(new_page)
    for timeframe in data.keys():
        image_headline = soup.new_tag('p', id="image_headline")
        image_headline.string = f'{head_text[timeframe]} comparison \
        ({data[timeframe]["start_date_satellite"]} to {data[timeframe]["end_date_satellite"]})'
        soup.body.append(image_headline)
        ul = soup.new_tag('ul')

        area_paragraph = soup.new_tag('li')
        area_paragraph.string = f'Project area: {data[timeframe]["project_area"]:.3f} km²'
        ul.append(area_paragraph)

        cover_start = soup.new_tag('li')
        cover_start.string = f'Vegetation cover ({data[timeframe]["start_date_satellite"]}): \
        {data[timeframe]["vegetation_start"]:,.0f} m² ({data[timeframe]["vegetation_share_start"]:.2f} %)'
        ul.append(cover_start)

        cover_end = soup.new_tag('li')
        cover_end.string = f'Vegetation cover ({data[timeframe]["end_date_satellite"]}): \
        {data[timeframe]["vegetation_end"]:,.0f} m² ({data[timeframe]["vegetation_share_end"]:.2f} %)'
        ul.append(cover_end)

        veg_gain = soup.new_tag('li')
        veg_gain.string = f'Vegetation health increase (green): \
        {data[timeframe]["vegetation_gain"]:,.0f} m² ({data[timeframe]["vegetation_gain_relative"]:.2f} %)'
        ul.append(veg_gain)

        veg_loss = soup.new_tag('li')
        veg_loss.string = f'Vegetation health decrease (red): \
        {data[timeframe]["vegetation_loss"]:,.0f} m² ({data[timeframe]["vegetation_loss_relative"]:.2f} %)'
        ul.append(veg_loss)

        net_veg_change = soup.new_tag('li')
        net_veg_change.string = f'Net vegetation change: \
        {data[timeframe]["vegetation_end"] - data[timeframe]["vegetation_start"]:,.0f} m² \
        ({data[timeframe]["vegetation_share_end"] - data[timeframe]["vegetation_share_start"]:.2f} %)'
        ul.append(net_veg_change)

        soup.body.append(ul)

        img = Path(data[timeframe]['path']).resolve()
        html_img = soup.new_tag('img', src=img)
        img_formatting = soup.new_tag('div', id="img_format")
        img_formatting.append(html_img)
        soup.body.append(img_formatting)

        # necessary for page break
        new_page = soup.new_tag('p', **{'class': 'new-page'})
        soup.body.append(new_page)
    return soup

def convert_html_to_pdf(source_html, output_filename):
    # open output file for writing (truncated binary)
    result_file = open(output_filename, "w+b")
    try:
        # convert HTML to PDF
        pisa_status = pisa.CreatePDF(
            source_html,  # the HTML to convert
            dest=result_file)  # file handle to receive result
    except Exception as e:
        print(f'Error: {e}')
        logging.debug(e)
    finally:
        # close output file
        result_file.close()  # close output file

    # return False on success and True on errors
    return pisa_status.err


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

#### this is the action script
### get collection
# download image collection for the whole range of dates
collection = (ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
              .filterDate(start_date, end_date)
              .filterBounds(geometry_feature)
              .map(lambda image: image.clip(geometry_feature))
              ##.map(get_project_size)
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 1))
              )

# select images from collection
# TODO: filter for cloud cover
# collection = cloud_mask_collection.filter(
#     ee.Filter.lt('RelCloudArea', 3)
# )
### calculate NDVI
ndvi_collection = collection.map(add_NDVI)
### maps and report


image_list = []
processing_date = py_date.strftime('%d.%m.%Y')
with open(JSON_FILE_NAME, 'r', encoding='utf-8') as f:
    data = json.load(f)
with open(JSON_FILE_NAME, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)

new_report = False

# loop through available data sets
for timeframe in timeframes:
    # get last image date
    timeframe_collection = collection.filterDate(timeframes[timeframe]['start_date'], timeframes[timeframe]['end_date'])
    ndvi_timeframe_collection = timeframe_collection.map(add_NDVI)
    ndvi_img_start = ee.Image(ndvi_timeframe_collection.toList(ndvi_timeframe_collection.size()).get(0))
    ndvi_img_end = ee.Image(ndvi_timeframe_collection.toList(ndvi_timeframe_collection.size()).get(ndvi_timeframe_collection.size().subtract(1)))

    # if there is no different image within that timeframe just take the next best
    if timeframe_collection.size().getInfo() > 1:
        latest_image = ee.Image(timeframe_collection.toList(timeframe_collection.size()).get(timeframe_collection.size().subtract(1)))
        first_image = ee.Image(timeframe_collection.toList(timeframe_collection.size()).get(0))

        latest_image_date = latest_image.date().format("dd.MM.YYYY").getInfo()
        first_image_date = first_image.date().format("dd.MM.YYYY").getInfo()
    else:
        latest_image = ee.Image(collection.toList(collection.size()).get(collection.size().subtract(1)))
        first_image = ee.Image(collection.toList(collection.size()).get(collection.size().subtract(2)))

        latest_image_date = latest_image.date().format("dd.MM.YYYY").getInfo()
        first_image_date = first_image.date().format("dd.MM.YYYY").getInfo()

        ndvi_img_start = ee.Image(add_NDVI(first_image))
        ndvi_img_end = ee.Image(add_NDVI(latest_image))

    # adjust short-term timeframe text depending on difference of newest data
    if timeframe == 'two_weeks':
        week_diff = round(latest_image.date().difference(first_image.date(), 'weeks').getInfo())
        if week_diff == 1:
            head_text['two_weeks'] = 'Short-term: One-week'
            body_text['two_weeks'] = [
                'Direct irrigation, pruning and maintenance control for the last week',
                'Focus on areas under maintenance (parks, roads)'
            ]
        else:
            head_text['two_weeks'] = f'Short-term: {week_diff}-weeks'
            body_text['two_weeks'] = [
                f'Direct irrigation, pruning and maintenance control for the last {week_diff} weeks',
                'Focus on areas under maintenance (parks, roads)'
            ]

    project_area = ndvi_img_start.getNumber('area').getInfo()

    vegetation_start = ndvi_img_start.getNumber('ndvi02_area').getInfo()
    vegetation_end = ndvi_img_end.getNumber('ndvi02_area').getInfo()
    area_change = vegetation_end - vegetation_start

    relative_change = 100 - (vegetation_end/vegetation_start) * 100
    vegetation_share_start = (vegetation_start/project_area) * 100
    vegetation_share_end = (vegetation_end/project_area) * 100
    vegetation_share_change = vegetation_share_end - vegetation_share_start

    #calculate difference between the two datasets
    growth_decline_img = ndvi_img_end.subtract(ndvi_img_start).select('thres')
    growth_decline_img_mask = growth_decline_img.neq(0)
    decline_mask = growth_decline_img.eq(-1)
    growth_mask = growth_decline_img.eq(1)
    growth_img = growth_decline_img.updateMask(growth_mask)
    decline_img = growth_decline_img.updateMask(decline_mask)
    growth_decline_img = growth_decline_img.updateMask(growth_decline_img_mask)
    # calculate area
    vegetation_stats_gain = growth_img.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry_feature,
        scale=10,
        maxPixels=1e29)
    vegetation_gain = ee.Number(vegetation_stats_gain.get('thres')).multiply(100).round().getInfo()

    vegetation_loss = area_change - vegetation_gain
    vegetation_loss_relative = -vegetation_loss / project_area * 100
    vegetation_gain_relative = vegetation_gain / project_area * 100

    if area_change < 0:
        relative_change = -relative_change

    # compare date of latest image with last recorded image
    # if there is new data it will set new_report to True
    json_file_name = JSON_FILE_NAME
    screenshot_save_name = f'{SCREENSHOT_SAVE_NAME}_{processing_date}_{timeframe}.png'

    with open(json_file_name, 'r', encoding='utf-8')as f:
        data = json.load(f)
        # create initial dict if empty
        if data == {}:
            print('creating initial data')
            new_report = True
            data[processing_date] = {}
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
        elif processing_date in data.keys() and timeframe not in data[processing_date].keys():
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
        elif latest_image_date != data[list(data.keys())[-1]][timeframe]['end_date_satellite']:
            if processing_date not in data.keys():
                print('processing date will be added.')
                data[processing_date] = {}
            print(f'Newest available data is from {latest_image_date}. Last generated report is from: {data[list(data.keys())[-2]][timeframe]["end_date_satellite"]}')
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
            print(f'No new data for {processing_date}.')
    with open(json_file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

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
    print(f'timeframe: {timeframe} processed')

if new_report:
    for timeframe in timeframes:
        # if no data for timeframe
        if timeframe not in data[processing_date].keys():
            data[processing_date][timeframe] = {}
            # search for previous date that has the data
            for date in list(data.keys())[-2::-1]:
                # fill data in
                if timeframe in data[date].keys():
                    data[processing_date][timeframe]['start_date'] = data[date][timeframe]['start_date']
                    data[processing_date][timeframe]['end_date'] = data[date][timeframe]['end_date']
                    data[processing_date][timeframe]['start_date_satellite'] = data[date][timeframe]['start_date_satellite']
                    data[processing_date][timeframe]['end_date_satellite'] = data[date][timeframe]['end_date_satellite']
                    data[processing_date][timeframe]['vegetation_start'] = data[date][timeframe]['vegetation_start']
                    data[processing_date][timeframe]['vegetation_end'] = data[date][timeframe]['vegetation_end']
                    data[processing_date][timeframe]['vegetation_share_start'] = data[date][timeframe]['vegetation_share_start']
                    data[processing_date][timeframe]['vegetation_share_end'] = data[date][timeframe]['vegetation_share_end']
                    data[processing_date][timeframe]['vegetation_share_change'] = data[date][timeframe]['vegetation_share_change']
                    data[processing_date][timeframe]['project_area'] = data[date][timeframe]['project_area']
                    data[processing_date][timeframe]['area_change'] = data[date][timeframe]['area_change']
                    data[processing_date][timeframe]['relative_change'] = data[date][timeframe]['relative_change']
                    data[processing_date][timeframe]['vegetation_gain'] = data[date][timeframe]['vegetation_gain']
                    data[processing_date][timeframe]['vegetation_loss'] = data[date][timeframe]['vegetation_loss']
                    data[processing_date][timeframe]['vegetation_gain_relative'] = data[date][timeframe]['vegetation_gain_relative']
                    data[processing_date][timeframe]['vegetation_loss_relative'] = data[date][timeframe]['vegetation_loss_relative']
                    data[processing_date][timeframe]['path'] = data[date][timeframe]['path']
                    data[processing_date][timeframe]['project_name'] = data[date][timeframe]['project_name']
    # sort data before genrating report
    data[processing_date] = {k: data[processing_date][k] for k in list(timeframes.keys())}
    with open(json_file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    soup = add_data_to_html(soup, data[processing_date], head_text, body_text, processing_date)
    pisa.showLogging()
    convert_html_to_pdf(soup.prettify(), PDF_PATH)


if not local_test_run:
    if new_report:
        sendEmail(sendtest, open_project_date(JSON_FILE_NAME)[processing_date], CREDENTIALS_PATH, PDF_PATH)
        logging.debug(f'New email sent on {str(datetime.today())}')
    else:
        logging.debug(f'No new email on {str(datetime.today())}')

if email_test_run:
    sendEmail(sendtest, open_project_date(JSON_FILE_NAME)[list(data.keys())[-1]], CREDENTIALS_PATH, PDF_PATH)

# TODO: chart changes changes over time
# TODO: interactive map in html email
