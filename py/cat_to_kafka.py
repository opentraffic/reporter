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

#""" For debugging
logger = logging.getLogger('kafka.client')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
h = logging.StreamHandler()
h.setLevel(logging.DEBUG)
logger.addHandler(h)
#"""

#parse a couple of options
parser = argparse.ArgumentParser(description='Generate reporter post body', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('file', metavar='F', type=str, nargs=1, help='A file name to be read from, use - for stdin')
parser.add_argument('--bootstrap', type=str, help='A list of ip(s) and port(s) for your kafka bootstrap servers')
parser.add_argument('--topic', type=str, help='Create a topic for which the messages should be associated')

args = parser.parse_args()
args.file = args.file[0]

producer = KafkaProducer(bootstrap_servers = args.bootstrap.split(','),api_version=(0, 10))

#output a single body
#for each line from stdin
handle = open(args.file, 'r') if args.file != '-' else sys.stdin
for line in handle:
  #try to work on the line as normal
  try:
   producer.send(args.topic, line.rstrip())
  #we couldnt parse this line so lets output what we have so far
  except:
    pass
#done
if args.file != '-':
  producer.close()
  handle.close()
