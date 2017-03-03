#!/usr/bin/env bash

# test the generated data against the live service
# 	after the deployment has completed.
#

# env
#
echo "Sourcing env from ./tests/env.sh..."
. ./tests/env.sh

if [ -z "$1" ]; then
  echo "Usage: $0 [reporter_url]"
  echo "Example: $0 \"http://reporter-dev.opentraffic.io/report?\""
	exit 1
else
	URL=$1
fi

echo "Running test data through $URL..."
cat ${PWD}/${valhalla_data_dir}/reporter_requests.json | \
  parallel \
    -j4 \
    --halt 2 \
    --progress \
    curl \
      --fail \
      --silent \
      --max-time 3 \
      --retry 3 \
      --retry-delay 3 \
      --data '{}' $URL
