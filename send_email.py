#!/usr/bin/python3
# -*- coding: UTF-8 -*-

# # # imports
import bs4
import gc
import logging
from datetime import datetime, timedelta
from pathlib import Path
import smtplib
import json
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from xhtml2pdf import pisa

# set up logging TODO: do this for main script as well
#logging.basicConfig(filename='ndvi-report-mailer.log', level=logging.DEBUG)

# no_timeout = Timeout(connect=None, read=None)
# http = PoolManager(timeout=no_timeout)

# general smtp mailer vars
sendtest = False


def sendEmail(test, project_data, credentials_path, path_to_pdf):
    # mapping different timeframes to the corresponding text
    head_text = {
        'two_weeks': 'One week',
        'one_year': 'One year',
        'nov_2016': 'Five year winter',
        'july_2016': 'Five year summer',
        'since_2016': 'Five year'
    }
    with open(credentials_path) as c:
        credentials = json.load(c)
    fromaddr = credentials['fromaddr']
    # recipients list
    if test:
        addr = ['gilbert.john@outlook.de']
    else:
        addr = ['gilbert.john@outlook.de', 'robeck@bp-la.com', 'alkhawand@bp-la.com']

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

    text = f'Dear all, <br> Here we report on the the vegetation change in the { project_data["two_weeks"]["project_name"]}. The results are based on the analysis of the Sentinel 2 Satellite data. The email is provided as soon as new data becomes available every 7-14 days. \
    <br><br>Please contact mailer@b-systems.com for any feedback and comments.<br><br>\
    Kind regards<br>boedeker systems<br>b-systems.com<br>\
    <img src="cid:image1" width="200"><br>'
    msgText = MIMEText(
        text, 'html'
    )
    msgAlternative.attach(msgText)
    # This example assumes the image is in the current directory
    fp = open(Path('static/bpla_logo_blau.png').resolve(), 'rb')
    msgImage = MIMEImage(fp.read())
    fp.close()

    # Define the image's ID as referenced above
    msgImage.add_header('Content-ID', '<image1>')
    msgRoot.attach(msgImage)

    with open(path_to_pdf, 'rb') as f:
        pdf_attach = MIMEApplication(f.read(), _subtype='pdf')
    pdf_attach.add_header('Content-Disposition', 'attachment', filename=str(path_to_pdf.split('/')[-1]))
    msgRoot.attach(pdf_attach)
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