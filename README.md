# Open Traffic Reporter

Open Traffic Reporter is part of OTv2, the new Open Traffic platform under development. It will take the place of OTv1's [Traffic Engine](https://github.com/opentraffic/traffic-engine) component.

Reporter takes in raw GPS probe data, matches it to [OSMLR segments](https://github.com/opentraffic/osmlr/blob/master/docs/intro.md) using [Valhalla](https://github.com/valhalla/valhalla/blob/master/docs/meili.md), and sends segments and speeds to the centralized [Open Traffic Datastore](https://github.com/opentraffic/datastore).

## How to run the Reporter...let us count the ways...

### Method 1: data from file/stdin

To build/run the [reporter service](https://github.com/opentraffic/reporter) via docker-compose:

```bash
#get some osmlr enabled routing tiles for your region
TODO: @gknisely show how to get a bbox and make a tar
#move your tar to some place
mv tiles.tar /some/path/to/tiles.tar
#before we start the reporter you'll need the format of your incoming messages
#we specify what formatter we want and its properties with a simple string
#the first char is the separator to use when parsing the args out of the string
#the first argument is the type of formatter, right now separated value or json
#  for separated value if your messages looked like: `2017-01-31 16:00:00|uuid_abcdef|x|x|x|accuracy|x|x|x|lat|lon|x|x|x`
#  your formatter string will be: `,sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss`
#  the arguments to the sv type formatter are: separator regex, uuid column, lat column, lon column, time column, accuracy column and (optional) date format string
#  for json if your messages looked like: `{"timestamp":1495037969,"id":"uuid_abcdef","accuracy":51.305,"latitude":3.465725,"longitude":-76.5135033}`
#  your formatter string will be: `@json@id@latitude@longitude@timestamp@accuracy`
#  the arguments to the json type formatter are: uuid key, lat key, lon key, time key, accuracy and (optional) date format string
#  note the last argument of both is a date string format, if your data is already an epoch timestamp you dont need to provide it
#TODO: fix the docker-compose.yml to actually supply DATASTORE_URL
#start up all the containers
FORMATTER='sv,\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss' DATAPATH=/some/path/to/data docker-compose up
#shovel messages into kafka from your local data source
py/cat_to_kafka.py --topic raw --bootstrap localhost:9092 YOUR_FLAT_FILE
#tail some docker logs
reporterpy=$(docker ps -a | grep -F reporter-py | awk '{print $1}')
docker logs --follow ${reporterpy}
```

### Method 2: data from existing kafka

If you already have a kafka stream setup then you'll only need to point the reporter at its outgoing topic with your messages on it. To do this you'll only need to run two of the pieces of software. The python reporter service and the kafka reporter stream processing application. These can either be run directly (especially in the case of debugging) or as docker containers. We'll go over both.


#### Just the reporter docker containers

```bash
#get some osmlr enabled routing tiles for your region
TODO: @gknisely show how to get a bbox and make a tar
#move your tar to some place
mv tiles.tar /some/path/to/tiles.tar
#need a bridged docker network so the kafka job can talk to the matcher service
docker network create --driver bridge opentraffic
#start up just the reporter python service (does the map matching)
#TODO: add -e DATASTORE_URL=http://localhost:8003/store? back in when its ready
docker run -d --net opentraffic -p 8002 --name reporter-py -v /some/path/to:/data/valhalla reporter:latest
#before we start the kafka worker you'll need the format of your incoming messages, right now separated value or json
#we specify what formatter we want and its properties with a simple string
#the first char is the separator to use when parsing the args out of the string
#the first argument is the type of formatter, right now separated value or json
#  for separated value if your messages looked like: `2017-01-31 16:00:00|uuid_abcdef|x|x|x|accuracy|x|x|x|lat|lon|x|x|x`
#  your formatter string will be: `,sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss`
#  the arguments to the sv type formatter are: separator regex, uuid column, lat column, lon column, time column, accuracy column and (optional) date format string
#  for json if your messages looked like: `{"timestamp":1495037969,"id":"uuid_abcdef","accuracy":51.305,"latitude":3.465725,"longitude":-76.5135033}`
#  your formatter string will be: `@json@id@latitude@longitude@timestamp@accuracy`
#  the arguments to the json type formatter are: uuid key, lat key, lon key, time key, accuracy and (optional) date format string
#  note the last argument of both is a date string format, if your data is already an epoch timestamp you dont need to provide it
#start up just the kafka reporter worker
docker run -d --net opentraffic --name reporter-kafka reporter:latest \
  /usr/local/bin/reporter-kafka -b YOUR_KAFKA_BOOTSTRAP_SERVER_AND_PORT -r raw -i formatted -l batched -f 'sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss' -u http://reporter-py:8002/report? -v
#tail some docker logs
reporterpy=$(docker ps -a | grep -F reporter-py | awk '{print $1}')
docker logs --follow ${reporterpy}
```

#### Debugging the application directly

```bash
#get some osmlr enabled routing tiles for your region
TODO: @gknisely show how to get a bbox and make a tar
#move your tar to some place
mv tiles.tar /some/path/to/tiles.tar
#install valhalla (or build it locally)
apt-add-repository -y ppa:valhalla-core/valhalla
apt-get update 
apt-get install valhalla-bin python-valhalla
#generate your valhalla config
valhalla_build_config --mjolnir-tile-extract /some/path/to/tiles.tar
#start up just the reporter python service (does the map matching)
#TODO: add DATASTORE_URL=http://localhost:8003/store? back in when its ready
#Note: PYTHONPATH is only needed if you are building valhalla locally, if you apt-get installed it above you wont need it
THREAD_POOL_COUNT=1 PYTHONPATH=../../valhalla/valhalla/.libs/ pdb py/reporter_service.py conf.json localhost:8002
#before we start the kafka worker you'll need the format of your incoming messages, right now separated value or json
#we specify what formatter we want and its properties with a simple string
#the first char is the separator to use when parsing the args out of the string
#the first argument is the type of formatter, right now separated value or json
#  for separated value if your messages looked like: `2017-01-31 16:00:00|uuid_abcdef|x|x|x|accuracy|x|x|x|lat|lon|x|x|x`
#  your formatter string will be: `,sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss`
#  the arguments to the sv type formatter are: separator regex, uuid column, lat column, lon column, time column, accuracy column and (optional) date format string
#  for json if your messages looked like: `{"timestamp":1495037969,"id":"uuid_abcdef","accuracy":51.305,"latitude":3.465725,"longitude":-76.5135033}`
#  your formatter string will be: `@json@id@latitude@longitude@timestamp@accuracy`
#  the arguments to the json type formatter are: uuid key, lat key, lon key, time key, accuracy and (optional) date format string
#  note the last argument of both is a date string format, if your data is already an epoch timestamp you dont need to provide it
#build the kafka reporter worker
sudo apt-get install -y openjdk-8-jdk maven
mvn clean package
#start up just the kafka reporter worker
target/reporter-kafka -b YOUR_KAFKA_BOOTSTRAP_SERVER_AND_PORT -r raw -i formatted -l batched -f 'sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss' -u http://localhost:8002/report? -v
#if you really want to debug, simply import the maven project into eclipse, make a new debug configureation, and add the arguments above to the arguments tab
#now you can set breakpoints etc and walk through the code in eclipse
```

When debugging, if you didnt already have a kafka stream handy to suck messages out of you can use the docker containers for just the kafka parts. If you do this the bit above about `YOUR_KAFKA_BOOTSTRAP_SERVER_AND_PORT` will be `localhost:9092`. Anyway start kafka and zookeeper in docker:

```bash
#need a bridged docker network so zookeeper and kafka can see eachother
docker network create --driver bridge opentraffic
#start zookeeper
docker run -d --net opentraffic -p 2181 --name zookeeper wurstmeister/zookeeper:latest
#start kafka
docker run -d --net opentraffic -p 9092 -e "KAFKA_ADVERTISED_HOST_NAME=localhost" -e "KAFKA_ADVERTISED_PORT=9092" -e "KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181" \
  -e "KAFKA_CREATE_TOPICS=raw:1:1,formatted:1:1,batched:4:1" -v /var/run/docker.sock:/var/run/docker.sock --name kafka wurstmeister/kafka:latest
#shovel messages into kafka from your local data source
cat YOUR_FLAT_FILE | py/cat_to_kafka.py --topic raw --bootstrap localhost:9092 -
```

### Exposed Ports/Services
* the container exposes port 8002 for the reporter python and docker-compose maps that port to your localhost
* you can test the reporter python http service with a trace to see what osmlr segments it matched: [click here](http://localhost:8002/report?json=%7B%22trace%22%3A%5B%7B%22lat%22%3A14.543087%2C%22lon%22%3A121.021019%2C%22time%22%3A1000%7D%2C%7B%22lat%22%3A14.543620%2C%22lon%22%3A121.021652%2C%22time%22%3A1008%7D%2C%7B%22lat%22%3A14.544957%2C%22lon%22%3A121.023247%2C%22time%22%3A1029%7D%2C%7B%22lat%22%3A14.545470%2C%22lon%22%3A121.023811%2C%22time%22%3A1036%7D%2C%7B%22lat%22%3A14.546580%2C%22lon%22%3A121.025124%2C%22time%22%3A1053%7D%2C%7B%22lat%22%3A14.547284%2C%22lon%22%3A121.025932%2C%22time%22%3A1064%7D%2C%7B%22lat%22%3A14.547817%2C%22lon%22%3A121.026665%2C%22time%22%3A1072%7D%2C%7B%22lat%22%3A14.549700%2C%22lon%22%3A121.028839%2C%22time%22%3A1101%7D%2C%7B%22lat%22%3A14.550350%2C%22lon%22%3A121.029610%2C%22time%22%3A1111%7D%2C%7B%22lat%22%3A14.551256%2C%22lon%22%3A121.030693%2C%22time%22%3A1125%7D%2C%7B%22lat%22%3A14.551785%2C%22lon%22%3A121.031395%2C%22time%22%3A1133%7D%2C%7B%22lat%22%3A14.553422%2C%22lon%22%3A121.033340%2C%22time%22%3A1158%7D%2C%7B%22lat%22%3A14.553819%2C%22lon%22%3A121.033806%2C%22time%22%3A1164%7D%2C%7B%22lat%22%3A14.553976%2C%22lon%22%3A121.033997%2C%22time%22%3A1167%7D%5D%7D)
* the output takes the form of: `{"segments":[{"segment_id": 12345, "start_time": 231231111.456, "end_time": 231231175.356, "length": 500, "internal": false, "begin_shape_index":0, "end_shape_index": 20} ... ]}`
  * segment_id is optinal and will not be present when the portion of the path did not have osmlr coverage, otherwise this id is the osmlr 64bit id
  * start_time is the time the path entered the osmlr segment, which will be -1 if the path got onto the segment in the middle of the segment
  * end_time is the time the path exited the osmlr segment, which will be -1 if the path exited from the segment in the middle of the segment
  * length is the length of the osmlr segment, which will be -1 if the segment was not completely traversed (entered or exited in the middle)
  * internal is a bool which says whether this portion of the path was on internal edges ones that can be ignored for the sake of transitioning from one segment to another. this cannot be true if segment_id is present
  * begin_shape_index is the index in the original trace before/at the start of the segment, useful for knowing which part of the trace constituted which segments
  * end_shape_index is the index in the original trace before/at the end of the segment, useful for knowing which part of the trace constituted which segments
* 3 other bits of code are running in the background to allow for on demand processing of single points at a time
  * the first two are kafka and zookeeper with some preconfigured topics to stream data on
  * the final piece is a kafka worker which does the reformatting of the raw stream and aggregates sequences of points by time and trace id (uuid)

### Env Var Overrides

The following environment variables are exposed to allow manipulation of the python matcher service:

- `MATCHER_BIND_ADDR`: the IP on which the process will bind inside the container. Defaults to '0.0.0.0'.
- `MATCHER_CONF_FILE`: the configuration file the process will reference. Defaults to '/etc/valhalla.json', which is included in the build of the container.
- `MATCHER_LISTEN_PORT`: the port on which the process will listen. Defaults to '8002'.

### Testing/Publishing Containers

This repository is tested on circleCI.

- pushes to master will result in a new container with the 'latest' tag being published on Docker Hub
- tagging in the form of `v{number}` will result in a docker container with a matching tag being built with whatever commit is referenced by that tag: e.g. tagging `v1.0.0` on master will result in a container with tag `v1.0.0` being built off of that tag on master.

### Manually Building and Publishing Containers

Example: build a container tagged 'test'.

```
docker build --tag opentraffic/reporter:test --force-rm .
docker push opentraffic/reporter:test
```

## Authentication

Currently we only support a rudimentary form of authentication between the reporter and the datastore. The idea is that the reporter will be run on premisis (ie. by fleet operator) and will then need to authenticate itself with the centralized datastore architecture. For now this is done via a `secret_key` query parameter in the reporters request url to the datastore. The datastore must be configured to do the authentication. The reporter gets the url for the datastore from an environment variable. This means that adding authentication only requires that one change this url to include the `secret_key` query parameter.
