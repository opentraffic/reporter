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

    #Set levels to report on, and levels to report transitions onto
    setattr(thread_local, 'report_levels', set([ int(i) for i in os.environ.get('REPORT_LEVELS', '0,1').split(',')]))
    setattr(thread_local, 'transition_levels', set([ int(i) for i in os.environ.get('TRANSITION_LEVELS', '0,1').split(',')]))

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


  #report some segments to the datastore
  def report(self, trace):
 
    #ask valhalla to give back OSMLR segments along this trace
    result = thread_local.segment_matcher.Match(json.dumps(trace, separators=(',', ':')))
    segments = json.loads(result)

    #Get the end time
    end_time = trace['trace'][len(trace['trace']) - 1]['time']

    #Walk from the last segment until a segment is found where the difference between
    #the end time and the segment begin time exceeds the threshold
    last_idx = len(segments['segments'])-1
    while (last_idx >= 0 and end_time - segments['segments'][last_idx]['start_time'] < thread_local.threshold_sec):
      last_idx -= 1

    #Trim shape to the beginning of the last segment
    shape_used = None
    if (last_idx >= 0):
      shape_used = segments['segments'][last_idx]['begin_shape_index']

    #Compute values to send to the datastore: start time for a segment
    #next segment (if any), start time at the next segment (end time of segment if no next segment)
    segments['mode'] = 'auto'
    prior_segment_id = None
    first_seg = True
    datastore_out = {}
    datastore_out['mode'] = 'auto'
    datastore_out['reports'] = []
    #length = -1 means this is a partial OSMLR segment match
    #internal means the segment is an internal intersection, turn channel, roundabout
    idx = 0
    while (idx <= last_idx):
      seg = segments['segments'][idx]
      segment_id = seg.get('segment_id')
      start_time = seg.get('start_time')
      end_time = seg.get('end_time')
      internal = seg.get('internal', False)
      length = seg.get('length')

      #check if segment Id is on the local level
      level = (segment_id & 0x7) if segment_id != None else -1

      #Output if both this segment and prior segment are complete
      if (segment_id != None and length > 0 and prior_segment_id != None and prior_length > 0):
        #Conditonally output prior segments on local level
        if prior_level in thread_local.report_levels:
          #Add the prior segment. Next segment is set to empty if transition onto local level
          report = dict()
          report['id'] = prior_segment_id
          report['next_id'] = segment_id if level in thread_local.transition_levels else None
          report['t0'] = prior_start_time
          report['t1']= start_time if level in thread_local.transition_levels else prior_end_time
          report['length'] = prior_length
          #Validate - ensure speed is not too high
          speed = (prior_length / (report['t1'] - report['t0'])) * 3.6
          if (speed < 200):
            datastore_out['reports'].append(report)
          else:
            #Log this as an error
            sys.stderr.write("Speed exceeds 200kph\n")

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

      first_seg = False
      idx += 1

    if not datastore_out['reports']:
      datastore_out.pop('reports')
    data = {}
    if shape_used:
      data['shape_used'] = shape_used
    data['segment_matcher'] = segments
    data['datastore'] = datastore_out
    return json.dumps(data, separators=(',', ':'))

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

    #possibly report on what we have
    try:
      return 200, self.report(trace)
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

