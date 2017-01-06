#!/usr/bin/env python

'''
If you're running this from this directory you can start it with some incantation such as:
PYTHONPATH=$PYTHONPATH:../../tools.libs ./matcher_service.py ../../conf/manila.json localhost:8002
'''

import sys
import StringIO
import json
import threading
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
from cgi import urlparse
import valhalla
from xml.etree import ElementTree
import json
from datetime import datetime, date

'''
sample url looks like this:
http://localhost:8002/?
'''

actions = { 'segment_match': None }

#TODO: read in multiple gpx files
#TODO: append all json responses to 1 csv file

sample_file = '/home/kdiluca/sandbox/reporter/py/data/001051629.gpx'
gpx = open(sample_file, 'r')
tree = ElementTree.parse(gpx)
json_list = []
gpx_list = []
prev = 0
elapsed_time = 0


#loop thru nodes
for node in tree.iter(): 
	#store name string
	if 'name' in node.tag:
		name = ElementTree.tostring(node, encoding='utf8', method='text')
		#namestr = '"name":' + name.strip() + ','
		namestr = name.strip()

	#store lat lon
	if 'lat' in node.attrib:
		lat = node.attrib.get('lat')
	if 'lon' in node.attrib:
		lon = node.attrib.get('lon')

    	#convert UTC to timestamp to datetime integer values of seconds
	if 'time' in node.tag:
		timestamp = ElementTree.tostring(node, encoding='utf8', method='text')
		epoch = datetime(1970,1,1)
		i = datetime.strptime(timestamp.strip(),"%Y-%m-%dT%H:%M:%SZ")
		delta_time = int((i - epoch).total_seconds())
		start_time = delta_time
		if (prev != 0):
			elapsed_time += delta_time - prev
		else:
			elapsed_time += delta_time - start_time

		prev = start_time

		#create json string from gpx traces and split out requests into approx. 60 second chunks based on elapsed time
		#jsonstr = {"lat":lat,"lon":lon,"time":str(delta_time)},
		jsonstr = '{"lat":' + lat + ',"lon":' + lon + ',"time":' + str(delta_time) +'},'
		if (elapsed_time > 60):
		    jsonstr = jsonstr[:-1]
		json_list.append(jsonstr)

		if (elapsed_time > 60):
			gpx_list.append('{"trace":[')
			#gpx_list.append(namestr)
			gpx_list.extend(json_list)
			gpx_list.append(']}')
			gpx_list.extend('\n')

			outfile = open('/home/kdiluca/sandbox/reporter/py/output/gpx_%s.json' %namestr, 'w')
			for line in gpx_list:
				#outfile.write(line)
				json.dumps(line, outfile)
			
			json_list = []
			outfile.close()
			elapsed_time = 0

#TODO: what do do with last few traces that total to < 60 sec?
    

#enable threaded server
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
  pass

#custom handler for getting routes
class SegmentMatcherHandler(BaseHTTPRequestHandler):

	def __init__(self, *args):
		self.segment_matcher = valhalla.SegmentMatcher()
		BaseHTTPRequestHandler.__init__(self, *args)

    #parse the request because we dont get this for free!
	def handle_request(self):
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

		"""
		trace_file = '/home/kdiluca/sandbox/reporter/py/output/gpx_'+namestr+'.json'
		with open(trace_file, 'r') as trace:		
 			for line in trace:		
 				result = self.segment_matcher.Match(json.dumps(line))
		"""

		#prints segments array info to terminal in csv format if partial start and end are false
		segments_dict = json.loads(result)
		for seg in segments_dict['segments']:
		    if "false" in seg['partial_start'] and "false" in seg['partial_end']:
		        print ','.join([seg['segment_id'], seg['begin_time'], seg['end_time'], seg['length']])
		    sys.stdout.flush()

				
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

