#!/bin/bash

#setup the dir where the container will find valhalla tiles (tiles.tar)
valhalla_data_dir=/data/valhalla

#pick parallelism
partitions=7

#kill all docker containers
docker rm -f $(docker ps -qa)
docker rmi -f $(docker images -q)

#start zookeeper
docker run -d --net opentraffic -p 2181:2181 --name zookeeper wurstmeister/zookeeper:latest

#start kafka brokers
docker run -d --net opentraffic -p 9092:9092 -e "KAFKA_ADVERTISED_HOST_NAME=172.17.0.1" -e "KAFKA_ADVERTISED_PORT=9092" -e "KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181" -e "KAFKA_CREATE_TOPICS=raw:7:1,formatted:7:1,batched:7:1" -v /var/run/docker.sock:/var/run/docker.sock --name kafka wurstmeister/kafka:latest

#wait for topics to be created
sleep 15

for i in {0..6}; do
  target/reporter-kafka -b localhost:9092 -t raw,formatted,batched  -f ',sv,\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss' -u http://localhost:8002/report? -p 2 -q 3600 -i 3600 -s DEBUG -o /data/opentraffic/reporter/results &> ${i}.log &
done

#start some traffic segment matchers
#docker run -d --net opentraffic -p 8002 --name reporter-py -e "THREAD_POOL_COUNT=${partitions}" -v ${valhalla_data_dir}:/data/valhalla opentraffic/reporter:latest
THREAD_POOL_COUNT=7 PYTHONPATH=../../valhalla/valhalla/.libs/ py/reporter_service.py ../../conf/valhalla.json localhost:8002

#now load in data with something like this
echo 'cd py'
echo './make_day_requests.sh -f 2017-01-01.gz -b localhost:9092 -t raw'                                             '

