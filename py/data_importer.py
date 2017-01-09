#!/usr/bin/env python

'''
If you're running this from this directory you can start it with some incantation such as:
PYTHONPATH=$PYTHONPATH:../../tools.libs ./data_importer.py ../../conf/manila.json localhost:8002
'''

import sys
import StringIO
import json
import threading
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
from cgi import urlparse
import valhalla
import csv,json,requests
from operator import itemgetter
from datetime import datetime, date
import urllib

'''
sample url looks like this:
http://localhost:8002/?
'''

actions = { 'segment_match': None }

prev = 0
elapsed_time = 0

csvfile = open('/data/traffic/manila', 'r')
jsonfile = open('reporter_requests.json', 'w')

fieldnames = ("time","vehicleId","lat","lon")
reader = csv.DictReader(csvfile, fieldnames=None)
prior_vehicle_id = 0
for row in sorted(reader, key=itemgetter(fieldnames[1], fieldnames[0])):
    epoch = datetime(1970,1,1)
    i = datetime.strptime(row.get(fieldnames[0]),"%Y-%m-%dT%H:%M:%S.%fZ")
    delta_time = int((i - epoch).total_seconds())
    start_time = delta_time
    if (prev != 0):
        elapsed_time += delta_time - prev
    else:
        elapsed_time += delta_time - start_time
    prev = start_time
    #TODO: Need to replace times with int time
    #row.update((fieldnames[0],delta_time) for fieldnames[0] in row)
    
    if prior_vehicle_id == 0:
        # First row - start a new trace URL
        jsonfile.write('http://localhost:8002/segment_match?json={"trace":[')
        json.dump(row, jsonfile)
    elif row.get(fieldnames[1]) == prior_vehicle_id:
        # Continuation of same vehicle Id - add to current URL
        jsonfile.write(',')
        json.dump(row, jsonfile)
    else:
        # End the prior URL. Ideally we would send a URL to the reporter...
        jsonfile.write(']}' + '\n')
        # Start a new URL
        jsonfile.write('http://localhost:8002/segment_match?json={"trace":[')
        json.dump(row, jsonfile)
    # Update prior_vehicle Id
    prior_vehicle_id = row.get(fieldnames[1])
 
# Close off the last URL (ideally send to reporter)
jsonfile.write(']}')
jsonfile.close()


#TODO: what do do with last few traces that total to < 60 sec?


#enable threaded server
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

#TODO: send json requests to segment matcher instead of to request file

#custom handler for getting routes
class SegmentMatcherHandler(BaseHTTPRequestHandler):
    def __init__(self, *args):
        self.segment_matcher = valhalla.SegmentMatcher()
        BaseHTTPRequestHandler.__init__(self, *args)

    #parse the request because we dont get this for free!
    def handle_request(self):
        self.path = urllib.urlopen(url)
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

        result = self.segment_matcher.Match(json.dumps(params))

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
	    	response, jsonp = self.handle_request()
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
    server = sys.argv[2].split('/')[-1].split(':')
    server[1] = int(server[1])
    server = tuple(server)
  except Exception as e:
    sys.stderr.write('Problem with config file: {0}\n'.format(e)) 
    sys.exit(1)

  #setup the server
  SegmentMatcherHandler.protocol_version = 'HTTP/1.0'
  httpd = ThreadedHTTPServer(server, SegmentMatcherHandler)

  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    httpd.server_close()

