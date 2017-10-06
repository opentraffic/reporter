#!/usr/bin/env python2

import argparse
import boto3
import functools
import sys
import os
import re
import logging
import gzip
import cStringIO
import contextlib
import multiprocessing
import tempfile
import hashlib
import time
import calendar
import math
import json
import valhalla
import reporter_service

#time's import of strptime is not thread safe so we have to import it ahead
#of time or use it in the main thread: https://bugs.python.org/issue7980
from _strptime import _strptime_time
time.strptime(time.strftime('%Y'), '%Y')

logger = logging.getLogger('simple_reporter')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

valhalla_tiles = [{'level': 2, 'size': 0.25}, {'level': 1, 'size': 1.0}, {'level': 0, 'size': 4.0}]
LEVEL_BITS = 3
TILE_INDEX_BITS = 22
SEGMENT_INDEX_BITS = 21
LEVEL_MASK = (2**LEVEL_BITS) - 1
TILE_INDEX_MASK = (2**TILE_INDEX_BITS) - 1
SEGMENT_INDEX_MASK = (2**SEGMENT_INDEX_BITS) - 1
INVALID_SEGMENT_ID = (SEGMENT_INDEX_MASK << (TILE_INDEX_BITS + LEVEL_BITS)) | (TILE_INDEX_MASK << LEVEL_BITS) | LEVEL_MASK

def get_tile_level(segment_id):
  return segment_id & LEVEL_MASK

def get_tile_index(segment_id):
  return (segment_id >> LEVEL_BITS) & TILE_INDEX_MASK

def get_prefixes_keys(client, bucket, prefixes):
  keys = []
  pres = []
  for prefix in prefixes:
    token = None
    first = True
    while first or token:
      if token:
        objects = client.list_objects_v2(Bucket=bucket, Delimiter='/', Prefix=prefix, ContinuationToken=token)
      else:
        objects = client.list_objects_v2(Bucket=bucket, Delimiter='/', Prefix=prefix)
      if 'Contents' in objects:
        keys.extend([ o['Key'] for o in objects['Contents'] ])
      if 'CommonPrefixes' in objects:
        pres.extend([ o['Prefix'] for o in objects['CommonPrefixes'] ])
      token = objects.get('NextContinuationToken')
      first = False
  return pres, keys

def split(l, n):
  size = int(math.ceil(len(l)/float(n)))
  cutoff = len(l) % n
  result = []
  pos = 0
  for i in range(0, n):
    end = pos + size if cutoff == 0 or i < cutoff else pos + size - 1
    result.append(l[pos:end])
    pos = end
  return result

def interrupt_wrapper(func):
  try:
    func()
  except (KeyboardInterrupt, SystemExit):
    logger.error('Interrupted or killed')

def download(bucket, keys, valuer, time_pattern, bbox, dest_dir):
  session = boto3.session.Session()
  client = session.client('s3')
  #TODO: just parse the time pattern pieces out and be more flexible
  fast_time = time_pattern == '%Y-%m-%d %H:%M:%S'
  for key in keys:
    #go get it
    try:
      file_name = hashlib.sha1(key).hexdigest()
      client.download_file(bucket, key, file_name)
      traces = {}
      logger.info('Downloaded %s' % key)
      with gzip.open(file_name, 'rb') as f:
        for message in f:
          #skip stuff not in bbox
          uuid, tm, lat, lon, acc = valuer(message)
          lat = float(lat)
          lon = float(lon)
          if lat < bbox[0] or lat > bbox[2] or lon < bbox[1] or lon > bbox[3]:
            continue
          if fast_time:
            tm = time.struct_time((int(tm[0:4]), int(tm[5:7]), int(tm[8:10]), int(tm[11:13]), int(tm[14:16]), int(tm[17:19]), 0, 0, 0))
          else:
            tm = time.strptime(tm, time_pattern)
          tm = calendar.timegm(tm)
          acc = min(int(math.ceil(float(acc))), 1000)
          serialized = ','.join([ str(i) for i in [uuid, tm, lat, lon, acc] ]) + os.linesep

          #hash the id part and get the values out, only take a little bit to force hash colisions
          key_file = dest_dir + os.sep + hashlib.sha1(uuid).hexdigest()[0:3]
          traces.setdefault(key_file, []).append(serialized)

      #append them to a file
      os.remove(file_name)
      for key_file, entries in traces.iteritems():
        serialized = ''.join(entries)
        with open(key_file, 'a', len(serialized)) as kf:
          kf.write(serialized)
      logger.info('Gathered traces from %s' % key)
    except (KeyboardInterrupt, SystemExit) as e:
      raise e
    except Exception as e:
      logger.error('%s was not processed %s' % (key, e))

def match(file_names, config, mode, report_levels, transition_levels, quantisation, inactivity, source, dest_dir):
  valhalla.Configure(config)
  segment_matcher = valhalla.SegmentMatcher()
  for file_name in file_names:
    #get out the data into a request payload
    traces = {}
    with open(file_name, 'r') as f:
      for line in f:
        uuid, tm, lat, lon, acc = tuple(line.strip().split(','))
        traces.setdefault(uuid, []).append({'lat': float(lat), 'lon': float(lon), 'time': int(tm), 'accuracy': int(acc)})

    #do each trace in this file
    tiles = {}
    for uuid, all_points in traces.iteritems():
      #sort the points by time in case threads were competing on the file
      all_points.sort(key=lambda v:v['time'])
      threshold_sec = 15

      #find the points where inactivity occurs, these are the time windows of a particular vehicles trace
      windows = []
      for i, point in enumerate(all_points):
        if i == 0 or point['time'] - all_points[i - 1]['time'] > inactivity:
          windows.append(i)

      #for each window, the last one is just an end marker
      for idx, i in enumerate(windows):
        #skip short traces, last one is just an end marker
        j = windows[idx + 1] if idx + 1 < len(windows) else len(all_points)
        if j - i < 2:
          continue
 
        #get the matches for it
        points = all_points[i : j]
        trace = {'uuid': uuid, 'trace': points, 'match_options':{'mode': mode}}
        try:
          match_str = segment_matcher.Match(json.dumps(trace, separators=(',', ':')))
          match = json.loads(match_str)
          report = reporter_service.report(match, trace, threshold_sec, report_levels, transition_levels)
        except (KeyboardInterrupt, SystemExit) as e:
          raise e
        except:
          logger.error('Failed to report trace with uuid %s from file %s' % (uuid, file_name))
          continue
        
        #weed out the usable segments and then send them off to the time tiles
        buckets = (points[-1]['time'] - points[0]['time']) / quantisation + 1
        segments = [ r for r in report['datastore']['reports'] if r['t0'] > 0 and r['t1'] > 0 and r['t1'] - r['t0'] > .5 and r['length'] > 0 and r['queue_length'] >= 0 ]
        for r in segments:
          duration = int(round(r['t1'] - r['t0']))
          start = int(math.floor(r['t0']))
          end = int(math.ceil(r['t1']))
          min_bucket = int(start / quantisation)
          max_bucket = int(end / quantisation)
          diff = max_bucket - min_bucket
          if diff > buckets:
            logger.error('Segment spans %d buckets but should be %d buckets or less for uuid %s in file %s' % (diff, buckets, uuid, file_name))
            continue
          for b in range(min_bucket, max_bucket + 1):
            tile_level = str(get_tile_level(r['id']))
            tile_index = str(get_tile_index(r['id']))
            tile_file_name = dest_dir + os.sep + str(b * quantisation) + '_' + str((b + 1) * quantisation - 1) + os.sep + tile_level + os.sep + tile_index
            s = [
              str(r['id']), str(r.get('next_id', INVALID_SEGMENT_ID)), str(duration), '1',
              str(r['length']), str(r['queue_length']), str(start), str(end), source, mode.upper()
            ]
            tiles.setdefault(tile_file_name, []).append(','.join(s) + os.linesep)

    #append to a file
    for tile_file_name, tile in tiles.iteritems():
      try: os.makedirs(os.sep.join(tile_file_name.split(os.sep)[:-1]))
      except (KeyboardInterrupt, SystemExit) as e:
        raise e
      except: pass
      serialized = ''.join(tile)
      with open(tile_file_name, 'a', len(serialized)) as f:
        f.write(serialized)

    #TODO: return the stats part so we can merge them together later on
    logger.info('Finished matching %d traces in %s' % (len(traces), file_name))
  
def report(file_names, bucket, privacy):
  session = boto3.session.Session()
  client = session.client('s3')
  for file_name in file_names:
    #sort the data for this tile
    with open(file_name, 'r') as f:
      segments = f.readlines()
    segments.sort()

    #cull the entries that dont meet the privacy requirements
    start = 0
    i = 0
    while i < len(segments):
      s = segments[start].split(',')
      e = segments[i].split(',')
      #we are onto a new range or the last one
      if s[0] != e[0] or s[1] != e[1] or i == len(segments) - 1:
        #if its the last range we need i to be as if its the next segment pair
        if i == len(segments) - 1:
          i += 1
        #didnt make the cut
        if i - start < privacy:
          segments[start: i] = []
          i = start
        #did make the cut
        else:
          start = i
      #next
      i += 1

    #dont send empty results
    if not segments:
      logger.info('No segments for %s after anonymising' % file_name)
      continue

    #figure out where this will go
    key = '/'.join(file_name.split(os.sep)[1:]) + '/' + hashlib.sha1(file_name).hexdigest()
    logger.info('Writing %d segments to %s' % (len(segments), key))

    #write the lines to a file like object and upload it
    with contextlib.closing(cStringIO.StringIO()) as f:
      f.write('segment_id,next_segment_id,duration,count,length,queue_length,minimum_timestamp,maximum_timestamp,source,vehicle_type' + os.linesep)
      f.write(''.join(segments))
      client.put_object(Bucket=bucket, Body=f.getvalue(), Key=key)

def get_traces(bucket, prefix, regex, valuer, time_pattern, bbox, concurrency):
  #get the proper keys we care about
  logger.info('Getting source data keys from bucket %s using prefix %s' % (bucket, prefix))
  _, keys = get_prefixes_keys(boto3.client('s3'), bucket, [prefix])
  filtered = filter(regex.match, keys)
  
  #download and parse them into proper files
  dest_dir = tempfile.mkdtemp(dir='')
  logger.info('Gathering trace data from %d source files into %s' % (len(filtered), dest_dir))
  keys = split(filtered, concurrency)
  processes = []
  for i in range(concurrency):
    bound = functools.partial(download, bucket, keys[i], valuer, time_pattern, bbox, dest_dir)
    processes.append(multiprocessing.Process(target=interrupt_wrapper, args=(bound,)))
    processes[-1].start()

  #TODO: monitor progress
  for p in processes:
    p.join()
  logger.info('Done gathering traces')
  return dest_dir

def make_matches(trace_dir, config, mode, report_levels, transition_levels, quantisation, inactivity, source, concurrency):
  #get the files that contain the trace data
  dest_dir = tempfile.mkdtemp(dir='')
  file_names = []
  for root, dirs, files in os.walk(trace_dir):
    for file_name in files:
      file_names.append(root + os.sep + file_name)

  #run the matching to turn them into osmlr segments with times
  logger.info('Matching traces from %d files to osmlr segments into %s' % (len(file_names), dest_dir))
  file_names = split(file_names, concurrency)  
  processes = []
  for i in range(concurrency):
    bound = functools.partial(match, file_names[i], config, mode, report_levels, transition_levels, quantisation, inactivity, source, dest_dir)
    processes.append(multiprocessing.Process(target=interrupt_wrapper, args=(bound,)))
    processes[-1].start()

  #TODO: monitor progress
  for p in processes:
    p.join()
  logger.info('Done matching trace data files')
  return dest_dir

def report_tiles(match_dir, bucket, privacy, concurrency):
  #get the full list of all the time tiles
  file_names = []
  for root, dirs, files in os.walk(match_dir):
    for file_name in files:
      file_names.append(root + os.sep + file_name)

  #send them up to s3
  logger.info('Reporting %d anonymised time tiles' % len(file_names))
  file_names = split(file_names, concurrency)  
  processes = []
  for i in range(concurrency):
    bound = functools.partial(report, file_names[i],bucket, privacy)
    processes.append(multiprocessing.Process(target=interrupt_wrapper, args=(bound,)))
    processes[-1].start() 

  #TODO: monitor progress
  for p in processes:
    p.join()
  logger.info('Done reporting tiles')

def check_box(bbox):
  b = [ float(b) for b in bbox.split(',') ]
  if b[0] < -90 or b[1] < -180 or b[2] > 90 or b[3] > 180 or b[0] >= b[2] or b[1] >= b[3]:
    raise argeparse.ArgumentTypeError('%s is not a valid bbox' % bbox)
  return b

def int_set(ints):
  return set(ints.split(','))

if __name__ == '__main__':
  #build args
  parser = argparse.ArgumentParser()
  parser.add_argument('--src-bucket', type=str, help='Bucket where to get the input trace data from', required=True)
  parser.add_argument('--src-prefix', type=str, help='Bucket prefix for getting source data', required=True)
  parser.add_argument('--src-key-regex', type=str, help='Bucket key regex for getting source data', default='.*')
  parser.add_argument('--src-valuer', type=str, help='A lambda used to extract the uid, time, lat, lon, accuracy from a given message in the input', default='lambda l: functools.partial(lambda c: [c[1], c[0], c[9], c[10], c[5] ], l.split("|"))()')
  parser.add_argument('--src-time-pattern', type=str, help='A string used to extract epoch seconds from a time string', default='%Y-%m-%d %H:%M:%S')
  parser.add_argument('--match-config', type=str, help='A file containing the config for the map matcher', required=True)
  parser.add_argument('--mode', type=str, help='The mode of transport used in generating the input trace data', default='auto')
  parser.add_argument('--report-levels', type=int_set, help='Comma seprated list of levels to report on', default=set([0,1]))
  parser.add_argument('--transition-levels', type=int_set, help='Comma separated list of levels to allow transitions on', default=set([0,1]))
  parser.add_argument('--quantisation', type=int, help='How large are the buckets to make tiles for. They should always be an hour (3600 seconds)', default=3600)
  parser.add_argument('--inactivity', type=int, help='How many seconds between readings of a given vehicle to consider as inactivity and there for separate for the purposes of matching', default=120)
  parser.add_argument('--privacy', type=int, help='How many readings of a given segment pair must appear before it being reported', default=2)
  parser.add_argument('--source-id', type=str, help='A simple string to identify where these readings came from', default='smpl_rprt')
  parser.add_argument('--dest-bucket', type=str, help='Bucket where we want to put the reporter output')
  parser.add_argument('--concurrency', type=int, help='Number of threads to use when doing various stages of processing', default=multiprocessing.cpu_count())
  parser.add_argument('--bbox', type=check_box, help='Comma separated coordinates within which data will be reported: min_lat,min_lon,max_lat,max_lon', default=[-90.0,-180.0,90.0,180.0])
  parser.add_argument('--trace-dir', type=str, help='To bypass trace gathering supply the directory with already parsed traces')
  parser.add_argument('--match-dir', type=str, help='To bypass trace matching supply the directory with the already matched segments')
  parser.add_argument('--cleanup', type=bool, help='Should temporary files be removed or not', default=True)
  args = parser.parse_args()

  try:
    #fetch the data and divide it up
    exec('valuer = ' + args.src_valuer)
    if not args.trace_dir and not args.match_dir:
      args.trace_dir = get_traces(args.src_bucket, args.src_prefix, re.compile(args.src_key_regex), valuer, args.src_time_pattern, args.bbox, args.concurrency)

    #do matching on every file
    if not args.match_dir:
      args.match_dir = make_matches(args.trace_dir, args.match_config, args.mode, args.report_levels, args.transition_levels, args.quantisation, args.inactivity, args.source_id, args.concurrency)

    #filter and upload all the data
    if args.dest_bucket:
      report_tiles(args.match_dir, args.dest_bucket, args.privacy, args.concurrency)

    #clean up the data
    if args.cleanup:
      os.remove(src_dir)
      os.remove(match_dir)
  except (KeyboardInterrupt, SystemExit):
    logger.error('Inerrupted or killed')
