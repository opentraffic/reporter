#!/usr/bin/env python

'''
If you're running this from this directory you can start the server with the following command:
PYTHONPATH=PYTHONPATH:../../valhalla/valhalla/.libs REDIS_HOST=localhost DATASTORE_URL=http://localhost:8003/store? pdb py/reporter_service.py ../../conf/manila.json localhost:8002

***NOTE:: Remove pdb from command and pdb.trace() below if you don't want to debug

sample url looks like this:
http://localhost:8002/segment_match?json=
'''
import os
import sys
import json
import redis
import multiprocessing
import threading
import socket
from Queue import Queue
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
from cgi import urlparse
import requests
import valhalla
#import pdb
import pprint
import pickle

actions = set(['report'])

# this is where thread local storage lives
thread_local = threading.local()

#use a thread pool instead of just frittering off new threads for every request
class ThreadPoolMixIn(ThreadingMixIn):
  allow_reuse_address = True  # seems to fix socket.error on server restart

  def serve_forever(self):
    # set up the threadpool
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
    setattr(thread_local, 'cache', redis.Redis(host=os.environ['REDIS_HOST']))

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

  #parse the request because we dont get this for free!
  def handle_request(self, post):
    #get the reporter data
    trace = self.parse_trace(post)

    #lets get the uuid from json the request
    uuid = trace.get('uuid')
    #pdb.set_trace()
    if uuid is not None:
      #do we already know something about this vehicleId already? Let's check Redis
      partial = thread_local.cache.get(uuid)
      if partial:
        partial = pickle.loads(partial)
        time_diff = trace['trace'][0]['time'] - partial[-1]['time']
        #check to make sure time is not stale and not in future
        if time_diff < os.environ.get('STALE_TIME', 60) and time_diff >= 0:
          #Now prepend the last bit of shape from the partial_end segment that's already in Redis
          #to the rest of the partial_start segment once it is returned from the segment_matcher
          trace['trace'] = partial + trace['trace']
    else:
      return 400, 'No uuid in segment_match request!'

    #ask valhalla to give back OSMLR segments along this trace
    result = thread_local.segment_matcher.Match(json.dumps(trace, separators=(',', ':')))
    segments = json.loads(result)
    #print '###########Segment Matcher Response, can include partials'
    #pprint.pprint(segments)

    #if there are segments
    if len(segments['segments']):
      #if the last one is partial, store in Redis
      if segments['segments'][-1]['length'] < 0:
        #gets the begin index of the last partial
        begin_index = segments['segments'][-1]['begin_shape_index']
        #in Redis, set the uuid as key and trace from the begin index to the end
        thread_local.cache.set(uuid, pickle.dumps(trace['trace'][begin_index:]), ex=os.environ.get('PARTIAL_EXPIRY', 300))
      #if any others are partial, we do not need so remove them
      segments['segments'] = [ seg for seg in segments['segments'] if seg['length'] > 0 ]
      segments['mode'] = "auto"
      segments['provider'] = "GRAB" #os.enviorn['PROVIDER_ID']
      #segments['reporter_id'] = os.environ['REPORTER_ID']

      #Now we will send the whole segments on to the datastore
      if len(segments['segments']):
        response = requests.post(os.environ['DATASTORE_URL'], json.dumps(segments))
        if response.status_code != 200:
          sys.stderr.write(response.text)
          sys.stderr.flush()
          return 500, response.text

    #******************************************************************#
    #QA CHECKS
    #prints segments array info to terminal in csv format if partial start and end are false
    #print '###########Complete Segments Stored in Datastore'
    #pprint.pprint(segments)
    #******************************************************************#

    #hand it back
    return 200, 'Reported on %d segments' % len(segments['segments'])

  #send an answer
  def answer(self, code, body):
    response = json.dumps({'response': body })
    try:
      self.send_response(code)

      #set some basic info
      self.send_header('Access-Control-Allow-Origin','*')
      self.send_header('Content-type', 'application/json;charset=utf-8')
      self.send_header('Content-length', len(response))
      self.end_headers()

      #hand it back
      self.wfile.write(response)
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
    os.environ['REDIS_HOST']
    os.environ['DATASTORE_URL']

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

