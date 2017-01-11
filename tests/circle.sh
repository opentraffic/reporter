#!/usr/bin/env bash
set -e

# download test data
echo "Downloading test data..."
aws s3 cp --recursive s3://circleci_reporter data

# start the container
echo "Starting the docker container..."
docker run \
  -d \
  -p 8002:8002 \
  --name reporter \
  -v ${PWD}/data:/data/valhalla \
  opentraffic/reporter

sleep 5

# generate some test json data with the csv formatter,
#   drop it in the bind mount so we can access it from
#   outside the container in the next test.
echo "Generating reporter request data with the csv formatter..."
sudo lxc-attach \
  -n "$(docker inspect --format "{{.Id}}" reporter)" -- \
  bash -c "/reporter/csv_formatter.py /data/valhalla/grab.csv > /data/valhalla/reporter_requests.json"

# test the generated data against the service
echo "Running a subset of the test data through the matcher service..."
cat ${PWD}/data/reporter_requests.json | \
  head -50 | \
  parallel \
    -j2 \
    --halt 2 \
    --progress \
    curl -s --data '{}' localhost:8002/segment_match?

echo "Done!"
