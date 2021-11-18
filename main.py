# packages
import ee
from datetime import datetime, timedelta
import json
import sys
import os
from fpdf import FPDF
import folium
import selenium
import time
from os import listdir
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from pathlib import Path

# get timeframe through command line arguments sys.argv[1]
timeframe = 'two_weeks'

IMAGE_WIDTH = 2480
IMAGE_HEIGHT = 1748

# ee.Authenticate()
ee.Initialize()

# variables
## import AOI and set geometry
with open('DQ.geojson') as f:
    geo_data = json.load(f)
geometry = geo_data['features'][0]['geometry']

## set dates for analysis
py_date = datetime.utcnow()
ee_date = ee.Date(py_date)
# print(ee_date)

if timeframe == 'two_weeks':
    start_date = ee.Date(py_date - timedelta(days=14))
    end_date = ee_date
elif timeframe == 'one_year':
    current_year = py_date.year
    start_date = ee.Date(py_date.replace(year=current_year - 1))
    end_date = ee_date
elif timeframe == 'nov_2016':
    start_date = ee.Date(py_date.replace(year=2016, month=11, day=1))
    end_date = ee.Date(py_date.replace(month=11))
elif timeframe == 'july_2016':
    start_date = ee.Date(py_date.replace(year=2016, month=7, day=1))
    end_date = ee.Date(py_date.replace(month=7))
else:
    print(f'Command {timeframe} not found.')
    sys.exit()


# cloud masking function
def mask_cloud_and_shadows(image):
    qa = image.select('QA60')

    # Both flags should be set to zero, indicating clear conditions
    clouds = qa.bitwiseAnd(1 << 10).Or(qa.bitwiseAnd(1 << 11))

    return image.updateMask(clouds.Not())


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
    # TODO: low priority: refactor this is clunky and costly in terms of processing and storage. We do not need to have a band with a constant pixel value accorss the data set.
    rel_cover = image.select('B1').multiply(0).add(a).rename('rel_ndvi')
    image = image.addBands(rel_cover)
    image = image.addBands(ndvi)

    thres = ndvi.gte(0.2).rename('thres') #TODO: low priority: clean up this is the same as on line 60
    image = image.addBands(thres)
    image = image.addBands(b)
    return image


def get_veg_stats(image):
    date = image.get('system:time_start')
    name = image.get('name')
    pixelArea = ee.Image.pixelArea() #TODO: low priority:vars not used
    fixArea = 5961031705.843 #TODO: low priority:vars not used
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


# download image collection for the whole range of dates
collection = (ee.ImageCollection('COPERNICUS/S2')
              .filterDate(start_date, end_date)
              .filterBounds(geometry)
              .map(lambda image: image.clip(geometry))
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 1)))

latest_image = ee.Image(collection.toList(collection.size()).get(collection.size().subtract(1)))
first_image = ee.Image(collection.toList(collection.size()).get(0))

latest_image_date = latest_image.date().format("YYYY-MM-dd").getInfo()
first_image_date = first_image.date().format("YYYY-MM-dd").getInfo()

# TODO: vegetation change not right
# TODO: relative vegetation change
vegetation_start = get_veg_stats(first_image).getInfo()["properties"]["NDVIarea"]
vegetation_end = get_veg_stats(latest_image).getInfo()["properties"]["NDVIarea"]
area_change = vegetation_end - vegetation_start
relative_change = 100 - (vegetation_end/vegetation_start) * 100
if area_change < 0:
    relative_change = -relative_change

print(f'Change in vegetation area: {area_change}')
print(f'First image date: {first_image_date}\nLast image date: {latest_image_date}')

new_report = False
# compare date of latest image with last recorded image
# if there is new data it will set new_report to True
json_file_name = 'data.json'

with open(json_file_name, 'r', encoding='utf-8')as f:
    data = json.load(f)
    if timeframe not in data:
        print('Timeframe not yet covered. Will be generated.')
        new_report = True
        data[timeframe] = {'latest_image': latest_image_date,
                           'first_image': first_image_date,
                           'vegetation_area_change': area_change,
                           'paths': []
                           }
    elif datetime.strptime(latest_image_date, '%Y-%m-%d') > datetime.strptime(data[timeframe]['latest_image'],'%Y-%m-%d'):
        print('New data. Updating File.')
        new_report = True
        data[timeframe]['latest_image'] = latest_image_date
        data[timeframe]['first_image'] = first_image_date
        data[timeframe]['vegetation_area_change'] = area_change
    else:
        print('No new data.')
        sys.exit()

if new_report:
    # select images from collection
    ndvi_collection = collection.map(add_NDVI)
    ndvi_img_start = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(0))
    ndvi_img_end = ee.Image(ndvi_collection.toList(ndvi_collection.size()).get(ndvi_collection.size().subtract(1)))

    # calculate difference between the two datasets
    growth_decline_img = ndvi_img_end.select('thres').subtract(ndvi_img_start.select('thres'))
    growth_decline_img_mask = growth_decline_img.neq(0)
    growth_decline_img = growth_decline_img.updateMask(growth_decline_img_mask)
    cloud_vis_img = ndvi_img_end.select('QA60')

    polygon = ee.Geometry.Polygon(geometry['coordinates'][0][0])
    project_area = round(polygon.area().getInfo())



def add_ee_layer(self, ee_image_object, vis_params, name):
    """Adds a method for displaying Earth Engine image tiles to folium map."""
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; <a href="https://earthengine.google.com/">Google Earth Engine</a>',
        name=name,
        overlay=True,
        control=True,
    ).add_to(self)

growth_vis_params = {
    'min': -1,
    'max': 1,
    'palette': ['FF0000', '00FF00']
}

# swap out the coordinates because folium takes them the other way around
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

# TODO: Add statistics

# Define middle point of our map
html_map = 'map.html'

centroid = ee.Geometry(geometry).centroid().getInfo()['coordinates']
# get coordinates from centroid for folium
lat, lon = centroid[1], centroid[0]

my_map = folium.Map(location=[lat, lon], zoom_control=False, control_scale=True)

basemaps['Google Satellite'].add_to(my_map)

folium.PolyLine(swapped_coords, color="white", weight=5, opacity=1).add_to(my_map)
folium.Choropleth(geo_data=geometry, fill_opacity=0.5, fill_color='#FFFFFF').add_to(my_map)

# Add Earth Engine drawing method to folium.
folium.Map.add_ee_layer = add_ee_layer

my_map.add_ee_layer(growth_decline_img, growth_vis_params, 'Growth and decline image')

# fit bounds for optimal zoom level
my_map.fit_bounds(swapped_coords)

my_map.save(html_map)
my_map

options = FirefoxOptions()
options.add_argument("--headless")
driver = selenium.webdriver.Firefox(options=options)

# for 300dpi a5 we need  2480x1748
driver.set_window_size(IMAGE_WIDTH, IMAGE_HEIGHT)
driver.get('file:///' + os.path.dirname(os.path.abspath('map.html')) + '\\map.html')
# wait for html to load
time.sleep(3)
driver.save_screenshot('growth_decline.jpg')

# generate pdf
pdf = FPDF(orientation='L')
pdf.add_page()
pdf.set_font("Arial", size=12)
pdf.image('growth_decline.jpg', x=10, y=10, w=IMAGE_WIDTH/10, h=IMAGE_HEIGHT/10)
pdf.add_page()
# pdf.cell(10, 10, txt=f'Project area: {project_area} m²')
pdf.cell(10, 20, txt=f'Vegetation area at start date ({first_image_date}): {vegetation_start} m²')
pdf.cell(10, 30, txt=f'Vegetation area at end date ({latest_image_date}): {vegetation_end} m²')
pdf.cell(10, 40, txt=f'Vegetation area change: { area_change } m²')
pdf.cell(10, 50, txt=f'Relative change: {relative_change:.2f}%')
pdf_output_path = f"output/report_{geo_data['name']}_{ timeframe }_{ first_image_date }_{ latest_image_date }.pdf"
pdf.output(pdf_output_path)

# discard temporary data
os.remove('growth_decline.jpg')
os.remove('map.html')

data[timeframe]['paths'].append(pdf_output_path)
with open(json_file_name, 'w', encoding='utf-8') as f:
    json.dump(data, f)


# TODO: current dataset with dataset 2016
# TODO: remove clouds from calculation
# TODO: run analysis over the 4 data sets with the dynamic dates
# TODO: chart changes changes over time