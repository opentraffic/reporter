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
#echo "Starting the datastore..."

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
  -e "TODO_DATASTORE_URL=http://localhost:${datastore_port}/store?" \
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
  wurstmeister/zookeeper:3.4.6

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
  -e "KAFKA_CREATE_TOPICS=raw:4:1,formatted:4:1,batched:4:1" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --name kafka \
  wurstmeister/kafka:0.10.2.1

# wait for the topics to be created
#
sleep 30

# start kafka worker
#
echo "Starting kafka reporter..."
mkdir ${PWD}/results
docker run \
  -d \
  --net opentraffic \
  --name reporter-kafka \
  -v ${PWD}/results:/results \
  reporter:latest \
  /usr/local/bin/reporter-kafka -b ${docker_ip}:${kafka_port} -t raw,formatted,batched -f ',sv,\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss' -u http://reporter-py:${reporter_port}/report? -p 1 -q 3600 -i 15 -s TEST -o /results 

# inject the data into kafka
#
sleep 10 #wait for the kafka worker to connect
echo "Producing data to kafka" 
py/cat_to_kafka.py --bootstrap localhost:9092 --topic raw --key-with 'lambda line: line.split("|")[1]' valhalla_data/*.sv

# done running stuff
#
echo "Sleeping 5 minutes to allow data to be processed..."
for i in $(seq 1 300); do
  echo -e "$i \c"
  sleep 1
done
docker kill $(docker ps -q)
  
# test that we got data written out
#
echo "Checking results..."
reporter=$(docker ps -a | grep -F "reporter-kafka" | awk '{print $1}')
tile_count=$(docker logs ${reporter} 2>&1 | grep -cF "Writing tile to")
if [[ ${tile_count} == 0 ]]; then
  echo "No tiles written"
  exit 1
fi
if [[ ${tile_count} != $(find ${PWD}/results -type f | wc -l) ]]; then
  echo "Wrong number of tiles written"
  exit 1
fi
for tile in $(docker logs ${reporter} 2>&1 | grep -F "Writing tile to" | sed -e "s/.*tile to //g"); do
  if [[ ! -e "${PWD}/${tile}" ]]; then
    echo "Couldn't find ${PWD}/${tile}"
    exit 1
  fi
done
echo "Done!"
