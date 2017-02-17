#!/usr/bin/env bash
set -e

reporter_port=8002
datastore_port=8003

# download test data
echo "Downloading test data..."
aws s3 cp --recursive s3://circleci_reporter data

# start the containers
echo "Starting the postgres container..."
docker run \
  -d \
  --name datastore-postgres \
  -e 'POSTGRES_USER=opentraffic' \
  -e 'POSTGRES_PASSWORD=changeme' \
  -e 'POSTGRES_DB=opentraffic' \
  postgres:9.6.1

echo "Sleeping to allow creation of database..."
sleep 5

echo "Starting the datastore container..."
docker run \
  -d \
  -p ${datastore_port}:${datastore_port} \
  -v ${PWD}/data:/data \
  --name datastore \
  --link datastore-postgres:postgres \
  opentraffic/datastore:latest

echo "Starting the redis container..."
docker run \
  -d \
  --name reporter-redis \
  redis:3.2.6

echo "Starting the reporter container..."
docker run \
  -d \
  -p ${reporter_port}:${reporter_port} \
  -e "REDIS_HOST=redis" \
  -e "DATASTORE_URL=http://datastore:${datastore_port}/store?" \
  --name reporter \
  --link reporter-redis:redis \
  --link datastore:datastore \
  -v ${PWD}/data:/data/valhalla \
  reporter:latest

sleep 3

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
    curl --max-time 3 --fail -s --data '{}' localhost:${reporter_port}/segment_match?

echo "Done!"
