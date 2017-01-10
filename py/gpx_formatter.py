from xml.etree import ElementTree
from datetime import datetime, date
import json

sample_file = '/home/kdiluca/sandbox/reporter/py/001051629.gpx'
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

