#!/usr/bin/env bash
set -e

# env
#
echo "Sourcing env from ./tests/env.sh..."
. ./tests/env.sh

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

# so we dont need to link containers
#
if [ $(docker network ls --filter name=opentraffic -q | wc -l) -eq 0 ]; then
  echo "Creating opentraffic bridge network..."
  docker network create --driver bridge opentraffic
fi

# start the python segment matcher
#
echo "Starting the python reporter container..."
docker run \
  -d \
  --net opentraffic \
  -p ${reporter_port}:${reporter_port} \
  -e "DATASTORE_URL=http://datastore:${datastore_port}/store?" \
  --name reporter-py \
  -v ${PWD}/${valhalla_data_dir}:/data/valhalla \
  reporter:latest

# start zookeeper
#
echo "Starting zookeeper..."
docker run \
  -d \
  --net opentraffic \
  -p ${zookeeper_port}:${zookeeper_port} \
  --name zookeeper \
  wurstmeister/zookeeper:latest

# start kafka
#
echo "Starting kafka..."
docker run \
  -d \
  --net opentraffic \
  -p ${kafka_port}:${kafka_port} \
  -e "KAFKA_ADVERTISED_HOST_NAME=${docker_ip}" \
  -e "KAFKA_ADVERTISED_PORT=${kafka_port}" \
  -e "KAFKA_ZOOKEEPER_CONNECT=zookeeper:${zookeeper_port}" \
  -e "KAFKA_CREATE_TOPICS=raw:1:1,formatted:1:1,batched:4:1" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --name kafka \
  wurstmeister/kafka:latest

# wait for the topics to be created
#
sleep 30

# start kafka job
#
echo "Starting kafka reporter..."
docker run \
  -d \
  --net opentraffic \
  --name reporter-kafka \
  reporter:latest \
  /usr/local/bin/reporter-kafka -b ${docker_ip}:${kafka_port} -r raw -i formatted -l batched -u http://reporter-py:8002/report? -v
  
sleep 3


#pump the data into kafka
py/cat_to_kafka.py --bootstrap localhost:9092 --topic raw valhalla_data/*.csv

# test that we got data through to the echo server
# TODO: this is lame do something more meaningful
#
posts=$(awk '{print $4}' datastore.log | grep -Fc POST)
if [[ ${oks} == 0 ]] || [[ ${posts} != ${oks} ]]; then
  exit 1
fi

sleep 3
kill ${echo_pid}
echo "Done!"
