#!/usr/bin/env python

'''
If you're running this from this directory you can start the server with the following command:
PYTHONPATH=PYTHONPATH:../../valhalla/valhalla/.libs DATASTORE_URL=http://localhost:8003/store? py/reporter_service.py ../../conf/manila.json localhost:8002

sample url looks like this:
http://localhost:8002/report?json=
'''
import os
import sys
import json
import multiprocessing
import threading
import socket
from Queue import Queue
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
from cgi import urlparse
import requests
import valhalla
import pickle
import math
from distutils.util import strtobool

actions = set(['report'])

#this is where thread local storage lives
thread_local = threading.local()

#use a thread pool instead of just frittering off new threads for every request
class ThreadPoolMixIn(ThreadingMixIn):
  allow_reuse_address = True  # seems to fix socket.error on server restart

  def serve_forever(self):
    # set up the threadpool
    if 'THREAD_POOL_COUNT' in os.environ:
      pool_size = int(os.environ.get('THREAD_POOL_COUNT'))
    else:
      pool_size = int(os.environ.get('THREAD_POOL_MULTIPLIER', 1)) * multiprocessing.cpu_count()
    self.requests = Queue(pool_size)
    for x in range(pool_size):
      t = threading.Thread(target = self.process_request_thread)
      t.setDaemon(1)
      t.start()
    # server main loop
    while True:
      self.handle_request()
    self.server_close()

  def make_thread_locals(self):
    setattr(thread_local, 'segment_matcher', valhalla.SegmentMatcher())

    #Set the threshold for last segment
    threshold_sec = 15
    if os.environ.get('THRESHOLD_SEC'):
      threshold_sec = bool(strtobool(str(os.environ.get('THRESHOLD_SEC'))))
    setattr(thread_local, 'threshold_sec', threshold_sec)

  def process_request_thread(self):
    self.make_thread_locals()
    while True:
      request, client_address = self.requests.get()
      ThreadingMixIn.process_request_thread(self, request, client_address)
    
  def handle_request(self):
    try:
      request, client_address = self.get_request()
    except socket.error:
      return
    if self.verify_request(request, client_address):
      self.requests.put((request, client_address))

#enable threaded server
class ThreadedHTTPServer(ThreadPoolMixIn, HTTPServer):
  pass

#report some segments for the datastore
def report(segments, trace, threshold_sec, report_levels, transition_levels):
  #Get the end time
  end_time = trace['trace'][len(trace['trace']) - 1]['time']

  #Walk from the last segment until a segment is found where the difference between
  #the end time and the segment begin time exceeds the threshold
  last_idx = len(segments['segments'])-1
  while last_idx >= 0 and end_time - segments['segments'][last_idx]['start_time'] < threshold_sec:
    last_idx -= 1

  #Trim shape to the beginning of the last segment
  shape_used = None
  if last_idx >= 0:
    shape_used = segments['segments'][last_idx]['begin_shape_index']

  #Compute values to send to the datastore: start time for a segment
  #next segment (if any), start time at the next segment (end time of segment if no next segment)
  segments['mode'] = 'auto'
  prior_segment_id = None
  first_seg = True
  idx, successful_count, unreported_count, successful_length, unreported_length, discontinuities_count, invalid_time_count, invalid_speed_count, unassociated_seg_count = [0 for _ in range(9)]
  datastore_out = {}
  datastore_out['mode'] = 'auto'
  datastore_out['reports'] = []
  while idx <= last_idx:
    seg = segments['segments'][idx]
    segment_id = seg.get('segment_id')
    way_ids = seg.get('way_ids')
    start_time = seg.get('start_time')
    end_time = seg.get('end_time')
    #internal means the segment is an internal intersection, turn channel, roundabout
    internal = seg.get('internal', False)
    queue_length = seg.get('queue_length')
    #length = -1 means this is a partial OSMLR segment match
    length = seg.get('length')
    #report a count of the number of matches that include discontinuities (a partial end time followed by a partial start time that are consecutive) as invalid
    if idx != 0 and segments['segments'][idx]['start_time'] == -1 and segments['segments'][idx-1]['end_time'] == -1:
      discontinuities_count += 1

    #check if segment Id is on the local level
    level = (segment_id & 0x7) if segment_id != None else -1

    #Conditionally output prior segment if it is complete and the level is configured to be reported
    if prior_segment_id != None and prior_length > 0 and internal != True:
      if prior_level in report_levels:
        #Add the prior segment.
        report = {'id': prior_segment_id, 't0' : prior_start_time, 't1' : (start_time if level in transition_levels else prior_end_time), 'length' : prior_length, 'queue_length' : prior_queue_length }
        if level in transition_levels and segment_id is not None:
          report['next_id'] = segment_id

        #Validate start and end times and ensure speed is not too high
        dt = float(report['t1']) - float(report['t0'])
        if dt <= 0 or math.isinf(dt) or math.isnan(dt):
          invalid_time_count += 1
        elif (prior_length / dt) * 3.6 > 160:
          invalid_speed_count += 1
        else:
          datastore_out['reports'].append(report)
          successful_count += 1
          successful_length = round((prior_length * 0.001),3) #convert meters to km
      #Log prior segments on local level not being reported; lets do a count and track prior_segment_ids
      else:
        unreported_count += 1
        unreported_length = round((prior_length * 0.001),3) #convert meters to km

    #Save state for next segment.
    if internal == True and first_seg != True:
      #Do not replace information on prior segment, except to mark the prior as internal
      prior_internal = internal
    else:
      prior_segment_id = segment_id
      prior_start_time = start_time
      prior_end_time = end_time
      prior_internal = internal
      prior_length = length
      prior_level = level
      prior_queue_length = queue_length

    first_seg = False
    idx += 1
    #Track segments that match to edges that do not have any OSMLR Id and are non-internal (turn channel, roundabout, internal intersection) -
    #Likely a service road (driveway, alley, parking aisle, etc.)
    if segment_id is None and internal == False:
      unassociated_seg_count += 1

  data = {'stats':{'successful_matches':{}, 'unreported_matches':{}, 'match_errors':{}}}
  if shape_used:
    data['shape_used'] = shape_used
  data['segment_matcher'] = segments
  data['datastore'] = datastore_out

  data['stats']['successful_matches']['count'] = successful_count
  data['stats']['successful_matches']['length'] = successful_length
  data['stats']['unreported_matches']['count'] = unreported_count
  data['stats']['unreported_matches']['length'] = unreported_length
  data['stats']['match_errors']['discontinuities'] = discontinuities_count
  data['stats']['match_errors']['invalid_speeds'] = invalid_speed_count
  data['stats']['match_errors']['invalid_times'] = invalid_time_count
  data['stats']['unassociated_segments'] = unassociated_seg_count

  return data

#custom handler for getting routes
class SegmentMatcherHandler(BaseHTTPRequestHandler):
  #boiler plate parsing
  def parse_trace(self, post):
    #split the query from the path
    try:
      split = urlparse.urlsplit(self.path)
    except:
      raise Exception('Try a url that looks like /action?query_string')
    #path has the action in it
    try:
      if split.path.split('/')[-1] not in actions:
        raise
    except:
      raise Exception('Try a valid action: ' + str([k for k in actions]))
    #handle POST
    if post:
      body = self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8')
      return json.loads(body)
    #handle GET
    else:
      params = urlparse.parse_qs(split.query)
      if 'json' in params:
        return json.loads(params['json'][0])
    raise Exception('No json provided')


  #parse the request because we dont get this for free!
  def handle_request(self, post):
    #get the trace data
    try:
      trace = self.parse_trace(post)
    except Exception as e:
      return 400, '{"error":"' + str(e) + '"}'

    #uuid is required
    uuid = trace.get('uuid')
    if uuid is None:
      return 400, '{"error":"uuid is required"}'

    #one or more points is required
    try:
      trace['trace'][1]
    except Exception as e:
      return 400, '{"error":"trace must be a non zero length array of object each of which must have at least lat, lon and time"}'

    #must have report and transition levels set
    try:
      report_levels = set(trace['match_options']['report_levels'])
    except Exception as e:
      return 400, '{"error":"match_options must include report_levels array"}'
    try:
      transition_levels = set(trace['match_options']['transition_levels'])
    except Exception as e:
      return 400, '{"error":"match_options must include transition_levels array"}'

    #possibly report on what we have
    try:
      #ask valhalla to give back OSMLR segments along this trace
      result = thread_local.segment_matcher.Match(json.dumps(trace, separators=(',', ':')))
      match = json.loads(result)
      data = report(match, trace, thread_local.threshold_sec, report_levels, transition_levels)
      return 200, json.dumps(data, separators=(',', ':'))
    except Exception as e:
      return 500, '{"error":"' + str(e) + '"}'

  #send an answer
  def answer(self, code, body):
    try:
      self.send_response(code)

      #set some basic info
      self.send_header('Access-Control-Allow-Origin','*')
      self.send_header('Content-type', 'application/json;charset=utf-8')
      self.send_header('Content-length', len(body))
      self.end_headers()

      #hand it back
      self.wfile.write(body)
    except:
      pass

  #handle the request
  def do(self, post):
    try:
      code, body = self.handle_request(post)
      self.answer(code, body)
    except Exception as e:
      self.answer(400, str(e))

  def do_GET(self):
    self.do(False)
  def do_POST(self):
    self.do(True)


#go off and wait for connections
if __name__ == '__main__':
  #check for a config file
  conf = {}
  try:
    with open(sys.argv[1]) as f:
      conf = json.load(f)
    valhalla.Configure(sys.argv[1])
    address = sys.argv[2].split('/')[-1].split(':')
    address[1] = int(address[1])
    address = tuple(address)
  except Exception as e:
    sys.stderr.write('Problem with config file: {0}\n'.format(e)) 
    sys.exit(1)

  #setup the server
  SegmentMatcherHandler.protocol_version = 'HTTP/1.0'
  httpd = ThreadedHTTPServer(address, SegmentMatcherHandler)

  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    httpd.server_close()

