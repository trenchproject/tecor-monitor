__author__ = 'Aji John'
# ==============================================================================
# Main monitor thread to sweep the outstanding requests
# Revised: 2016-09-10
__version__ = '0.0.1'
# ==============================================================================]

import os
import sched
import time
from datetime import date
from datetime import datetime
from enum import Enum
from os.path import join, dirname
from string import Template
import shutil
# old
# from boto import s3

# new
# import boto3
# from botocore.exceptions import ClientError

# s3 = boto3.client('s3')

# from boto.s3.connection import OrdinaryCallingFormat
from dotenv import load_dotenv
from pymongo import MongoClient
import sys
import cdsapi

import SES
import pyncl

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)
s3bucket = os.environ.get("BUCKET")
awsregion = os.environ.get("AWSREGION")
inputdir = os.environ.get("INPUTDIR")
outputdir = os.environ.get("OUTPUTDIR")

s = sched.scheduler(time.time, time.sleep)

'''
Extract Request

{"email": "x.y@gmail.com",
 "text": "Request for extract",
 "lats": ["30", "43"],
 "longs":["-125", "-113"],
 "variable":["Tsurface"],
 "startdate":"19810102",
 "enddate":"19810102",
 "interval":"",
 "aggregationmetric":"",
  "outputformat":"csv",
  "timelogged":"",
  "status":"OPEN",
  "misc":""
}
'''


class ErrorMessages(Enum):
    OK = 0
    BOUNDING_BOX_TOO_SMALL = 2
    TWO_YEAR_FILTER_LIMIT = 3
    NON_EXISTENT_MICROCLIM_FILE = 42
    SEGMENTATION_FAULT_CORE_DUMPED = 139
    NCL_COMMAND_NOT_FOUND = 127
    UNKNOWN_ERROR_OCCURED_LOGGED_FOR_RESEARCH = 500


def check_new(sc):
    # look for new jobs
    # if exists, pick it, change the status
    #
    today = date.today()
    print("Starting sweep on " + str(today.strftime('%m/%d/%Y %H:%M')))
    requests = db.requests

    error = True
    filesDownloaded = False

    request_lkup = requests.find_one({"status": "OPEN"})

    # copy the required files to local
    # update the status to say picked-up
    # invoke the script to call the ncl
    # verify the file exists in S3
    # send email out

    if(request_lkup is not None):

        # iterate thru variables to get the file names
        # for variable in request_lkup['variable']:
        # find the distinct years in the range
        # dates are in format - "19810131"
        enddate = datetime.strptime(request_lkup['enddate'], '%Y%m%d')
        fromdate = datetime.strptime(request_lkup['startdate'], '%Y%m%d')
        noofyears = enddate.year - fromdate.year

        # set the time period
        timeperiod = ''
        years = []

        # Requested for same year
        if(noofyears == 0):
                # use the from year
                # initiate copy of all the files for the year for each requested variable
                years = [fromdate.year]

        else:
                # get the years
                years = [i+fromdate.year for i in range(noofyears)]

        # check if past or future
        if fromdate.year < datetime.now().year:
                    timeperiod = 'past'
        else:
                    timeperiod = 'future'

        # if the input work directory doesn't exist, create it
        if not os.path.exists(inputdir + '/' + str(request_lkup['_id'])):
                os.makedirs(inputdir + '/' + str(request_lkup['_id']))

        # fail to proceed, limit for only 2 years
        if(noofyears > 2):
            error = True
            retCode = 3
        else:
            error = False

        # Form the request string
        requeststring = Template(
                'Your request was submitted with parameters -  start date $startdate, enddate $enddate,' +
                ' bounding box ($lats,$latn) ($lonw,$lone), ' +
                ' shade level $shadelevel, height $hod, interval $interval and aggregation metric $aggregation.\n')
        request_text = requeststring.safe_substitute(startdate=request_lkup['startdate'],
                                                         enddate=request_lkup['enddate'],
                                                         lats=request_lkup['lats'][0], latn=request_lkup['lats'][1],
                                                         lonw=request_lkup['longs'][0], lone=request_lkup['longs'][1],
                                                         shadelevel=request_lkup['shadelevel'], hod=request_lkup['hod'],
                                                         interval=request_lkup['interval'],
                                                         aggregation=request_lkup['aggregation'])
        # if not error:
          # initiate copy
          # for variable in request_lkup['variable']:
            # for eg - past_1989_WIND10.nc
            # for year in years:
                # key = timeperiod+ '_' + str(year)+'_'+variable + '.nc'
                # if  not os.path.isfile(inputdir+  '/' + str(request_lkup['_id']) +  '/' + key):
                   # with open(inputdir+  '/' + str(request_lkup['_id']) +  '/' + key, 'wb') as data:
                     # try:
                        # s3.download_fileobj(s3bucket, key, data)
                        # filesDownloaded = True
                     # except ClientError as e:
                         # if e.response['ResponseMetadata']['HTTPStatusCode'] == '404':
                            # retCode = 42
                         # else:
                             # retCode = 500
                         # break

          # if the output work directory doesn't exist create it
        if not os.path.exists(outputdir + '/' + str(request_lkup['_id'])):
            os.makedirs(outputdir + '/' + str(request_lkup['_id']))

        #Cds Function for Source ERA5
        def function_cds(variable,time,output,North,South,East,West,start_day,end_day,start_month,end_month,start_year,end_year):
                c = cdsapi.Client()
                d = c.retrieve(
                'reanalysis-era5-single-levels',
            {
                'product_type': 'reanalysis',
                'variable': variable,

                'year': [
                    start_year,
                    end_year
                ],
                'month': [
                    start_month,
                    end_month
                ],
                'day': [
                    start_day,
                    end_day
                ],
                'time': time,
                'format': output,
                'area': [
                    North, West, South,
                    East,
                ],
            },
            ) 
                sys.stdout.write(str(d))

        # if the input source ERA5 then it should generate a result link
        if request_lkup['source'] == 'ERA5':
            start_day = request_lkup['enddate'][6:8]
            end_day = request_lkup['startdate'][6:8]
            start_month = request_lkup['startdate'][4:6]
            end_month = request_lkup['enddate'][4:6]
            start_year = request_lkup['startdate'][:4]
            end_year = request_lkup['enddate'][:4]
            North = request_lkup['lats'][0]
            South = request_lkup['lats'][1]
            East = request_lkup['longs'][0]
            West = request_lkup['longs'][1]
            interval = request_lkup['interval']
            output = request_lkup['outputformat']

            if interval == 'Daily':
                time = ['00:00']
            elif interval == '6 Hourly':
                time = ['00:00','06:00','12:00','18:00']
            elif interval == '12 Hourly':
                time = ['00:00','12:00']
            elif interval == 'Hourly':
                time = ['00:00','01:00','02:00','03:00','04:00','05:00','06:00','07:00','08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00','18:00','19:00','20:00','21:00','22:00','23:00']
            
            variables = request_lkup['variable'] 
            variable = []
            dict_variable = {'Tair':'2m_temperature','Tsurface':'skin_temperature','Tsoil':'soil_temperature_level_1','SMOIS':'volumetric_soil_water_layer_1'}
            for i in variables:
                variable.append(dict_variable[i])

            function_cds(variable,time,output,North,South,East,West,start_day,end_day,start_month,end_month,start_year,end_year)

        else:
          # Iterate through all the variables
          for variable in request_lkup['variable']:
            # lat is LatS, LatN
            # lon is LonW, LonE
            retCode = pyncl.RunNCLV2.withvar(inputdir + '/' + str(request_lkup['_id']), outputdir + '/' + str(request_lkup['_id']), request_lkup['startdate'],
                             request_lkup['enddate'],
                             request_lkup['lats'][0],
                             request_lkup['lats'][1],
                             request_lkup['longs'][0],
                             request_lkup['longs'][1],
                             variable,
                             # 0, 0,0,0,1)
                             request_lkup['shadelevel'],
                             request_lkup['hod'],
                             request_lkup['interval'],
                             request_lkup['aggregation'],
                             1)
            # If one variable job errors , leave
            if(retCode < 0 or retCode > 0):
                error = True
                break
            else:
                error = False

        if(not error):
            # Last set of variables shade, height,interval,aggregation,output

            # boto 2 - revised 06/8
            # c = s3.connect_to_region(awsregion,calling_format=OrdinaryCallingFormat())
            # bucket = c.get_bucket(s3bucket, validate=False)

            # D-extract
            # key = bucket.new_key('/' + str(request_lkup['_id']) +'/extract.txt')
            # key.set_contents_from_filename(outputdir+ '/d02.txt')

            transitdirectory = outputdir + '/' + str(request_lkup['_id'])

            # copy all the created files
            filestosend = [f for f in os.listdir(transitdirectory) if os.path.isfile(
                os.path.join(transitdirectory, f))]

            fileurls = []
            emailbodyurl = ''
            footer = '\n \n If any questions/issues, please report it on our github issues page - https://github.com/trenchproject/ebm/issues.'

            for file in filestosend:

                # boto 2 upload to s3
                # key = bucket.new_key('/' + str(request_lkup['_id']) + '/' + file)
                # key.set_contents_from_filename(transitdirectory + '/' + file)
                # key.set_metadata('Content-Type', 'text/plain')
                # key.set_acl('public-read')

                # Create file on S3 and setup the permissions - boto3
                with open(transitdirectory + '/' + file, "rb") as f:
                    # s3.upload_fileobj(f, s3bucket, '/' + str(request_lkup['_id']) + '/' + file,
                    ExtraArgs = {"Metadata": {"Content-Type": "text/plain"}, 'ACL': 'public-read'}

               # 2 days expiry
                # url = key.generate_url(expires_in=172800, query_auth=False, force_http=True)
                # boto3
                # url = s3.generate_presigned_url(
                    ClientMethod='get_object',
                    Params={
                        'Bucket': s3bucket,
                        'Key': '/' + str(request_lkup['_id']) + '/' + file
                    },
                    ExpiresIn = 172800
                

                fileurls.append(url)
                emailbodyurl=emailbodyurl + "\n" + url

            SES.send_ses(awsregion, 'requests@microclim.org', 'Your extract request-' +
                     str(request_lkup['_id']) + ' has completed',
                         request_text + "You can access your files using the hyperlinks below \n " + emailbodyurl + footer, request_lkup['email'])

            requests.update_one({
                '_id': request_lkup['_id']
                }, {
                '$set': {
                'status': "EMAILED"
                }
                }, upsert = False)

            # TODO
            # Check if the update actually occured


        else:
            SES.send_ses(awsregion, 'requests@microclim.org', 'Your extract request-' +
                         str(request_lkup['_id']) + \
                             ' has completed with ERROR',
                         request_text + "Request has resulted in error - " + ErrorMessages(retCode).name + " for date range " + request_lkup['startdate'] +
                                      "-" + request_lkup['enddate'], request_lkup['email'])

            requests.update_one({
                '_id': request_lkup['_id']
            }, {
                '$set': {
                    'status': "ERRORED",
                    'status_message': ErrorMessages(retCode).name + " for date range " + request_lkup['startdate'] +
                                      "-" + request_lkup['enddate']
                }
            }, upsert = False)

        print("Processed request id - " +
              str(request_lkup['_id']) + " from " + str(request_lkup['email']))

    # Remove the files from ebinput/{requestid}
    if filesDownloaded:
        if os.path.isdir(inputdir + '/' + str(request_lkup['_id'])):
            shutil.rmtree(inputdir + '/' + str(request_lkup['_id']))

    print("Completed sweep on " + str(today.strftime('%m/%d/%Y %H:%M')))

    # Resechedule
    s.enter(60, 1, check_new, (sc,))

def test():
    request={"email": "aji.john@xyz.com",
        "text": "Request for extract",
        "lats": ["30", "43"],
        "longs": ["-125", "-113"],
        "variable": ["Tsurface"],
        "startdate": "19810102",
        "enddate": "19810131",
        "interval": "",
        "aggregationmetric": "",
        "outputformat": "csv",
        "timelogged": "",
        "status": "OPEN",
        "misc": ""}
    pass




if __name__ == '__main__':
    # Initialize with DB Context
    db=MongoClient()['ebm']
    # test()
    # Check every minute
    s.enter(60, 1, check_new, (s,))
    s.run()
