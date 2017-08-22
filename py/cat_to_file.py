#!/usr/bin/env python
import sys
import os
import argparse
import logging
import json
import re

#parse a couple of options
parser = argparse.ArgumentParser(description='Generate reporter post body', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('file', metavar='F', type=str, nargs=1, help='A file name to be read from, use - for stdin')
parser.add_argument('--key-with', type=str, help='A lambda of the form "lambda line: line.do_something()" such that the program can extract a key from a given line of input')

args = parser.parse_args()
args.file = args.file[0]

#Manila Extract BBox
bb_ymin = 14.501
bb_xmin = 120.9
bb_ymax = 14.70
bb_xmax = 121.13

exec('key_with = ' + (args.key_with if args.key_with else 'None'))

#output a single body
#for each line from stdin
handle = open(args.file, 'r') if args.file != '-' else sys.stdin
out_file=[]
for line in handle:
  #try to work on the line as normal
  try:
    l = line.rstrip()
    pieces = l.split('|')
    lat=float(pieces[9])
    lon=float(pieces[10])
    if lat >= bb_ymin and lat <= bb_ymax and lon >= bb_xmin and lon <= bb_xmax:
      key = bytes(key_with(l)) if key_with else None
      value = bytes(l.rstrip())
      out_file.append(value+"/n")

  except Exception as e:
    sys.stderr.write(repr(e))
    sys.stderr.write(os.linesep)
    
print(str(len(out_file)))    
  
#done
if args.file != '-':
  handle.close()
  
with open('2017-01-02', "ab") as f:
  f.write(str(out_file))   
