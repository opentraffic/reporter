#!/usr/bin/env python
import sys
import os
import argparse
import logging
import json
import re
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
parser.add_argument('--key-with', type=str, help='A lambda of the form "lambda line: line.do_something()" such that the program can extract a key from a given line of input')
parser.add_argument('--value-with', type=str, help='A lambda of the form "lambda line: line.do_something()" such that the program can modify the value in some way before producing')

args = parser.parse_args()
args.file = args.file[0]

producer = KafkaProducer(bootstrap_servers = args.bootstrap.split(','),api_version=(0, 10))
exec('key_with = ' + (args.key_with if args.key_with else 'None'))
exec('value_with = ' + (args.value_with if args.value_with else 'None'))

#output a single body
#for each line from stdin
handle = open(args.file, 'r') if args.file != '-' else sys.stdin
for line in handle:
  #try to work on the line as normal
  try:
   l = line.rstrip()
   key = bytes(key_with(l)) if key_with else None
   value = bytes(value_with(l) if value_with else l)
   producer.send(args.topic, key = key, value = value)
  except Exception as e:
    sys.stderr.write(repr(e))
    sys.stderr.write(os.linesep)
#done
if args.file != '-':
  producer.close()
  handle.close()
