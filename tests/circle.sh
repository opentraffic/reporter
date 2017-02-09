#!/usr/bin/env bash
set -e

reporter_port=8002

# download test data
echo "Downloading test data..."
aws s3 cp --recursive s3://circleci_reporter data

# start the container
echo "Starting the redis container..."
docker run \
  -d \
  --name reporter-redis \
  redis:3.2.6

echo "Starting the reporter container..."
docker run \
  -d \
  -p ${reporter_port}:${reporter_port} \
  --name reporter \
  --link reporter-redis:redis \
  -v ${PWD}/data:/data/valhalla \
  $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/opentraffic/reporter:$CIRCLE_SHA1

sleep 5

# generate some test json data with the csv formatter,
#   drop it in the bind mount so we can access it from
#   outside the container in the next test.
echo "Generating reporter request data with the csv formatter..."
sudo lxc-attach \
  -n "$(docker inspect --format "{{.Id}}" reporter)" -- \
  bash -c "/reporter/csv_formatter.py /data/valhalla/grab.csv >/data/valhalla/reporter_requests.json"

# basic json validation
echo "Validating csv formatter output is valid json..."
jq "." ${PWD}/data/reporter_requests.json >/dev/null

# test the generated data against the service
echo "Running a subset of the test data through the matcher service..."
cat ${PWD}/data/reporter_requests.json | \
  head -50 | \
  parallel \
    -j2 \
    --halt 2 \
    --progress \
    curl --fail -s --data '{}' localhost:${reporter_port}/segment_match?

echo "Done!"
