# NDVI-auto-processing
This script calculates the Normalised Difference Vegetation Index (NDVI) using Sentinel 2 data for a Area of Interest given by a ```geojson``` polygone. The data is obtained and processed using the Google Earth Engine API. It returns the absolute and relative area and maps the results for five time frames. 
- last two weeks
- last year
- last summer
- last winter
- since the beginning of time to last dataset

The scirpt is set to check for new data and comparing it to the latest results stored locally. If new data is available an email is generated with the results and maps. 