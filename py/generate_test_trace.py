
import sys
import json
import requests
import time as t
from random import shuffle
import itertools
import pdb
import numpy as np
from pyproj import Proj, transform
from scipy.stats import norm
from shapely.geometry import LineString, MultiPoint, MultiLineString

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

def synthesize_gps(dfEdges, shapeCoords, localEpsg="2768", distribution="normal",
                   noise=0, sampleRate=1, uuid="999999", shapeMatch="map_snap",
                   mode="auto", turnPenaltyFactor=0, breakageDist=2000, beta=3,
                   sigmaZ=4.07, searchRadius=50):

    accuracy = round(min(100, norm.ppf(0.95, loc=0, scale=max(1, noise))), 2)
    mProj = Proj(init='epsg:{0}'.format(localEpsg))
    llProj = Proj(init='epsg:4326')
    jsonDict = {
        "uuid": uuid, "trace": [], "shape_match": shapeMatch,
        "match_options": {
            "mode": mode,
            "turn_penalty_factor": turnPenaltyFactor,
            "breakage_distance": breakageDist,
            "beta": beta,
            "sigma_z": sigmaZ,
            "search_radius": searchRadius,
            "gps_accuracy": accuracy}}
    trueRouteCoords = []
    resampledCoords = []
    gpsRouteCoords = []
    displacementLines = []
    lonAdjs = []
    latAdjs = []
    noiseLookback = int(np.ceil(30 / (sampleRate + 2)))
    sttm = int(t.time()) - 86400   # yesterday
    seconds = 0
    shapeIndexCounter = 0
    pdb.set_trace()
    for i, edge in enumerate(edges):
        if i == 0:
            trueCoords = shapeCoords[edge['begin_shape_index']]
            trueRouteCoords.append(trueCoords)
        trueCoords = shapeCoords[edge['end_shape_index']]
        trueRouteCoords.append(trueCoords)
        edgeShapeIndices = []
        for j, coordPair in enumerate(edge['oneSecCoords']):
            if (not seconds % sampleRate) | (
                (i + 1 == len(dfEdges)) &
                (j + 1 == len(edge['oneSecCoords']))
            ):
                lon, lat = coordPair
                resampledCoords.append([lon, lat])
                if noise > 0:
                    projLon, projLat = transform(llProj, mProj, lon, lat)
                    while True:
                        lonAdj = np.random.normal(scale=noise)
                        latAdj = np.random.normal(scale=noise)
                        if shapeIndexCounter == 0:
                            noiseQuad = [np.sign(lonAdj), np.sign(latAdj)]
                            break
                        elif [np.sign(lonAdj), np.sign(latAdj)] == noiseQuad:
                            break
                    lonAdjs.append(lonAdj)
                    latAdjs.append(latAdj)
                    newProjLon = projLon + np.mean(lonAdjs[-noiseLookback:])
                    newProjLat = projLat + np.mean(latAdjs[-noiseLookback:])
                    projLon, projLat = newProjLon, newProjLat
                    lon, lat = transform(mProj, llProj, projLon, projLat)
                time = sttm + seconds
                lat = round(lat, 6)
                lon = round(lon, 6)
                jsonDict["trace"].append({
                    "lat": lat, "lon": lon, "time": time})
                gpsRouteCoords.append([lon, lat])
                displacementLines.append([coordPair, [lon, lat]])
                edgeShapeIndices.append(shapeIndexCounter)
                shapeIndexCounter += 1
            seconds += 1

    return jsonDict

def convert_coords_to_meters(coords, localEpsg, inputOrder='lonlat'):
    if inputOrder == 'latlon':
        indices = [1, 0]
    elif inputOrder == 'lonlat':
        indices = [0, 1]
    else:
        print('"inputOrder" param cannot be processed')
    inProj = Proj(init='epsg:4326')
    outProj = Proj(init='epsg:{0}'.format(localEpsg))
    projCoords = [
        transform(inProj, outProj, coord[indices[0]], coord[indices[1]])
        for coord in coords]
    return projCoords

def get_coords_per_second(shapeCoords, edges, localEpsg):
    mProj = Proj(init='epsg:{0}'.format(localEpsg))
    llProj = Proj(init='epsg:4326')
    coords = shapeCoords
    projCoords = convert_coords_to_meters(coords, localEpsg=localEpsg)
    for i, edge in enumerate(edges):
        subSegmentCoords = []
        if i == 0:
            subSegmentCoords.append(coords[edge['begin_shape_index']])
        dist = edge['length']
        distMeters = dist * 1e3
        speed = edge['speed']
        mPerSec = speed * 1e3 / 3600.0
        beginShapeIndex = edge['begin_shape_index']
        endShapeIndex = edge['end_shape_index']
        if (beginShapeIndex >= len(coords) - 1) | \
           (endShapeIndex >= len(coords)):
            continue
        line = LineString(projCoords[beginShapeIndex:endShapeIndex + 1])
        seconds = 0
        while mPerSec * seconds < distMeters:
            seconds += 1
            newPoint = line.interpolate(mPerSec * seconds)
            newLon, newLat = transform(mProj, llProj, newPoint.x, newPoint.y)
            subSegmentCoords.append([newLon, newLat])
        if i == len(edges) - 1:
            subSegmentCoords.append(coords[edge['end_shape_index']])
        edge['oneSecCoords'] = subSegmentCoords
        edge['numOneSecCoords'] = len(subSegmentCoords)
    return edges

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
    matchedPts = decode(matched.json()['shape'])
    return edges, matchedPts

if __name__ == '__main__':
  try:
    lat1 = sys.argv[1]
    lon1 = sys.argv[2]
    lat2 = sys.argv[3]
    lon2 = sys.argv[4] 
    shape = get_route_shape(lat1, lon1, lat2, lon2)
    print("")
    edges, shapeCoords = get_trace_attrs(shape)
    print("")
    edges = get_coords_per_second(shapeCoords, edges, '2768')
    report_json = synthesize_gps(edges, shapeCoords)
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


