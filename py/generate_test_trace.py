
import sys
import json
import requests
import time as t
from random import shuffle
import itertools

def decode(encoded):
    inv = 1.0 / 1e6
    decoded = []
    previous = [0, 0]
    i = 0
    while i < len(encoded):
        ll = [0, 0]
        for j in [0, 1]:
            shift = 0
            byte = 0x20
            while byte >= 0x20:
                byte = ord(encoded[i]) - 63
                i += 1
                ll[j] |= (byte & 0x1f) << shift
                shift += 5
            ll[j] = previous[j] + \
                (~(ll[j] >> 1) if ll[j] & 1 else (ll[j] >> 1))
            previous[j] = ll[j]
        decoded.append(
            [float('%.6f' % (ll[1] * inv)), float('%.6f' % (ll[0] * inv))])
    return decoded

def synthesize_gps(edges, shape, distribution="normal",
                   stddev=0, uuid='999999'):

    jsonDict = {"uuid": uuid, "trace": []}
    coords = decode(shape)
    maxCoordIndex = max([edge['end_shape_index'] for edge in edges])
    if maxCoordIndex >= len(coords):
        return None, None
    sttm = t.time() - 86400   # yesterday
    for i, edge in enumerate(edges):

        dist = edge['length']
        speed = edge['speed']

        beginShapeIndex = edge['begin_shape_index']
        endShapeIndex = edge['end_shape_index']
        lon, lat = coords[endShapeIndex]

        if i == 0:
            st_lon, st_lat = coords[beginShapeIndex]

        if stddev > 0:
            avgLat = np.mean(np.array(coords)[:, 1])
            # approx. 111.111 km per deg lon unless very close to the poles
            stddevLon = stddev / 111.111
            # approx 111.111 km * cos(lat) per deg lat
            stddevLat = stddev / (111.111 * np.cos(avgLat))
            lon += np.random.normal(scale=stddevLon)
            lat += np.random.normal(scale=stddevLat)
        dur = dist / speed * 3600.0
        time = sttm + dur
        time = int(round(time))
        if i == 0:
            st_lon, st_lat = coords[beginShapeIndex]
            jsonDict["trace"].append(
                {"lat": st_lat, "lon": st_lon, "time": sttm, "accuracy": min(
                    5, stddev * 1e3)})
        jsonDict["trace"].append(
            {"lat": lat, "lon": lon, "time": time, "accuracy": min(
                5, stddev * 1e3)})
        sttm = time

    return jsonDict

def get_route_shape(stLat, stLon, endLat, endLon):
    jsonDict = {"locations": [
        {"lat": stLat, "lon": stLon, "type": "break"},
        {"lat": endLat, "lon": endLon, "type": "break"}],
        "costing": "auto", "id": "test_route"}
    payload = {"json": json.dumps(jsonDict, separators=(',', ':'))}
    baseUrl = 'http://localhost:8002/route'
    route = requests.get(baseUrl, params=payload)
    shape = route.json()['trip']['legs'][0]['shape']
    print(route.url)
    if route.status_code == 200:
        return shape
    else:
        print 'No shape returned'

def get_trace_attrs(shape):
    jsonDict = {
        "encoded_polyline": shape,
        "costing": "auto",
        "directions_options": {"units": "kilometers"},
        "shape_match": "edge_walk",
        "trace_options": {"turn_penalty_factor": 500}}
    payload = {"json": json.dumps(jsonDict, separators=(',', ':'))}
    baseUrl = 'http://localhost:8002/trace_attributes?'
    matched = requests.get(baseUrl, params=payload)
    edges = matched.json()['edges']
    print(matched.url)
    return edges


if __name__ == '__main__':
  try:
    lat1 = sys.argv[1]
    lon1 = sys.argv[2]
    lat2 = sys.argv[3]
    lon2 = sys.argv[4]
    shape = get_route_shape(lat1, lon1, lat2, lon2)
    print("")
    edges = get_trace_attrs(shape)
    print("")
    optionsDict = {
        "match_options": {"mode":"bicycle"}}
    report_json = synthesize_gps(edges, shape)
    report_json.update(optionsDict)
    payload = {"json": json.dumps(report_json, separators=(',', ':'))}
    baseUrl = 'http://localhost:8001/report?'
    matched_segs = requests.get(baseUrl, params=payload)
    print(matched_segs.url)
    print("")
    datastore_out = matched_segs.json()['datastore']
    print(json.dumps(datastore_out, separators=(',', ':')))

  except:
    e = sys.exc_info()[0]
    print e


