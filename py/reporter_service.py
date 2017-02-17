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

actions = { 'segment_match': None }

#use a thread pool instead of just frittering off new threads for every request
class ThreadPoolMixIn(ThreadingMixIn):
  allow_reuse_address = True  # seems to fix socket.error on server restart

  def serve_forever(self):
    # set up the threadpool
    self.requests = Queue(multiprocessing.cpu_count())
    for x in range(multiprocessing.cpu_count()):
      t = threading.Thread(target = self.process_request_thread)
      t.setDaemon(1)
      t.start()
    # server main loop
    while True:
      self.handle_request()
    self.server_close()

  def make_thread_locals(self):
    self.segment_matcher = valhalla.SegmentMatcher()
    self.cache = redis.Redis(host=os.environ['REDIS_HOST'])

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
    #pdb.set_trace()
    #get the reporter data
    trace = self.parse_trace(post)

    #lets get the uuid from json the request
    uuid = trace.get('uuid')
    if uuid is not None:
      #do we already know something about this vehicleId already? Let's check Redis
      partial_kv = self.server.cache.get(uuid)
      #if partial_kv is not None:
        #TODO: we will need to prepend the last bit of shape from the partial_end segment that's already in Redis 
        # to the rest of the partial_start segment once it is returned from the segment_matcher
        #params['partial_start'] = json.loads(partial_kv)
    else:
      return 400, 'No uuid in segment_match request!'

    #ask valhalla to give back OSMLR segments along this trace
    result = self.server.segment_matcher.Match(json.dumps(trace))
    segments = json.loads(result)

    #if there is something
    if len(segments['segments']):
      #if the last one is partial, store in Redis
      if segments['segments'][-1]['partial_end']:
        self.server.cache.setnx(uuid, segments['segments'][-1])
      #if any others are partial, we do not need so remove them
      segments['segments'] = [ seg for seg in segments['segments'] if not seg['partial_start'] and not seg['partial_end'] ]
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
    pprint.pprint(segments)
    #******************************************************************#

    #hand it back
    return 200, segments

  #send an answer
  def answer(self, code, body):
    response = json.dumps({'response': body })
    self.send_response(code)

    #set some basic info
    self.send_header('Access-Control-Allow-Origin','*')
    self.send_header('Content-type', 'application/json;charset=utf-8')
    self.send_header('Content-length', len(response))
    self.end_headers()

    #hand it back
    self.wfile.write(response)

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

