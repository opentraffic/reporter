#!/usr/bin/env python
import sys
import traceback
import os
import argparse
import logging
import json
import re
from functools import partial
from kafka import KafkaProducer
from kafka.common import KafkaError

logger = logging.getLogger('kafka.client')
logger.setLevel(logging.DEBUG)
h = logging.StreamHandler()
h.setLevel(logging.DEBUG)
logger.addHandler(h)

log = logging.getLogger('cat_producer')
log.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(fmt='%(asctime)s %(levelname)s %(message)s'))
log.addHandler(handler)

#parse a couple of options
parser = argparse.ArgumentParser(description='Generate reporter post body', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('file', metavar='F', type=str, nargs=1, help='A file name to be read from, use - for stdin')
parser.add_argument('--bootstrap', type=str, help='A list of ip(s) and port(s) for your kafka bootstrap servers', required=True)
parser.add_argument('--topic', type=str, help='Create a topic for which the messages should be associated', required=True)
parser.add_argument('--key-with', type=str, help='A lambda of the form "lambda line: line.do_something()" such that the program can extract a key from a given line of input', required=False)
parser.add_argument('--value-with', type=str, help='A lambda of the form "lambda line: line.do_something()" such that the program can modify the value in some way before producing', required=False)
parser.add_argument('--send-if', type=str, help='A lambda of the from "lambda line: line.do_something()" such that the program can know if it should send the line or not', required=False)

args = parser.parse_args()
args.file = args.file[0]

producer = KafkaProducer(bootstrap_servers = args.bootstrap.split(','),api_version=(0, 10))
exec('key_with = ' + (args.key_with if args.key_with else 'None'))
exec('value_with = ' + (args.value_with if args.value_with else 'None'))
exec('send_if = ' + (args.send_if if args.send_if else 'None'))

#output a single body
#for each line from stdin
handle = open(args.file, 'r') if args.file != '-' else sys.stdin
lines = 0
total = 0
shown = False
for line in handle:
  #try to work on the line as normal
  try:
    l = line.rstrip()   
    if send_if is None or send_if(line):
      key = bytes(key_with(l)) if key_with else None
      value = bytes(value_with(l) if value_with else l)
      producer.send(args.topic, key = key, value = value)
      lines += 1
      shown = False
    total += 1
    if not shown and lines % 10000 == 0:
      shown = True
      log.info('Sent ' + str(lines) + ' messages of ' + str(total) + ' total messages')
  except Exception as e:
    sys.stderr.write('With arguments: ' + str(args) + os.linesep)
    sys.stderr.write('With line: ' + l + os.linesep)
    traceback.print_exc(file=sys.stderr)

log.info('Finished sending ' + str(lines) + ' messages of ' + str(total) + ' total messages')

#done
if args.file != '-':
  producer.close()
  handle.close()
