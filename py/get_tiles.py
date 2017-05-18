#!/usr/bin/env python
#Author: Greg Knisely
#TileHierarchy and Tiles logic based on 
#https://github.com/valhalla/valhalla/blob/master/src/baldr/tilehierarchy.cc and
#https://github.com/valhalla/valhalla/blob/master/src/baldr/graphtile.cc

import sys
import math
import getopt
from distutils.util import strtobool

#world bb
minx_ = -180
miny_ = -90
maxx_ = 180
maxy_ = 90

#more global vars
boundingbox = None
url = None
output_dir = None
tile_ids = {}

class BoundingBox(object):

  def __init__(self, min_x, min_y, max_x, max_y):
     self.minx = min_x
     self.miny = min_y
     self.maxx = max_x
     self.maxy = max_y

  #The bounding boxes do NOT intersect if the other bounding box is
  #entirely LEFT, BELOW, RIGHT, or ABOVE bounding box.
  def Intersects(self, bbox):
    if ((bbox.minx < self.minx and bbox.maxx < self.minx) or
        (bbox.miny < self.miny and bbox.maxy < self.miny) or
        (bbox.minx > self.maxx and bbox.maxx > self.maxx) or
        (bbox.miny > self.maxy and bbox.maxy > self.maxy)):
      return False
    return True

class TileHierarchy(object):

  def __init__(self):
    self.levels = {}
    # local
    self.levels[2] = Tiles(BoundingBox(minx_,miny_,maxx_,maxy_),.25)
    # arterial
    self.levels[1] = Tiles(BoundingBox(minx_,miny_,maxx_,maxy_),1)
    # highway
    self.levels[0] = Tiles(BoundingBox(minx_,miny_,maxx_,maxy_),4)

class Tiles(object):

  def __init__(self, bbox, size):
     self.bbox = bbox
     self.tilesize = size

     self.ncolumns = int(math.ceil((self.bbox.maxx - self.bbox.minx) / self.tilesize))
     self.nrows = int(math.ceil((self.bbox.maxy - self.bbox.miny) / self.tilesize))
     self.max_tile_id = ((self.ncolumns * self.nrows) - 1)

  def TileCount(self):
    return self.ncolumns * self.nrows

  def Row(self, y):
    #Return -1 if outside the tile system bounds
    if (y < self.bbox.miny or y > self.bbox.maxy):
      return -1

    #If equal to the max y return the largest row
    if (y == self.bbox.maxy):
      return nrows - 1
    else:
      return int((y - self.bbox.miny) / self.tilesize)

  def Col(self, x):
    #Return -1 if outside the tile system bounds
    if (x < self.bbox.minx or x > self.bbox.maxx):
      return -1

    #If equal to the max x return the largest column
    if (x == self.bbox.maxx):
      return self.ncolumns - 1
    else:
      col = (x - self.bbox.minx) / self.tilesize
      return int(col) if (col >= 0.0) else int(col - 1)

  def Digits(self, number):
    digits = 1 if (number < 0) else 0
    while long(number):
       number /= 10
       digits += 1
    return long(digits)
   
  def TileExists(self, row, col, level, directory):

    #get the tile id
    tile_id = (row * self.ncolumns) + col

    max_length = self.Digits(self.max_tile_id)

    remainder = max_length % 3
    if remainder:
      max_length += 3 - remainder

    #if it starts with a zero the pow trick doesn't work
    if level == 0:
       file_suffix = '{:,}'.format(int(pow(10, max_length)) + tile_id).replace(',', '/')
       file_suffix += ".gph"
       file_suffix = "0" + file_suffix[1:]
       file = directory + '/' + file_suffix

       if (os.path.isfile(file)):
         return tile_id
       return None

    #it was something else
    file_suffix = '{:,}'.format(level * int(pow(10, max_length)) + tile_id).replace(',', '/')
    file_suffix += ".gph"
    file = directory + '/' + file_suffix

    if (os.path.isfile(file)):
      return tile_id
    return None

  # get the file name based on tile_id and level
  def GetFilename(self, tile_id, level, directory):

    max_length = self.Digits(self.max_tile_id)

    remainder = max_length % 3
    if remainder:
       max_length += 3 - remainder

    #if it starts with a zero the pow trick doesn't work
    if level == 0:
      file_suffix = '{:,}'.format(int(pow(10, max_length)) + tile_id).replace(',', '/')
      file_suffix += ".gph"
      file_suffix = "0" + file_suffix[1:]
      file = directory + '/' + file_suffix

      if (os.path.isfile(file)):
        return file
      return None

    #it was something else
    file_suffix = '{:,}'.format(level * int(pow(10, max_length)) + tile_id).replace(',', '/')
    file_suffix += ".gph"
    file = directory + '/' + file_suffix

    if (os.path.isfile(file)):
      return file
    return None

  # get the File based on tile_id and level
  def GetFile(self, tile_id, level):

    max_length = self.Digits(self.max_tile_id)

    remainder = max_length % 3
    if remainder:
       max_length += 3 - remainder

    #if it starts with a zero the pow trick doesn't work
    if level == 0:
      file_suffix = '{:,}'.format(int(pow(10, max_length)) + tile_id).replace(',', '/')
      file_suffix += ".gph"
      file_suffix = "0" + file_suffix[1:]
      file = '/' + file_suffix
      return file


    #it was something else
    file_suffix = '{:,}'.format(level * int(pow(10, max_length)) + tile_id).replace(',', '/')
    file_suffix += ".gph"
    file = '/' + file_suffix

    return file

  def TileId(self, y, x):
    if (y < self.bbox.miny or x < self.bbox.minx or
        y > self.bbox.maxy or x > self.bbox.maxx):
      return -1

    #Find the tileid by finding the latitude row and longitude column
    return (self.Row(y) * self.ncolumns) + self.Col(x)

  # Get the bounding box of the specified tile.
  def TileBounds(self, tileid):
    row = tileid / self.ncolumns
    col = tileid - (row * self.ncolumns)

    x = self.bbox.minx + (col * self.tilesize)
    y = self.bbox.miny + (row * self.tilesize)
    return BoundingBox(x, y, x + self.tilesize, y + self.tilesize)

  # Get the neighboring tileid to the right/east.
  def RightNeighbor(self, tileid):
    row = tileid / self.ncolumns
    col = tileid - (row * self.ncolumns)

    return (tileid + 1) if (col < self.ncolumns - 1) else (tileid - self.ncolumns + 1)

  # Get the neighboring tileid to the left/west.
  def LeftNeighbor(self, tileid):
    row = tileid / self.ncolumns
    col = tileid - (row * self.ncolumns)
    return (tileid - 1) if (col > 0) else (tileid + self.ncolumns - 1)

  # Get the neighboring tileid above or north.
  def TopNeighbor(self, tileid):
    return (tileid + self.ncolumns) if (tileid < int(self.TileCount() - self.ncolumns)) else tileid

  # Get the neighboring tileid below or south.
  def BottomNeighbor(self, tileid):
    return tileid if (tileid < self.ncolumns) else (tileid - self.ncolumns)

  # Get the list of tiles that lie within the specified bounding box.
  # The method finds the center tile and spirals out by finding neighbors
  # and recursively checking if tile is inside and checking/adding
  # neighboring tiles
  def TileList(self, bbox, ids):
    # Get tile at the center of the bounding box. Return -1 if the center
    # of the bounding box is not within the tiling system bounding box.

    tilelist = []
    # Get the center of the BB to get the tile id
    tileid = self.TileId(((bbox.miny + bbox.maxy) * 0.5), ((bbox.minx + bbox.maxx) * 0.5))

    if (tileid == -1):
      return tilelist

    # List of tiles to check if in view. Use a list: push new entries on the
    # back and pop off the front. The tile search tends to spiral out from
    # the center.
    checklist = []

    # Visited tiles
    visited_tiles = set()

    # Set this tile in the checklist and it to the list of visited tiles.
    checklist.append(tileid)
    visited_tiles.add(tileid)

    # Get neighboring tiles in bounding box until NextTile returns -1
    # or the maximum number specified is reached
    while (len(checklist) != 0):
      #Get the element off the front of the list and add it to the tile list.
      tileid = checklist.pop(0)
      # only add tile ids that have been found in the list of ids
      if tileid in ids:
        tilelist.append(tileid)

      # Check neighbors
      neighbor = self.LeftNeighbor(tileid)
      if (neighbor not in visited_tiles and
          bbox.Intersects(self.TileBounds(neighbor))):
        checklist.append(neighbor)
        visited_tiles.add(neighbor)

      neighbor = self.RightNeighbor(tileid)
      if (neighbor not in visited_tiles and
          bbox.Intersects(self.TileBounds(neighbor))):
        checklist.append(neighbor)
        visited_tiles.add(neighbor)

      neighbor = self.TopNeighbor(tileid)
      if (neighbor not in visited_tiles and
          bbox.Intersects(self.TileBounds(neighbor))):
        checklist.append(neighbor)
        visited_tiles.add(neighbor)

      neighbor = self.BottomNeighbor(tileid)
      if (neighbor not in visited_tiles and
          bbox.Intersects(self.TileBounds(neighbor))):
        checklist.append(neighbor)
        visited_tiles.add(neighbor)

    return tilelist

def check_args(argv):

   global url, output_dir, boundingbox
   try:
      opts, args = getopt.getopt(sys.argv[1:], "h:b:u:d:", ["help=", "bbox=", "url=", "output_dir="])
   except getopt.GetoptError:
      print('tiles.py -b lower_left_lng_lat, upper_right_lng_lat -u https://thewebsite.com/dir -d /data/tiles')
      print('tiles.py -b -74.251961,40.512764,-73.755405,40.903125 -u https://thewebsite.com/dir -d /data/tiles')
      sys.exit(2)
   for opt, arg in opts:
      if opt in ("-h", "--help"):
         print('tiles.py -b lower_left_lng_lat, upper_right_lng_lat -u https://thewebsite.com/dir -d /data/tiles')
         print('tiles.py -b -74.251961,40.512764,-73.755405,40.903125 -u https://thewebsite.com/dir -d /data/tiles')
         sys.exit()
      elif opt in ("-b", "--bbox"):
         boundingbox = arg
      elif opt in ("-u", "--url"):
         url = arg
      elif opt in ("-d", "--output_dir"):
         output_dir = arg

   if (boundingbox == None or output_dir == None or url == None):
      print('tiles.py -b lower_left_lng_lat, upper_right_lng_lat -u https://thewebsite.com/dir -d /data/tiles')
      print('tiles.py -b -74.251961,40.512764,-73.755405,40.903125 -u https://thewebsite.com/dir -d /data/tiles')
      sys.exit()

#this is the entry point to the program
if __name__ == "__main__":
   
  check_args(sys.argv[1:])

  # these are the tiles that should exist in s3
  tile_hierarchy = TileHierarchy()
  for level, tiles in tile_hierarchy.levels.items():
    tile_ids[level] = set()
    for row in xrange(0, tiles.nrows):
      for col in xrange(0, tiles.ncolumns):
        tile_id = (row * tiles.ncolumns) + col
        tile_ids[level].add(tile_id)

  if boundingbox:
    bbox = [ float(i) for i in boundingbox.split(',')]

    bounding_boxes = []
    #check our bb and make sure it does not cross 180/-180, if it does
    #split it into two bounding boxes.
    # example 174.223,-37.348,-175.314,-36.4099999 will change to
    # 174.223,-37.348,180.0,-36.4099999 and
    # -180.0,-37.348,-175.314,-36.4099999
    if (bbox[0] >= bbox[2]) and (bbox[2] >= -180.0):
      bounding_boxes.append(BoundingBox(bbox[0], bbox[1], 180.0, bbox[3]))
      bounding_boxes.append(BoundingBox(-180.0, bbox[1], bbox[2], bbox[3]))
    else:
      bounding_boxes.append(BoundingBox(bbox[0], bbox[1], bbox[2], bbox[3]))

    while (len(bounding_boxes) != 0):
      b_box = bounding_boxes.pop(0)

      for level, t_ids in tile_ids.items():
        # only get the tiles that intersect the bounding box
        tiles = tile_hierarchy.levels[level].TileList(b_box,t_ids)
        for t in tiles:
          file_name = tile_hierarchy.levels[level].GetFile(t, level)
          print(url + file_name)
          print("--create-dirs")
          print("-o")
          print(output_dir + file_name)

