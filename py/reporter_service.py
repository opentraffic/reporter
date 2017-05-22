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

    #clean out the unuseful partial segments
    segments['mode'] = 'auto'
    segments['provider'] = os.environ.get('PROVIDER', '')

    #Now we will send the whole segments on to the datastore
    if os.environ.get('DATASTORE_URL') and len(segments['segments']):
      response = requests.post(os.environ['DATASTORE_URL'], json.dumps(segments))
      if response.status_code != 200:
        raise Exception(response.text)

    return segments


  #parse the request because we dont get this for free!
  def handle_request(self, post):
    #get the reporter data
    trace = self.parse_trace(post)
    #uuid is required
    uuid = trace.get('uuid')
    if uuid is None:
      return 400, 'uuid is required'

    #one or more points is required
    try:
      trace['trace'][1]
    except Exception as e:
      return 400, 'trace must be a non zero length array of object each of which must have at least lat, lon and time'

    #possibly report on what we have
    try:
      segments = self.report(trace)
    except Exception as e:
      return 500, str(e)

    return 200, segments

  #send an answer
  def answer(self, code, body):
    if isinstance(body, str):
      response = json.dumps({'error': body}, separators=(',', ':'))
    else:
      response = json.dumps(body, separators=(',', ':'))

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

