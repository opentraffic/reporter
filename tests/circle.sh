#!/usr/bin/env bash
set -e

# env
#
echo "Sourcing env from ./tests/env.sh..."
. ./tests/env.sh

# build flink job
#
export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-amd64
mvn install 2>&1 1>/dev/null
mvn clean package
flink_job=${PWD}/target/accumulator-1.0-SNAPSHOT.jar

# download test data
#
echo "Downloading test data..."
aws s3 cp --recursive s3://circleci_reporter valhalla_data

# for now we have an echo server in place of the real data store
# TODO: start the real data store container
#
echo "Starting the datastore..."
prime_echod tcp://*:${datastore_port} 1 &> datastore.log &
echo_pid=$!

# start the python segment matcher
#
echo "Starting the reporter container..."
docker run \
  -d \
  -p ${reporter_port}:${reporter_port} \
  -e "DATASTORE_URL=http://datastore:${datastore_port}/store?" \
  --name reporter \
  -v ${PWD}/${valhalla_data_dir}:/data/valhalla \
  reporter:latest

# start the flink job manager container
#
echo "Starting the flink job manager..."
docker run \
  -d \
  -p ${flink_port}:${flink_port} \
  --name jobmanager \
  -v $(dirname ${flink_job}):/jobs \
  -t flink local
  
sleep 3

# submit the flink job to the flink job manager
# for now we'll use file mode, later we'll switch to consume from kafka
#
echo "Running flink job from file..."
JOBMANAGER_CONTAINER=$(docker ps --filter name=jobmanager --format={{.ID}})
docker exec -t \
  -i "$JOBMANAGER_CONTAINER" \
  flink run \
  -c opentraffic.accumulator.Accumulator /jobs/$(basename ${flink_job}).jar \
  --file valhalla_data/*.csv \
  --reporter http://reporter:${reporter_port}/report?

# test that we got data through to the echo server
# TODO: this is lame do something more meaningful
#
posts=$(awk '{print $4}' datastore.log | grep -Fc POST)
oks=$(awk '{print $4}' datastore.log | grep -Fc 200)
if [[ ${oks} == 0 ]] || [[ ${posts} != ${oks} ]]; then
  exit 1
fi

echo "Done!"
