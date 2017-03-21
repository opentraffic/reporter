#!/usr/bin/env python
import sys
import os
import time
import calendar
import argparse
import json

#parse a couple of options
parser = argparse.ArgumentParser(description='Generate reporter post body', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('file', metavar='F', type=str, nargs=1, help='A file name to be read from, use - for stdin')
parser.add_argument('--batch-size', type=int, help='How many points per trace before starting a new request', default=100)
parser.add_argument('--time-between', type=int, help='How many seconds allowed between adjacent readings before starting a new request', default=60)
parser.add_argument('--output-format', type=str, help='What format of output to use, either json or csv', default='json', choices=['json','csv'])
args = parser.parse_args()
args.file = args.file[0]

#output a single body
def emit(trace):
  if len(trace['trace']) < 2:
    return
  if args.output_format == 'json':
    sys.stdout.write(json.dumps(trace, separators=(',', ':')) + os.linesep)
  else:
    csv = ','.join([ ','.join([str(t['time']), str(t['lat']), str(t['lon'])]) for t in trace['trace'] ])
    sys.stdout.write(trace['uuid'] + ','  + csv + os.linesep)
    sys.stdout.flush()

#for each line from stdin
uuids = {}
handle = open(args.file, 'r') if args.file != '-' else sys.stdin
for line in handle:
  #try to work on the line as normal
  try:
    #parse out the important parts of the line
    parts = line.split('|')
    uuid = parts[1]
    reading = { 'time': calendar.timegm(time.strptime(parts[0], '%Y-%m-%d %H:%M:%S')), \
      'lat': float(parts[9]), \
      'lon': float(parts[10]) }
    #update this uuids trace
    if uuid not in uuids:
      uuids[uuid] = {'uuid': uuid, 'trace':[]}
    trace = uuids[uuid]['trace']
    #if its been too much time or we hit the batch size
    if (len(trace) and reading['time'] - trace[-1]['time'] > args.time_between) or len(trace) > args.batch_size:
      emit(uuids[uuid])
      uuids[uuid] = {'uuid': uuid, 'trace':[reading]}
    #append
    else:
      trace.append(reading)
  #we couldnt parse this line so lets output what we have so far
  except:
    for k,v in uuids.iteritems():
      emit(v)
    uuids = {}
#flush anything left
for k,v in uuids.iteritems():
  emit(v)
#done
if args.file != '-':
  handle.close()
