#!/bin/bash

# example: load february: run this via
#   nohup ./run.sh >logs/run.out 2>&1 &
for i in {01..31}; do
  ./load_data.sh $i 03 2017
done
