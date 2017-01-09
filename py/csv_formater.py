#!/usr/bin/env python

'''
That will create a file of json reporter requests.
Run the following to curl the reporter requests thru the reporter_service via POST:
time cat reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/segment_match?
'''

import sys
import csv
import json
from operator import itemgetter
from datetime import datetime, date

prev = 0
elapsed_time = 0

csvfile = open(sys.argv[1], 'r')
columns = ("time","vehicleId","lat","lon")
reader = csv.DictReader(csvfile, fieldnames=columns)
trace = []
for row in sorted(reader, key=itemgetter(columns[1], columns[0])):
  # Convert to epoch seconds
  epoch = datetime(1970,1,1)
  i = datetime.strptime(row.get(columns[0]),"%Y-%m-%dT%H:%M:%S.%fZ")
  delta_time = int((i - epoch).total_seconds())
  row['time'] = delta_time
  start_time = delta_time
  if (prev != 0):
    elapsed_time += delta_time - prev
  else:
    elapsed_time += delta_time - start_time
  prev = start_time

  # Continuation of same vehicle Id
  if len(trace) and row.get(columns[1]) == trace[-1].get(columns[1]):
    trace.append(row)
  # End the prior vehicle
  else:
    if len(trace):
      print json.dumps({'trace':trace})
    trace = [ row ]
    #print json.dumps({'type': 'Feature', 'geometry': { 'type': 'LineString', 'coordinates': [ [float(i['lon']), float(i['lat'])] for i in trace ] }, 'properties':{}}, separators=(',',':')), ','


  # Update prior_vehicle Id
  prior_vehicle_id = row.get(columns[1])
