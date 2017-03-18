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
import time
import calendar

# Read the file
with open(sys.argv[1], 'r') as csvfile:
  columns = ("time","uuid","lat","lon")
  reader = csv.DictReader(csvfile, fieldnames=columns)
  trace = {'trace':[], 'uuid': None}
  # For each row of data
  for row in sorted(reader, key=itemgetter(columns[1], columns[0])):
    # Convert to epoch seconds
    row[columns[0]] = calendar.timegm(time.strptime(row.get(columns[0]),"%Y-%m-%dT%H:%M:%S.%fZ"))
    # These shouldn't be strings
    row['lon'] = float(row['lon'])
    row['lat'] = float(row['lat'])

    # Continuation of same uuid
    if len(trace['trace']) and row.get(columns[1]) == trace['uuid']:
      del row[columns[1]]
      trace['trace'].append(row)
    # End the prior vehicle
    else:
      if len(trace['trace']) > 1:
        print json.dumps(trace, separators=(',',':'))
        #print json.dumps({'type': 'Feature', 'geometry': { 'type': 'LineString', 'coordinates': [ [i['lon'], i['lat']] for i in trace ] }, 'properties':{'uuid':uuid}}, separators=(',',':')), ','
      trace['uuid'] = row[columns[1]]
      del row[columns[1]]
      trace['trace'] = [ row ]
