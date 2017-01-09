#!/usr/bin/env python

'''
If you're running this from this directory you can create the json request files from the raw CSV data by running this:
PYTHONPATH=PYTHONPATH:../../tools/.libs ./data_importer.py

That will create a reporter_requests.json file.
Run the following to curl the reporter requests thru the reporter_service via POST:
time cat reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/segment_match?
'''

import sys
import StringIO
import json
import threading
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
from cgi import urlparse
import valhalla
import csv,json,requests
from operator import itemgetter
from datetime import datetime, date

'''
sample url looks like this:
http://localhost:8002/?
'''

actions = { 'segment_match': None }

prev = 0
elapsed_time = 0

csvfile = open('/data/traffic/manila', 'r')
jsonfile = open('reporter_requests.json', 'w')

fieldnames = ("time","vehicleId","lat","lon")
reader = csv.DictReader(csvfile, fieldnames=None)
prior_vehicle_id = 0
for row in sorted(reader, key=itemgetter(fieldnames[1], fieldnames[0])):
  epoch = datetime(1970,1,1)
  i = datetime.strptime(row.get(fieldnames[0]),"%Y-%m-%dT%H:%M:%S.%fZ")
  delta_time = int((i - epoch).total_seconds())
  start_time = delta_time
  if (prev != 0):
    elapsed_time += delta_time - prev
  else:
    elapsed_time += delta_time - start_time
  prev = start_time
  #Replace times with int time
  row['time'] = delta_time

  if prior_vehicle_id == 0:
    # First row - start a new trace URL
    jsonfile.write('{"trace":[')
    json.dump(row, jsonfile, separators=(',',':'))
  elif row.get(fieldnames[1]) == prior_vehicle_id:
    # Continuation of same vehicle Id - add to current URL
    jsonfile.write(',')
    json.dump(row, jsonfile, separators=(',',':'))
  else:
    # End the prior URL. Ideally we would send a URL to the reporter...
    jsonfile.write(']}\n')
    # Start a new URL
    jsonfile.write('{"trace":[')
    json.dump(row, jsonfile, separators=(',',':'))
  # Update prior_vehicle Id
  prior_vehicle_id = row.get(fieldnames[1])
 
# Close off the last URL (ideally send to reporter)
jsonfile.write(']}')
jsonfile.close()
