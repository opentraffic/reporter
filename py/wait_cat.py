#!/usr/bin/env python
import sys
import os
import time
import argparse


#generator for streaming a file
def stream(handle, size=4096):
  while True:
    chunk = handle.read(size)
    if not chunk:
      break
    yield chunk


#allow a file separator so stuff downstream can know
parser = argparse.ArgumentParser(description='Like cat but will wait for files to exist', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('files', metavar='F', type=str, nargs='+', help='A file name to be sent to stdout')
parser.add_argument('--file-separator', type=str, help='A string to write to at the end of each file', default='')
parser.add_argument('--delete', action='store_true', help='Delete a file after cat\'ing its contents')
args = parser.parse_args()

#we are writing to stdout
wait_files = args.files
#until there is nothing left to wait for
while True:
  #remember how many we had
  wait_count = len(wait_files)
  #for each file check if we have it
  for wait_file in wait_files:
    if os.path.isfile(wait_file):
      #we have it so stream it on
      with open(wait_file, 'rb') as handle:
        for chunk in stream(handle):
          sys.stdout.write(chunk)
          sys.stdout.flush()
      #write the file separator
      sys.stdout.write(args.file_separator)
      sys.stdout.flush()
      #done with this one
      wait_files.remove(wait_file)
      if args.delete:
        os.remove(wait_file)
      break
  #we're done
  if len(wait_files) == 0:
    break
  #seems like nothing was there yet so wait around a bit
  if len(wait_files) == wait_count:
    time.sleep(10)
