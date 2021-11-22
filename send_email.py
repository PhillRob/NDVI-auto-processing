#!/usr/bin/python3
# -*- coding: UTF-8 -*-

# # # imports
import gc
import logging
import math
import smtplib
import time
import json
import ee
from collections import Counter
from datetime import datetime, timedelta
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from fulcrum import Fulcrum


# fulcrum vars BPLA
urlBase = 'https://api.fulcrumapp.com/api/v2/'
logging.basicConfig(filename='fulcrum-monthly-mailer.log', level=logging.DEBUG)

# no_timeout = Timeout(connect=None, read=None)
# http = PoolManager(timeout=no_timeout)

# general smtp mailer vars
fromaddr = "mailer@bp-la.com"
sendtest = False
recordsPerPage = 5000

ee.Initialize()

# Metro
## Issue Log
def METROISSemail(test, project_data):
    ####GILBERT: THIS IS JUST THE GET DATA AND RUN SUMMARY STATS PART WHICH POPUlATES VARS USED IN HTML FURTHER DOWN.
    with open('credentials.json') as c:
        credentials = json.load(c)
    apiToken = credentials['api_token']
    fulcrum = Fulcrum(key=apiToken)

    # recipients list
    if test:
        addr = ['gilbert.john@outlook.de', 'robeck@bp-la.com', 'philipp.robeck@gmail.com', 'phill@gmx.li']
    else:
        addr = ['gilbert.john@outlook.de', 'robeck@bp-la.com', 'philipp.robeck@gmail.com', 'phill@gmx.li']

    # get project vars
    formID = "d38fbeff-b3cf-4931-9b53-c3dd5a2062de"

    # get number of pages
    recordCount = fulcrum.forms.find(formID)['form']['record_count']
    pages = math.ceil(recordCount / recordsPerPage)

    # get data
    if pages > 1:
        for p in range(1, pages + 1):
            dataPage = fulcrum.records.search(url_params={'form_id': formID, 'page': p, 'per_page': recordsPerPage})['records']
            if p > 1:
                data.extend(dataPage)
            else:
                data = dataPage
    else:
        data = fulcrum.records.search(url_params={'form_id': formID, 'page': 1, 'per_page': recordsPerPage})['records']


    # total count per package
    for index in range(len(data)):
        if '6678' in data[index]['form_values']:
            data[index]['dp'] = ''.join(data[index]['form_values']['6678']['choice_values'][0])

    # mail vars
    ### GILBERT: THIS PREPARES THE EMAIL IN HTML AND ATTCHES TH LOGO ETC. PLEASE HAVE A READ AND MODIFY TO INCLUDE OUR DATA AND PDFs/
    msgRoot = MIMEMultipart('related')
    msgRoot['From'] = fromaddr
    msgRoot['To'] = ','.join(addr)
    msgRoot['Subject'] = (f"{project_data['project_name']} Vegetation report.")
    msgRoot.preamble = 'This is a multi-part message in MIME format.'

    # Encapsulate the plain and HTML versions of the message body in an
    # 'alternative' part, so message agents can decide which they want to display.
    msgAlternative = MIMEMultipart('alternative')
    msgRoot.attach(msgAlternative)

    # email attachments
    part = MIMEBase('application', "octet-stream")
    path = Path(project_data['paths'][-1])
    with open(path, 'rb') as file:
        part.set_payload(file.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition',
                        'attachment', filename=path.name)
        msgRoot.attach(part)
    #end attachments

    # Next, we attach the body of the email to the MIME message:
    msgText = MIMEText(
        f"Dear all, attached if the vegetation report for the project: {project_data['project_name']}\n"
        f'Project area: {project_data["project_area"]:,} m²\n'
        f'Vegetation area at start date ({project_data["first_image_date"]}): {project_data["vegetation_share_start"]:,} m²\n'
        f'Vegetation area at start date ({project_data["first_image_date"]}) relative to the project area: {project_data["vegetation_share_start"]:.2f}%\n'
        f'Vegetation area at end date ({project_data["latest_image_date"]}): {project_data["vegetation_end"]:,} m²\n'
        f'Vegetation area at end date ({project_data["latest_image_date"]}) relative to the project area: {project_data["vegetation_share_end"]:.2f}%\n'
        f'Vegetation area change: {project_data["area_change"]:,} m²\n'
        f'Relative change: {project_data["relative_change"]:.2f}%\n')
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

with open('data.json', 'r', encoding='utf-8')as f:
    try:
        data = json.load(f)
    except:
        print('Could not open json file.')

METROISSemail(sendtest, data['one_year'])
print('Email sent')
