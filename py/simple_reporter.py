#!/usr/bin/env python2

import argparse
import boto3
import urllib
import functools
import os
import re
import traceback
import logging
import gzip
import cStringIO
import contextlib
import Queue
import multiprocessing
import threading
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

thread_local = threading.local()

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

class Worker(threading.Thread):
  def __init__(self, tasks, results, local_init):
    threading.Thread.__init__(self)
    self.tasks = tasks
    self.results = results
    self.daemon = True
    self.local_init = local_init
    self.start()
  def run(self):
    self.local_init()
    while True:
      func, args, kargs = self.tasks.get()
      try:
        result = func(*args, **kargs)
        if result is not None:
          self.results.put(result)
      except Exception as e: logger.error(traceback.format_exc())
      finally: self.tasks.task_done()

class ThreadPool:
  def __init__(self, num_threads, thread_local_init=lambda:None):
    self.tasks = Queue.Queue(0)
    self.results = Queue.Queue(0)
    for _ in range(num_threads): Worker(self.tasks, self.results, thread_local_init)
  def add_task(self, func, *args, **kargs):
    self.tasks.put((func, args, kargs))
  def join(self):
    self.tasks.join()
    return list(self.results.queue)
  def queue_size(self):
    return self.tasks.qsize()

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

def download(bucket, key, keyer, valuer, time_pattern, bbox, dest_dir):
  #TODO: just parse the time pattern pieces out and be more flexible
  fast_time = time_pattern == '%Y-%m-%d %H:%M:%S'
  #go get it
  try:
    file_name = hashlib.sha1(key).hexdigest()
    thread_local.client.download_file(bucket, key, file_name)
    traces = {}
    logger.info('Downloaded %s' % key)
    with gzip.open(file_name, 'rb') as f:
      for message in f:
        #skip stuff not in bbox
        value = valuer(message)
        lat = float(value[1])
        lon = float(value[2])
        if lat < bbox[0] or lat > bbox[2] or lon < bbox[1] or lon > bbox[3]:
          continue
        if fast_time:
          tm = time.struct_time((int(value[0][0:4]), int(value[0][5:7]), int(value[0][8:10]), int(value[0][11:13]), int(value[0][14:16]), int(value[0][17:19]), 0, 0, 0))
        else:
          tm = time.strptime(value[0], time_pattern)
        tm = calendar.timegm(tm)
        acc = min(int(math.ceil(float(value[3]))), 1000)
        message_key = keyer(message)
        serialized = ','.join([ str(i) for i in [tm, lat, lon, acc] ]) + os.linesep
        #hash the id part and get the values out
        key_file = '00' + hashlib.sha1(message_key).hexdigest()
        chars = list(key_file)
        for i in range(0, 14):
          chars.insert(i * 3 + i, '/')
        key_file = dest_dir + ''.join(chars)
        traces.setdefault(key_file, []).append(serialized)
    os.remove(file_name)
    #append them to a file
    for key_file, entries in traces.iteritems():
      try: os.makedirs(os.sep.join(key_file.split('/')[:-1]))
      except: pass
      serialized = ''.join(entries)
      with open(key_file, 'a', len(serialized)) as kf:
        kf.write(serialized)
    logger.info('Gathered traces from %s' % key)
  except Exception as e:
    logger.error('%s was not processed %s' % (key, e))
    raise e
  
def local_session():
  setattr(thread_local, 'session', boto3.session.Session())
  setattr(thread_local, 'client', thread_local.session.client('s3'))

def get_traces(bucket, prefix, regex, keyer, valuer, time_pattern, bbox, threads):
  logger.info('Getting source data keys from bucket %s using prefix %s' % (bucket, prefix))
  #get the proper keys we care about
  _, keys = get_prefixes_keys(boto3.client('s3'), bucket, [prefix])
  filtered = filter(regex.match, keys)
  
  #download and parse them into proper files
  dest_dir = tempfile.mkdtemp(dir='')
  logger.info('Gathering trace data from source files into %s' % dest_dir)
  pool = ThreadPool(threads, local_session)
  total = 0.0
  for key in filtered:
    pool.add_task(download, bucket, key, keyer, valuer, time_pattern, bbox, dest_dir)
    total += 1
  logger.info('%d source files have been queued' % total)

  #monitor progress
  progress = -1
  while pool.queue_size() > 0:
   p = int((1.0 - (pool.queue_size() / total)) * 10) * 10
   if p > progress:
     logger.info('Gathering traces %d%%' % p)
     progress = p
   time.sleep(1)
  pool.join()
  if progress != 100:
    logger.info('Gathering traces 100%')
  logger.info('Done gathering traces')
  return dest_dir

def match(file_name, quantisation, source, dest_dir):
  #get out the data into a request payload
  trace = { 'uuid': file_name, 'trace': [] }
  with open(file_name, 'r') as f:
    for line in f:
      tm, lat, lon, acc = tuple(line.strip().split(','))
      trace['trace'].append({'lat': float(lat), 'lon': float(lon), 'time': int(tm), 'accuracy': int(acc)})

  #skip short traces
  if len(trace['trace']) < 2:
    return

  #sort the points by time in case threads were competing on the file
  trace['trace'].sort(key=lambda v:v['time'])
  report_levels = set([0, 1])
  transition_levels = set([0, 1])
  threshold_sec = 15
  
  #get the matches for it
  try:
    match_str = thread_local.segment_matcher.Match(json.dumps(trace, separators=(',', ':')))
    match = json.loads(match_str)
    report = reporter_service.report(match, trace, threshold_sec, report_levels, transition_levels)
  except:
    logger.error('Failed to report trace %s' % file_name)
    raise Exception('Failed to report trace %s' % json.dumps(trace, separators=(',', ':')))
  
  #weed out the usable segments and then send them off to the time tiles
  segments = [ r for r in report['datastore']['reports'] if r['t0'] > 0 and r['t1'] > 0 and r['t1'] - r['t0'] > .5 and r['length'] > 0 and r['queue_length'] >= 0 ]
  for r in segments:
    duration = int(round(r['t1'] - r['t0']))
    start = int(math.floor(r['t0']))
    end = int(math.ceil(r['t1']))
    min_bucket = int(start / quantisation)
    max_bucket = int(end / quantisation)
    for b in range(min_bucket, max_bucket + 1):
      tile_level = str(get_tile_level(r['id']))
      tile_index = str(get_tile_index(r['id']))
      file_name = dest_dir + os.sep + str(b * quantisation) + '_' + str((b + 1) * quantisation - 1) + os.sep + tile_level + os.sep + tile_index
      #append to a file
      try: os.makedirs(os.sep.join(file_name.split(os.sep)[:-1]))
      except: pass
      with open(file_name, 'a', 1) as f:
        s = [
          str(r['id']),
          str(r.get('next_id', INVALID_SEGMENT_ID)),
          str(duration),
          '1',
          str(r['length']),
          str(r['queue_length']),
          str(start),
          str(end),
          source,
          'AUTO'
        ]
        f.write(','.join(s) + os.linesep)

  #TODO: return the stats part so we can merge them together later on

def local_matcher():
  setattr(thread_local, 'segment_matcher', valhalla.SegmentMatcher())

def make_matches(trace_dir, config, quantisation, source, threads):
  #download and parse them into proper files
  dest_dir = tempfile.mkdtemp(dir='')
  logger.info('Matching trace data to osmlr segments into %s' % dest_dir)
  valhalla.Configure(config)
  pool = ThreadPool(threads, local_matcher)
  total = 0.0
  for root, dirs, files in os.walk(trace_dir):
    for file_name in files:
      pool.add_task(match, root + os.sep + file_name, quantisation, source, dest_dir)
      total += 1
  logger.info('%d traces have been queued' % total)

  #monitor progress
  progress = -1
  while pool.queue_size() > 0:
   p = int((1.0 - (pool.queue_size() / total)) * 20) * 5
   if p > progress:
     logger.info('Matching trace data %d%%' % p)
     progress = p
   time.sleep(1)
  pool.join()
  if progress != 100:
    logger.info('Matching trace data 100%')
  logger.info('Done matching trace data')
  return dest_dir
  
def report(file_name, bucket, privacy):
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

  #write the lines to a file like object and upload it
  with contextlib.closing(cStringIO.StringIO()) as f:
    f.write('segment_id,next_segment_id,duration,count,length,queue_length,minimum_timestamp,maximum_timestamp,source,vehicle_type' + os.linesep)
    for s in segments:
      f.write(s)
    thread_local.client.put_object(
      Bucket=bucket,
      Body=f.getvalue(),
      Key='/'.join(file_name.split(os.sep)[1:]) + '/' + hashlib.sha1(file_name).hexdigest())  

def report_tiles(match_dir, bucket, privacy, threads):
  #download and parse them into proper files
  logger.info('Reporting anonymised time tiles')
  pool = ThreadPool(threads, local_session)
  total = 0.0
  for root, dirs, files in os.walk(match_dir):
    for file_name in files:
      pool.add_task(report, root + os.sep + file_name, bucket, privacy)
      total += 1
  logger.info('%d tiles have been queued' % total)

  #monitor progress
  progress = -1
  while pool.queue_size() > 0:
   p = int((1.0 - (pool.queue_size() / total)) * 20) * 5
   if p > progress:
     logger.info('Reporting tiles %d%%' % p)
     progress = p
   time.sleep(1)
  pool.join()
  if progress != 100:
    logger.info('Reporting tiles 100%')
  logger.info('Done reporting tiles')

def check_box(bbox):
  b = [ float(b) for b in bbox.split(',') ]
  if b[0] < -90 or b[1] < -180 or b[2] > 90 or b[3] > 180 or b[0] >= b[2] or b[1] >= b[3]:
    raise argeparse.ArgumentTypeError('%s is not a valid bbox' % bbox)
  return b

if __name__ == '__main__':
  #build args
  parser = argparse.ArgumentParser()
  parser.add_argument('--src-bucket', type=str, help='Bucket where to get the input trace data from', required=True)
  parser.add_argument('--src-prefix', type=str, help='Bucket prefix for getting source data', required=True)
  parser.add_argument('--src-key-regex', type=str, help='Bucket key regex for getting source data', default='.*')
  parser.add_argument('--src-keyer', type=str, help='A lambda used to extract the key from a given message in the input', default='lambda l: l.split("|")[1]')
  parser.add_argument('--src-valuer', type=str, help='A lambda used to extract the time, lat, lon, accuracy from a given message in the input', default='lambda l: functools.partial(lambda c: [c[0], c[9], c[10], c[5] ], l.split("|"))()')
  parser.add_argument('--src-time-pattern', type=str, help='A string used to extract epoch seconds from a time string', default='%Y-%m-%d %H:%M:%S')
  parser.add_argument('--match-config', type=str, help='A file containing the config for the map matcher', required=True)
  parser.add_argument('--quantisation', type=int, help='How large are the buckets to make tiles for. They should always be an hour (3600 seconds)', default=3600)
  parser.add_argument('--privacy', type=int, help='How many readings of a given segment pair must appear before it being reported', default=2)
  parser.add_argument('--source-id', type=str, help='A simple string to identify where these readings came from', default='smpl_rprt')
  parser.add_argument('--dest-bucket', type=str, help='Bucket where we want to put the reporter output', required=True)
  parser.add_argument('--concurrency', type=int, help='Number of threads to use when doing various stages of processing', default=multiprocessing.cpu_count())
  parser.add_argument('--bbox', type=check_box, help='Comma separated coordinates within which data will be reported: min_lat,min_lon,max_lat,max_lon', default=[-90.0,-180.0,90.0,180.0])
  parser.add_argument('--trace-dir', type=str, help='To bypass trace gathering supply the directory with already parsed traces')
  parser.add_argument('--match-dir', type=str, help='To bypass trace matching supply the directory with the already matched segments')
  args = parser.parse_args()

  #fetch the data and divide it up
  exec('keyer = ' + args.src_keyer)
  exec('valuer = ' + args.src_valuer)
  if not args.trace_dir and not args.match_dir:
    args.trace_dir = get_traces(args.src_bucket, args.src_prefix, re.compile(args.src_key_regex), keyer, valuer, args.src_time_pattern, args.bbox, args.concurrency)

  #do matching on every file
  if not args.match_dir:
    args.match_dir = make_matches(args.trace_dir, args.match_config, args.quantisation, args.source_id, args.concurrency)

  #filter and upload all the data
  report_tiles(args.match_dir, args.dest_bucket, args.privacy, args.concurrency)

  #clean up the data
  #os.remove(src_dir)
  #os.remove(match_dir)
