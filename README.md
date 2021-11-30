# Vegetation Statistics (NDVI) and mapping using GEE python API
This script calculates the Normalised Difference Vegetation Index (NDVI) using Sentinel 2 data for an Area of Interest given by a ```geojson``` polygon. The data is obtained and processed using the [Google Earth Engine API](https://developers.google.com/earth-engine). It returns the absolute and relative vegetation area and maps the results for five time frames. 
- last two weeks
- last year
- last summer
- last winter
- since the beginning of time to last dataset

The script checks for new data and compares the latest available data it to the latest results stored locally. If new data is available an email is generated with the results and maps. A ```crontab``` command allows to run this daily and provide the email results if new data is published. 