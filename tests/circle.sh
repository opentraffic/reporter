#!/usr/bin/env bash
set -e

# env
#
reporter_port=8002
datastore_port=8003

postgres_user="opentraffic"
postgres_password="changeme"
postgres_db="opentraffic"

valhalla_data_dir="valhalla_data"

# download test data
#
echo "Downloading test data..."
aws s3 cp --recursive s3://circleci_reporter valhalla_data

# start the containers
#
echo "Starting the postgres container..."
docker run \
  -d \
  --name datastore-postgres \
  -e "POSTGRES_USER=${postgres_user}" \
  -e "POSTGRES_PASSWORD=${postgres_password}" \
  -e "POSTGRES_DB=${postgres_db}" \
  postgres:9.6.1

echo "Sleeping to allow creation of database..."
sleep 5

echo "Starting the datastore container..."
docker run \
  -d \
  -p ${datastore_port}:${datastore_port} \
  -e "POSTGRES_USER=${postgres_user}" \
  -e "POSTGRES_PASSWORD=${postgres_password}" \
  -e "POSTGRES_DB=${postgres_db}" \
  -e 'POSTGRES_HOST=postgres' \
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
  -v ${PWD}/${valhalla_data_dir}:/data/valhalla \
  reporter:latest

sleep 3

# generate some test json data with the csv formatter,
#   drop it in the bind mount so we can access it from
#   outside the container in the next test.
#
echo "Generating reporter request data with the csv formatter..."
sudo lxc-attach \
  -n "$(docker inspect --format "{{.Id}}" reporter)" -- \
  bash -c "/reporter/csv_formatter.py /data/valhalla/grab.csv >/data/valhalla/reporter_requests.json"

# basic json validation
#
echo "Validating csv formatter output is valid json..."
jq "." ${PWD}/${valhalla_data_dir}/reporter_requests.json >/dev/null

# test the generated data against the service
#
echo "Running test data through the matcher service..."
cat ${PWD}/${valhalla_data_dir}/reporter_requests.json | \
  parallel \
    -j2 \
    --halt 2 \
    --progress \
    curl \
      --fail \
      --silent \
      --max-time 3 \
      --retry 3 \
      --retry-delay 3 \
      --data '{}' localhost:${reporter_port}/segment_match?

echo "Done!"
