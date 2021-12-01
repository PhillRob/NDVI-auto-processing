#!/usr/bin/python3
# -*- coding: UTF-8 -*-

# # # imports
import gc
import logging
from datetime import datetime, timedelta
import smtplib
import json
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# set up logging TODO: do this for main script as well
#logging.basicConfig(filename='ndvi-report-mailer.log', level=logging.DEBUG)

# no_timeout = Timeout(connect=None, read=None)
# http = PoolManager(timeout=no_timeout)

# general smtp mailer vars
fromaddr = "mailer@bp-la.com"
sendtest = False


def sendEmail(test, project_data):
    with open('credentials/credentials.json') as c:
        credentials = json.load(c)
    apiToken = credentials['api_token']

    # recipients list
    if test:
        addr = ['gilbert.john@outlook.de']
    else:
        addr = ['gilbert.john@outlook.de', 'robeck@bp-la.com', 'philipp.robeck@gmail.com', 'phill@gmx.li']

    # mail vars
    msgRoot = MIMEMultipart('related')
    msgRoot['From'] = fromaddr
    msgRoot['To'] = ','.join(addr)
    msgRoot['Subject'] = f"{ project_data['two_weeks']['project_name']}: Vegetation Cover Report {datetime.now().strftime('%d.%m.%Y') }"
    msgRoot.preamble = 'This is a multi-part message in MIME format.'

    # Encapsulate the plain and HTML versions of the message body in an
    # 'alternative' part, so message agents can decide which they want to display.
    msgAlternative = MIMEMultipart('alternative')
    msgRoot.attach(msgAlternative)

    text = 'Dear all, <br> Here we report on the the vegetation change in the Diplomatic Quarter. The results are based on the analysis of the Sentinel 2 Satellite data. The email is provided as soon as new data becomes available every 7-14 days.<br>'
    for timeframe in project_data:
        # Next, we attach the body of the email to the MIME message:
        text += f'<h2>{project_data[timeframe]["project_name"]}: Vegetation change from {project_data[timeframe]["start_date_satellite"]} to {project_data[timeframe]["end_date_satellite"]} </h2>'
        text += f'<img src="cid:image1{timeframe}"><br>'
        text += f'Project area: {project_data[timeframe]["project_area"]:.2f} km²<br>Vegetation cover ({project_data[timeframe]["start_date"]}): {project_data[timeframe]["vegetation_start"]:,} m² ({project_data[timeframe]["vegetation_share_start"]:.2f}%)<br>Vegetation cover ({project_data[timeframe]["end_date"]}): {project_data[timeframe]["vegetation_end"]:,} m² ({project_data[timeframe]["vegetation_share_end"]:.2f}%)<br>Net vegetation change: {project_data[timeframe]["area_change"]:,} m² ({project_data[timeframe]["vegetation_share_change"]:.2f}%)<br><br>'

        # This example assumes the image is in the current directory
        fp = open(project_data[timeframe]['path'], 'rb')
        msgImage = MIMEImage(fp.read())
        fp.close()

        # Define the image's ID as referenced above
        msgImage.add_header('Content-ID', f'<image1{timeframe}>')
        msgRoot.attach(msgImage)
    msgText = MIMEText(
        text, 'html'
    )

    msgAlternative.attach(msgText)
    # For sending the mail, we have to convert the object to a string, and then use the same prodecure as above to send
    # using the SMTP server.
    server = smtplib.SMTP('smtp.1und1.de', 587)
    server.starttls()
    server.ehlo()
    server.login(fromaddr, credentials['login_pw'])
    server.sendmail(fromaddr, addr, msgRoot.as_string())
    server.quit()
    gc.collect()

def open_project_date(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            return data
        except:
            print('Could not open json file.')

