#!/usr/bin/env python

'''
That will create a file of json reporter requests from a gpx file.
'''
import sys
import StringIO
import json
from xml.etree import ElementTree
import xmltodict,json
from datetime import datetime, date

actions = { 'segment_match': None }

"""
#this converts full xml to json
#xml_file = '/home/kdiluca/sandbox/tools/py/gpx/gpx-planet-2013-04-09/identifiable/001/051/001051629.gpx'
with open(xml_file, "rb") as f:    # notice the "rb" mode
    d = xmltodict.parse(f, xml_attribs=True)
    print json.dumps(d, indent=4)
"""


gpxfile = open(sys.argv[1], 'r')
tree = ElementTree.parse(gpxfile)
json_list = []
gpx_list = []
prev = 0
elapsed_time = 0

for node in tree.iter(): 
  if 'name' in node.tag:
    name = ElementTree.tostring(node, encoding='utf8', method='text')
    namestr = '"name":' + name + ','

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
    jsonstr = '{"lat":' + lat + ',"lon":' + lon + ',"time":' + str(delta_time) +'},'
    json_list.append(jsonstr)

    gpx_list.extend(json_list)
    gpx_list_out = open('/home/kdiluca/sandbox/reporter/py/gpx.json', 'w')
    gpx_list_out.write('{"trace":[')
    for line in gpx_list:
      gpx_list_out.write(line)
    gpx_list_out.write(']}\n')
    json_list = []
    gpx_list_out.close()
    elapsed_time = 0

 
