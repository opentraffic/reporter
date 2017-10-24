# Open Traffic Reporter

Open Traffic Reporter is part of [OTv2](https://github.com/opentraffic/otv2-platform). It takes the place of OTv1's [Traffic Engine](https://github.com/opentraffic/traffic-engine) component.

Reporter takes in raw GPS probe data, matches it to [OSMLR segments](https://github.com/opentraffic/osmlr/blob/master/docs/intro.md) using [Valhalla](https://github.com/valhalla/valhalla/blob/master/docs/meili.md), and sends segments and speeds to the centralized [Open Traffic Datastore](https://github.com/opentraffic/datastore).

Reporter can be run in two ways:
- as a set of Java-based programs that consume live [Apache Kafka](https://kafka.apache.org/) location streams
- as a set of Python-based scripts that consume historical location snapshots

---

## Contents

<!-- to update contents:
  npm install -g markdown-toc
  markdown-toc -i README.md
-- >
<!-- toc -->

- [Kafka-based Reporter](#kafka-based-reporter)
  * [Method 1: data from file/stdin](#method-1-data-from-filestdin)
  * [Method 2: data from existing kafka](#method-2-data-from-existing-kafka)
    + [Just the reporter docker containers](#just-the-reporter-docker-containers)
    + [Debugging the application directly](#debugging-the-application-directly)
  * [Kafka](#kafka)
    + [Kafka Maintenance](#kafka-maintenance)
  * [Exposed Ports/Services](#exposed-portsservices)
  * [Reporter Output](#reporter-output)
      - [`datastore`: contain the mode and list of reports that are sent to the datastore](#datastore-contain-the-mode-and-list-of-reports-that-are-sent-to-the-datastore)
      - [`segment_matcher`: the result of matched segments from the traffic_segment_matcher](#segment_matcher-the-result-of-matched-segments-from-the-traffic_segment_matcher)
      - [`shape_used`: the index within the input trace that can be trimmed](#shape_used-the-index-within-the-input-trace-that-can-be-trimmed)
  * [Env Var Overrides](#env-var-overrides)
  * [Testing/Publishing Containers](#testingpublishing-containers)
  * [Manually Building and Publishing Containers](#manually-building-and-publishing-containers)
- [Script-based Reporter](#script-based-reporter)
- [Authentication](#authentication)
- [Configuration](#configuration)
- [Different Transport Modes](#different-transport-modes)

<!-- tocstop -->

---

## Kafka-based Reporter

### Method 1: data from file/stdin

To build/run the Reporter service via docker-compose:

```bash
#get some osmlr enabled routing tiles for your region via the download_tiles.sh located in the py directory.
#The documentation can be found here: https://github.com/opentraffic/reporter/tree/dev/py
./download_tiles.sh `Bounding_Box` `URL` `Output_Directory` `Number_of_Processes` `Tar_Output`
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
FORMATTER='sv,\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss' DATAPATH=/some/path/to docker-compose up
#shovel messages into kafka from your local data source
py/cat_to_kafka.py --topic raw --bootstrap localhost:9092 --key-with 'lambda line: line.split("|")[1]' YOUR_FLAT_FILE
#tail some docker logs
reporterpy=$(docker ps -a | grep -F reporter-py | awk '{print $1}')
docker logs --follow ${reporterpy}
```

### Method 2: data from existing kafka

If you already have a kafka stream setup then you'll only need to point the reporter at its outgoing topic with your messages on it. To do this you'll only need to run two of the pieces of software. The python reporter service and the kafka reporter stream processing application. These can either be run directly (especially in the case of debugging) or as docker containers. We'll go over both.


#### Just the reporter docker containers

```bash
#get some osmlr enabled routing tiles for your region via the download_tiles.sh located in the py directory. 
#The documentation can be found here: https://github.com/opentraffic/reporter/tree/dev/py
./download_tiles.sh `Bounding_Box` `URL` `Output_Directory` `Number_of_Processes` `Tar_Output`
#move your tar to some place
mv tiles.tar /some/path/to/tiles.tar
#need a bridged docker network so the kafka job can talk to the matcher service
docker network create --driver bridge opentraffic
#start up just the reporter python service (does the map matching)
#TODO: add -e DATASTORE_URL=http://localhost:8003/store? back in when its ready
docker run -d --net opentraffic -p 8002 --name reporter-py -v /some/path/to:/data/valhalla opentraffic/reporter:latest
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
docker run -d --net opentraffic --name reporter-kafka opentraffic/reporter:latest \
  /usr/local/bin/reporter-kafka -b YOUR_KAFKA_BOOTSTRAP_SERVER_AND_PORT -t raw,formatted,batched -f 'sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss' -u http://reporter-py:8002/report? -p 2 -q 3600 -i 600 -s TEST -o /results
#tail some docker logs
reporterpy=$(docker ps -a | grep -F reporter-py | awk '{print $1}')
docker logs --follow ${reporterpy}
```

#### Debugging the application directly

Say you want to make changes to the reporter, its a real pain to debug this through docker so lets not. Lets run those bits of the code directly:

```bash
#get some osmlr enabled routing tiles for your region via the download_tiles.sh located in the py directory.
#The documentation can be found here: https://github.com/opentraffic/reporter/tree/dev/py
./download_tiles.sh `Bounding_Box` `URL` `Output_Directory` `Number_of_Processes` `Tar_Output`
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
target/reporter-kafka -b YOUR_KAFKA_BOOTSTRAP_SERVER_AND_PORT -t raw,formatted,batched -f @json@id@latitude@longitude@timestamp@accuracy -u http://localhost:8002/report? -p 2 -q 3600 -i 600 -s TEST -o /results
#if you really want to debug, simply import the maven project into eclipse, make a new debug configureation, and add the arguments above to the arguments tab
#now you can set breakpoints etc and walk through the code in eclipse
```

When debugging, if you didnt already have a kafka stream handy to suck messages out of you can use the docker containers for just the kafka parts. If you do this the bit above about `YOUR_KAFKA_BOOTSTRAP_SERVER_AND_PORT` will be `localhost:9092`. Anyway start kafka and zookeeper in docker:

```bash
#need a bridged docker network so zookeeper and kafka can see eachother
docker network create --driver bridge opentraffic
#start zookeeper
docker run -d --net opentraffic -p 2181:2181 --name zookeeper wurstmeister/zookeeper:latest
#start kafka
docker run -d --net opentraffic -p 9092:9092 -e "KAFKA_ADVERTISED_HOST_NAME=localhost" -e "KAFKA_ADVERTISED_PORT=9092" -e "KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181" \
  -e "KAFKA_CREATE_TOPICS=raw:4:1,formatted:4:1,batched:4:1" -v /var/run/docker.sock:/var/run/docker.sock --name kafka wurstmeister/kafka:latest
#shovel messages into kafka from your local data source
cat YOUR_FLAT_FILE | py/cat_to_kafka.py --topic raw --bootstrap localhost:9092 --key-with 'lambda line: json.loads(line)["id"]' -
```

Notice the number `4` appearing multiple times in the above `docker run` command. This configures the number of partitions in each topic (its essentially akin to parallelism). You can increase or decrease this however you like for your particular system. The first topic `raw:4:1`, because it has 4 paritions must be keyed by uuid, as noted below. If you are not keying your input in this way please set it to `raw:1:1`.

### Kafka

We use kafka streams as the input mechanism to the reporter. You'll notice above that we rely on 3 topics being present. Its important that, if you are running your own Kafka infrastructure, that either the first topic is keyed by the uuid/vehicle id or that you only run a single partition in this topic. The reason for that is to prevent messages from arriving at the second topic in an out of order fashion.

You'll also notice that there are tons of options to the kafka stream program so we'll list them here for clarity:

```
usage: kafka-reporter
 -b,--bootstrap <arg>         Bootstrap servers config
 -d,--duration <arg>          How long to run the program in seconds,
                              defaults to (essentially) forever.
 -f,--formatter <arg>         The formatter configuration separated args
                              for constructing a custom formatter.
                              Separated value and json are currently
                              supported.
                              To construct a seprated value formatter
                              where the raw messages look like:
                              2017-01-31
                              16:00:00|uuid_abcdef|x|x|x|accuracy|x|x|x|la
                              t|lon|x|x|x
                              Specify a value of:
                              --formatter ",sv,\|,1,9,10,0,5,yyyy-MM-dd
                              HH:mm:ss"
                              To construct a json formatter where the raw
                              messages look like:
                              {"timestamp":1495037969,"id":"uuid_abcdef","
                              accuracy":51.305,"latitude":3.465725,"longit
                              ude":-76.5135033}
                              Specify a value of:
                              --formatter
                              ",json,id,latitude,longitude,timestamp,accur
                              acy"
                              Note that the time format string is
                              optional, ie when your time value is already
                              in epoch seconds.
 -i,--flush-interval <arg>    The interval, in seconds, at which tiles are
                              flushed to storage. Do not set this
                              parameter lower than the quantisation. Doing
                              so could result in tiles with very few
                              segment pairs.
 -m,--mode <arg>              The mode of travel the input data used.
                              Defaults to auto(mobile)
 -o,--output-location <arg>   A location to put the output histograms.
                              This can either be an http://location to
                              POST to or /a/directory to write files to.
                              If its of the form https://*.amazonaws.com
                              its assumed to be an s3 bucket and you'll
                              need to have the environment variables
                              AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
                              properly set.
 -p,--privacy <arg>           The minimum number of observations of a
                              given segment pair required before including
                              this pair in the histogram.
 -q,--quantisation <arg>      The granularity, in seconds, at which to
                              combine observations into as single tile.
                              Setting this to 3600 will result in tiles
                              where all segment pairs occuring within a
                              given hour will be in the same tile. Do not
                              set this parameter higher than the flush
                              interval parameter. Doing so could result in
                              tiles with very few segment pairs
 -r,--reports <arg>           The levels of osmlr segments we will report
                              on as the first segment in the segment pair.
                              Defaults to 0,1. Any combination of 0,1,2 is
                              allowed
 -s,--source <arg>            The name used in the tiles as a means of
                              identifying the source of the data.
 -t,--topics <arg>            A comma separated list of topics listed in
                              the order they are operated on in the kafka
                              stream.The first topic is the raw
                              unformatted input messages. The second is
                              the formatted messages. The third is
                              segments. The fourth is the anonymised
                              segments.
 -u,--reporter-url <arg>      The url to send batched/windowed portions of
                              a given keys points to.
 -x,--transitions <arg>       The levels of osmlr segments we will report
                              on as the second segment in the segment
                              pair. Defaults to 0,1. Any combination of
                              0,1,2 is allowed
```

#### Kafka Maintenance

If you run Kafka locally a lot it can start to get out of control with respect to both number of containers and disk space etc. If you want to kill off all of your containers try this:

    docker rm -f $(docker ps -qa);
    
If you want to remove all of your various versions of docker images try this:

    docker rmi -f $(docker images -q)
    
Finally if your disk is starting to fill up you can tell docker to free all of that space by doing:

    docker volume prune

### Exposed Ports/Services
* the container exposes port 8002 for the reporter python and docker-compose maps that port to your localhost
* you can test the reporter python http service with a trace to see 1) what is being sent to the datastore 2) what osmlr segments it matched 3) the shape used index within the input trace that can be trimmed (either been reported on or can be skipped) : [click here](http://localhost:8002/report?json={"uuid":"100609","trace":[{"lat":14.543087,"lon":121.021019,"time":1000},{"lat":14.543620,"lon":121.021652,"time":1008},{"lat":14.544957,"lon":121.023247,"time":1029},{"lat":14.545470,"lon":121.023811,"time":1036},{"lat":14.546580,"lon":121.025124,"time":1053},{"lat":14.547284,"lon":121.025932,"time":1064},{"lat":14.547817,"lon":121.026665,"time":1072},{"lat":14.549700,"lon":121.028839,"time":1101},{"lat":14.550350,"lon":121.029610,"time":1111},{"lat":14.551256,"lon":121.030693,"time":1125},{"lat":14.551785,"lon":121.031395,"time":1133},{"lat":14.553422,"lon":121.033340,"time":1158},{"lat":14.553819,"lon":121.033806,"time":1164},{"lat":14.553976,"lon":121.033997,"time":1167}]})
* the output takes the form of:
`"datastore":{"mode":"auto, "reports":[{"id": , next_id": , "queue_length": 0, "length": 500, "t0": , "t1": }]},`
`"segment_matcher": {"segments":[{"segment_id": 12345, "way_ids":[123123123], "start_time": 231231111.456, "end_time": 231231175.356, "queue_length": 0, "length": 500, "internal": false, "begin_shape_index":0, "end_shape_index": 20}], "mode":"auto},`
`"shape_used": 10}`

### Reporter Output

##### `datastore`: contain the mode and list of reports that are sent to the datastore
``` 
  * mode : a Valhalla mode of travel
  * reports : an array of reports that contain: 
      * id : segment id
      * next_id : next segment id
      * queue_length : the distance (meters) from the end of the segment where the speed drops below the threshold
      * length : the length of the osmlr segment, which will be -1 if the segment was not completely traversed (entered or exited in the middle)
      * t0 : the time at the start of the segment_id
      * t1 : the time at the start of the next_id; if that is empty, then we use the time at the end of the segment_id
```
##### `segment_matcher`: the result of matched segments from the traffic_segment_matcher
``` 
  * segments : an array of segments:
      * segment_id : optinal and will not be present when the portion of the path did not have osmlr coverage, otherwise this id is the osmlr 64bit id
      * way_ids : a list of way ids per segment
      * start_time : the time the path entered the osmlr segment, which will be -1 if the path got onto the segment in the middle of the segment
      * end_time : the time the path exited the osmlr segment, which will be -1 if the path exited from the segment in the middle of the segment
      * queue_length : the distance (meters) from the end of the segment where the speed drops below the threshold
      * length`: the length of the osmlr segment, which will be -1 if the segment was not completely traversed (entered or exited in the middle)
      * internal : a bool which says whether this portion of the path was on internal edges ones that can be ignored for the sake of transitioning from one segment to another. this cannot be true if segment_id is present
      * begin_shape_index : the index in the original trace before/at the start of the segment, useful for knowing which part of the trace constituted which segments
      * end_shape_index : the index in the original trace before/at the end of the segment, useful for knowing which part of the trace constituted which segments
  * mode : a Valhalla mode of travel
``` 
##### `shape_used`: the index within the input trace that can be trimmed

* 3 other bits of code are running in the background to allow for on demand processing of single points at a time
  * the first two are kafka and zookeeper with some preconfigured topics to stream data on
  * the final piece is a kafka worker which does the reformatting of the raw stream and aggregates sequences of points by time and trace id (uuid)

### Env Var Overrides

The following environment variables are exposed to allow manipulation of the python matcher service:

- `MATCHER_BIND_ADDR`: the IP on which the process will bind inside the container. Defaults to '0.0.0.0'.
- `MATCHER_CONF_FILE`: the configuration file the process will reference. Defaults to '/etc/valhalla.json', which is included in the build of the container.
- `MATCHER_LISTEN_PORT`: the port on which the process will listen. Defaults to '8002'.

### Testing/Publishing Containers

This repository is tested on [CircleCI](https://circleci.com/gh/opentraffic/reporter).

- pushes to master will result in a new container with the 'latest' tag being published on [Docker Hub](https://hub.docker.com/r/opentraffic/reporter/)
- tagging in the form of `v{number}` will result in a docker container with a matching tag being built with whatever commit is referenced by that tag: e.g. tagging `v1.0.0` on master will result in a container with tag `v1.0.0` being built off of that tag on master.

### Manually Building and Publishing Containers

Example: build a container tagged 'test'.

```
docker build --tag opentraffic/reporter:test --force-rm .
docker push opentraffic/reporter:test
```

## Script-based Reporter

Kafka is quite a bit of architecture with a lot of nice features and is being already used in organizations who handle a lot of data. For this reason Kafka was an obvious choice for our on-premises work. For those that want to run the reporter but don't want to manage the complexity of Kafka we have developed a simple script to make the same types of output the kafka reporters do. The scripted is located in `py/simple_reporter.py`. It's inputs are as follows:

```
usage: simple_reporter.py [-h] --src-bucket SRC_BUCKET --src-prefix SRC_PREFIX
                          [--src-key-regex SRC_KEY_REGEX]
                          [--src-valuer SRC_VALUER]
                          [--src-time-pattern SRC_TIME_PATTERN] --match-config
                          MATCH_CONFIG [--mode MODE]
                          [--report-levels REPORT_LEVELS]
                          [--transition-levels TRANSITION_LEVELS]
                          [--quantisation QUANTISATION]
                          [--inactivity INACTIVITY] [--privacy PRIVACY]
                          [--source-id SOURCE_ID] [--dest-bucket DEST_BUCKET]
                          [--concurrency CONCURRENCY] [--bbox BBOX]
                          [--trace-dir TRACE_DIR] [--match-dir MATCH_DIR]
                          [--cleanup CLEANUP]

optional arguments:
  -h, --help            show this help message and exit
  --src-bucket SRC_BUCKET
                        Bucket where to get the input trace data from
  --src-prefix SRC_PREFIX
                        Bucket prefix for getting source data
  --src-key-regex SRC_KEY_REGEX
                        Bucket key regex for getting source data
  --src-valuer SRC_VALUER
                        A lambda used to extract the uid, time, lat, lon,
                        accuracy from a given message in the input
  --src-time-pattern SRC_TIME_PATTERN
                        A string used to extract epoch seconds from a time
                        string
  --match-config MATCH_CONFIG
                        A file containing the config for the map matcher
  --mode MODE           The mode of transport used in generating the input
                        trace data
  --report-levels REPORT_LEVELS
                        Comma seprated list of levels to report on
  --transition-levels TRANSITION_LEVELS
                        Comma separated list of levels to allow transitions on
  --quantisation QUANTISATION
                        How large are the buckets to make tiles for. They
                        should always be an hour (3600 seconds)
  --inactivity INACTIVITY
                        How many seconds between readings of a given vehicle
                        to consider as inactivity and there for separate for
                        the purposes of matching
  --privacy PRIVACY     How many readings of a given segment pair must appear
                        before it being reported
  --source-id SOURCE_ID
                        A simple string to identify where these readings came
                        from
  --dest-bucket DEST_BUCKET
                        Bucket where we want to put the reporter output
  --concurrency CONCURRENCY
                        Number of threads to use when doing various stages of
                        processing
  --bbox BBOX           Comma separated coordinates within which data will be
                        reported: min_lat,min_lon,max_lat,max_lon
  --trace-dir TRACE_DIR
                        To bypass trace gathering supply the directory with
                        already parsed traces
  --match-dir MATCH_DIR
                        To bypass trace matching supply the directory with the
                        already matched segments
  --cleanup CLEANUP     Should temporary files be removed or not
```

Note that the program requires access to the map matching python module and a match config. The module is currently only available on linux and so the use of the program would depend on having access to a linux machine or docker.

The program works by first spawning a bunch of threads to download the source data from the bucket provided. You can use a regex to limit the data downloaded to just those files which match the regex. As the threads are downloading the source data they are parsing it according to the valuer lambda used to extract the various important information from a given line of the file. It also uses the time pattern to parse the time strings from the source data as well. This parsed data will be stored in many separate files each containing only the data for a small number of unique vehicles. After that source data is parsed and accumulated, more threads are spawned to crawl over the files and for each one assemble the trace of a given vehicle, get its osmlr segments and store those in the appropriate time tile files according to the quantisation parameter. After all traces have been matched to osmlr segments another set of threads is spawned to sort the tiles contents and remove observations which to meet the privacy threshold specified. The tiles are then uploaded to s3 where the datastore can do further processing. To reduce processing time and requirements you can specify a bounding box although this still requires all the source data to be filtered so it doesn't affect the time spent downloading sources.

The program can also allow you to resume processing at a certain phase. If for example you've downloaded all the data but stopped processing it during matching, you can resume with the matching process by using the the `--trace-dir` aregument. Similarly if you want to resume after the matching has finished you can pass the `--match-dir` argument. 

[More documentation](./load-historical-data/README.md) is available on how to use the script-based Reporter to load historical data.

## Authentication

Currently we only support a rudimentary form of authentication between the reporter and the datastore. The idea is that the reporter will be run on premisis (ie. by fleet operator) and will then need to authenticate itself with the centralized datastore architecture. For now this is done via s3 authentication where fleet operators will be given keys to access s3. More info about connecting the reporter to s3 can be found by running the kafka-reporter without argument to see configuration parameter.

## Configuration

The reporter works by using an algorithm called map matching to take gps traces and compute the paths they took given a backing route network. The route network in this case is provided by the [valhalla](https://github.com/valhalla) library which is used to do the map matching algorithm. The algorithm has a number of configuration parameters which can be tuned to the particular use-cases found within the input data. Currently these values are set to sensible defaults and are baked into the docker container. To make changes to these values you'll need to change the `Dockerfile` and build your own container with custom values. These values are set via the `valhalla_build_config` command within the `Dockerfile`. To see the different values for map matching you can run `valhalla_build_config` and have a look at the various `meili` options.

In addition, the Reporter can be configured to determine which levels of the road network can be reported to the Datastore. By default, the configuration is set to report on highway and arterial levels and to exclude local or residential roads. There are 2 environment variables that control this:

* REPORT_LEVELS=0,1,2 - This will enable reporting on all road levels including local roads. The default is set to 0,1 if no environment variable is set. 
* TRANSITION_LEVELS=0,1,2 - This will enable reporting transitions onto next segment for all road levels, including local roads. The defaults is set to 0,1 if no environment variable is set.

Note that setting to report next segment transitions on all levels will not necessarily mean that all transitions onto local roads will be reported. Since full segments must be traversed, any transition onto a local road that occurs along the middle of an arterial or highway traffic segment will not be reported.

## Different Transport Modes

The reporter is configured to handle automobile as the default transport mode. There are no means of automatically detecting different transport modes and separating reports into specific transport modes. A dedicated setup is required for each different transport mode and inputs must be segmented into the specific transport mode. If one needed to track a different transport mode (for example, bus) some changes to how the reporter is configured and run would be required. These changes include:
* Input GPS stream - The input GPS data must be separated by transport mode such that the inputs to the Reporter include GPS points for a single transport mode.
* Reporter TRANSPORT_MODE - Currently the reporter defaults to using a transport mode of `auto` when matching to OSMLR segments. An additional option needs to be added to the reporters to override this if a different type of data is expected. This transport mode must be one of the supported transport modes within the map-matching logic: bus, motor_scooter, bicycle, or auto.
* --dest_bucket - The destination bucket for where the output is written must be changed to be a separate S3 bucket. There are no means for combining transport modes within the Datastore or Public Data Extracts created from the Datastore. To handle a different transport mode within the Open Traffic system, a separate Datastore must be deployed and run for each separate transport mode.

There are also some considerations for how the Datastore is configured (TBD).

