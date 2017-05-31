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

    local_reporting = False
    if os.environ.get('LOCAL_REPORTING'):
      local_reporting = bool(strtobool(str(os.environ.get('LOCAL_REPORTING'))))
    setattr(thread_local, 'local_reporting', local_reporting)

    threshold_sec = None
    if os.environ.get('THRESHOLD_SEC'):
      threshold_sec = bool(strtobool(str(os.environ.get('THRESHOLD_SEC'))))
    setattr(thread_local, 'threshold_sec', threshold_sec)

    provider = os.environ.get('PROVIDER', '')
    setattr(thread_local, 'provider', provider)

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
  def report(self, trace, debug):
 
    #ask valhalla to give back OSMLR segments along this trace
    result = thread_local.segment_matcher.Match(json.dumps(trace, separators=(',', ':')))
    segments = json.loads(result)

    #remember how much shape was used
    #NOTE: no segments means your trace didnt hit any and we are purging it
    shape_used  = len(trace['trace']) if len(segments['segments']) or segments['segments'][-1].get('segment_id') is None or segments['segments'][-1]['length'] < 0 else segments['segments'][-1] ['begin_shape_index']

    #Compute values to send to the datastore: start time for a segment
    #next segment (if any), start time at the next segment (end time of segment if no next segment)
    segments['mode'] = 'auto'
    segments['provider'] = thread_local.provider
    prior_segment_id = None
    datastore_out = dict()
    datastore_out['mode'] = 'auto'
    datastore_out['provider'] = thread_local.provider
    datastore_out['reports'] = []

    #length = -1 means this is a partial OSMLR segment match
    #internal means the segment is an internal intersection, turn channel, roundabout
    for seg in segments['segments']:
      segment_id = seg.get('segment_id')
      start_time = seg.get('start_time')
      end_time = seg.get('end_time')
      internal = seg.get('internal')
      length = seg.get('length')

      #check if segment Id is on the local level
      local_level = True if segment_id != None and (segment_id & 0x3) == 2 else False

      #Output if both this segment and prior segment are complete
      if (segment_id != None and length > 0 and prior_segment_id != None and prior_length > 0):
        #Conditionally output prior segments on local level
        if prior_local_level != None:
          if thread_local.local_reporting == True:
            #Add segment (but empty next segment)
            report = dict()
            report['id'] = prior_segment_id
            report['next_id'] = 0
            report['t0'] = prior_start_time
            report['t1']= prior_end_time
            report['length'] = prior_length
            datastore_out['reports'].append(report)
        else:
          #Add the prior segment. Next segment is set to empty if transition onto local level
          report = dict()
          report['id'] = prior_segment_id
          report['next_id'] = segment_id if local_level == False else 0
          report['t0'] = prior_start_time
          report['t1']= start_time if local_level == False else prior_end_time
          report['length'] = prior_length
          datastore_out['reports'].append(report)

      #Save state for next segment.
      if internal != None:
        #Do not replace information on prior segment, except to mark the prior as internal
        prior_internal = internal
      else:
        prior_segment_id = segment_id
        prior_start_time = start_time
        prior_end_time = end_time
        prior_internal = internal
        prior_length = length
        prior_local_level = local_level

    if not datastore_out['reports']:
      datastore_out.pop('reports')
    data = dict()
    data['shape_used'] = shape_used
    data['segment_matcher'] = segments
    data['datastore'] = datastore_out
    #Now we will send the whole segments on to the datastore
    if debug == False:
      if os.environ.get('DATASTORE_URL') and len(reports):
        response = requests.post(os.environ['DATASTORE_URL'], datastore_json)
        if response.status_code != 200:
          raise Exception(response.text)
      data['shape_used'] = shape_used
      
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

    if trace.get('debug'):
      try:
        pdb.set_trace()
        debug = bool(strtobool(str(trace.get('debug'))))
      except:
        debug = False
    else:
     debug = False

    #one or more points is required
    try:
      trace['trace'][1]
    except Exception as e:
      return 400, '{"error":"trace must be a non zero length array of object each of which must have at least lat, lon and time"}'

    #possibly report on what we have
    try:
      return 200, self.report(trace, debug)
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

