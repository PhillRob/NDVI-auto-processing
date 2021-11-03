Automatic NDIV Google Web App Scope
•	Task definition: Develop automatic processing script to analyse NDVI, report on change and provide maps, statistic via email 
•	Time frame: 3 weeks max (19.11)
•	Target user group: Maintenance manager (DQ and other projects)
•	Project: 717
•	10 days Enrique (GIS Junior)
1	TASK
Script to be developed, and deployed to AWS server to 
•	Conduct NDVI analysis for DQ
•	Every two weeks
•	Provide maps (legend, scalebar, and north arrow in text) and statistics on change
•	Sent summary emails with map and images and text for statistics
•	Using google earth engine API 
•	Script in python 
2	OUTPUT
•	Analysis script python (analysis, maps, stats)
•	Emailing script python (analysis output)
3	EMAIL SUMMARY WITH FOUR MAPS 
3.1	LONG-TERM CHANGE
•	Summer comparison: July 2016 to last July data set available
•	Winter comparison: November 2016 to last November data set available
3.2	MID-TERM CHANGE
Last data set available to last year’s data set 
3.3	SHORT TERM CHANGE
Last data set available to 2 weeks ago
Sentinel 2 

# DQ NDVI Analysis Logic

dates:
    1. July 2016 to this year July data set
    2. November 2016 to this year November data set
    3. Last data set avaible to last years data set (-12month)
    4. Last data set avaible to -2weeks

if new data available
    download last image
    if AOI polygone falls within one image
        download all data data based on dates 
        analysis NDVI
        calculate relative veg cover for dates above
        calculate vegetated areas
        calulcate areas and rel veg cover differences 
        map
        export results to files
        email results

    else: mosaicing

else: do nothing

