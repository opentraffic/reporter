#!/usr/bin/env python

'''
If you're running this from this directory you can start the server with the following command:
PYTHONPATH=PYTHONPATH:../../valhalla/valhalla/.libs REDIS_HOST=127.0.0.1 DATASTORE_URL='http://localhost:8003/store?' pdb py/reporter_service.py ../../conf/manila.json localhost:8002

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
import pdb
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

  def process_request_thread(self):
    self.segment_matcher = valhalla.SegmentMatcher()
    '''create redis env var to determine where to find Redis for each thread'''
    self.cache = redis.Redis(host=os.environ['REDIS_HOST'])
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

  #parse the request because we dont get this for free!
  def handle_request(self, post):
    #split the query from the path
    try:
      split = urlparse.urlsplit(self.path)
    except:
      raise Exception('Try a url that looks like /action?query_string')
    #path has the costing method and action in it
    try:
      action = actions[split.path.split('/')[-1]]
    except:
      raise Exception('Try a valid action: ' + str([k for k in actions]))
    #get a dict and unexplode non-list entries
    params = urlparse.parse_qs(split.query)
    for k,v in params.iteritems():
      if len(v) == 1:
        params[k] = v[0]

    #save jsonp or not
    jsonp = params.get('jsonp', None)
    if params.has_key('json'):
      params = json.loads(params['json'])
    if jsonp is not None:
      params['jsonp'] = jsonp
    #handle POST
    if post:
      params = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8'))

    #lets get the vehicle id from json the request
    if params['vehicleId']:
      print params['vehicleId']
      #do we already know something about this vehicleId already? Let's check Redis
      partial_kv = self.server.cache.get(params['vehicleId'])
      if partial_kv is not None:
        print "Partial key value for this vehicle already exists in Redis"
        #TODO: we will need to prepend the last bit of shape from the partial_end segment that's already in Redis 
        # to the rest of the partial_start segment once it is returned from the segment_matcher
        #params['partial_start'] = json.loads(partial_kv)
      else:
        print "This vehicleId does not exist in cache " + params['vehicleId']
    else:
        raise Exception('No vehicleId in segment_match request!')

    #this return was used to avoid redis
    #return params, False

    pdb.set_trace()
    #ask valhalla to give back OSMLR segments along this trace
    result = self.server.segment_matcher.Match(json.dumps(params))
    segments_dict = json.loads(result)

    if len(segments_dict['segments']):
      #if the last one is partial, store in Redis
      if segments_dict['segments'][-1]['partial_end']:
        self.server.cache.setnx(params['vehicleId'], segments_dict['segments'][-1])
      #if any others are partial, we do not need so remove them
      segments_dict['segments'] = [ seg for seg in segments_dict['segments'] if not seg['partial_start'] and not seg['partial_end'] ]

      #Now we will send the whole segments on to the datastore
      segments_dict['mode'] = "auto"
      segments_dict['provider'] = "GRAB"
      #segments_dict['reporter_id'] = os.environ['REPORTER_ID']
      response = requests.post(url=os.environ['DATASTORE_URL'], data=json.dumps(segments_dict))

      if response.status_code != 200:
        sys.stderr.write(response.text)
        sys.stderr.flush()

    #******************************************************************#
    #QA CHECKS
    #prints segments array info to terminal in csv format if partial start and end are false
    '''Segments need to be stored in the datastore'''
    pprint.pprint(segments_dict['segments'])
    #******************************************************************#

    #javascriptify this
    if jsonp:
      result = jsonp + '=' + result + ';'
    #hand it back
    return result, jsonp is not None

  #send a success
  def succeed(self, response, jsonp):
    self.send_response(200)

    #set some basic info
    self.send_header('Access-Control-Allow-Origin','*')
    if jsonp:
      self.send_header('Content-type', 'text/plain;charset=utf-8')
    else:
      self.send_header('Content-type', 'application/json;charset=utf-8')
      self.send_header('Content-length', len(response))
    self.end_headers()

    #hand it back
    self.wfile.write(response)

  #send a fail
  def fail(self, error):
    self.send_response(400)

    #set some basic info
    self.send_header('Access-Control-Allow-Origin','*')
    self.send_header('Content-type', 'text/plain;charset=utf-8')
    self.send_header('Content-length', len(error))
    self.end_headers()

    #hand it back
    self.wfile.write(str(error))

  #handle the request
  def do_GET(self):
    #get out the bits we care about
    try:
      response, jsonp = self.handle_request(False)
      self.succeed(response, jsonp)
    except Exception as e:
      self.fail(str(e))

  #handle the request
  def do_POST(self):
    #get out the bits we care about
    try:
      response, jsonp = self.handle_request(True)
      self.succeed(response, jsonp)
    except Exception as e:
      self.fail(str(e))


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

