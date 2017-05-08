#!/usr/bin/env python
import sys
import os
import time
import calendar
import argparse
import json
import logging, time
from kafka import KafkaProducer
from kafka.common import KafkaError
 
logger = logging.getLogger('kafka.client')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('push_data.log')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)

producer = KafkaProducer(bootstrap_servers=['172.17.0.1:9092'],api_version=(0, 9))

#parse a couple of options
parser = argparse.ArgumentParser(description='Generate reporter post body', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('file', metavar='F', type=str, nargs=1, help='A file name to be read from, use - for stdin')

args = parser.parse_args()
args.file = args.file[0]

#output a single body
#for each line from stdin
handle = open(args.file, 'r') if args.file != '-' else sys.stdin
for line in handle:
  #try to work on the line as normal
  try:
   producer.send("tracepts", line)
  #we couldnt parse this line so lets output what we have so far
  except:
    pass
#done
if args.file != '-':
  producer.close()
  handle.close()
