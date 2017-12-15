#!/bin/bash
# NOTE: concurrency set to 12 for r3.4xlarge

if [ -z $3 ]; then
  echo "Usage: go.sh [day] [month] [year]"
else
  day=$1
  month=$2
  year=$3

  ./simple_reporter.py --src-bucket grab_historical_data --src-prefix ${year}_${month}/ --src-key-regex ".*${year}_${month}_${day}_.*gz" --dest-bucket reporter-drop-prod --match-config conf.json --report-levels 0,1,2 --transition-levels 0,1,2 --concurrency 16 >logs/${day}_${month}_${year}.out 2>&1
fi

