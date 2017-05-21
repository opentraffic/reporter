# Open Traffic Reporter

Open Traffic Reporter is part of OTv2, the new Open Traffic platform under development. It will take the place of OTv1's [Traffic Engine](https://github.com/opentraffic/traffic-engine) component.

Reporter takes in raw GPS probe data, matches it to [OSMLR segments](https://github.com/opentraffic/osmlr/blob/master/docs/intro.md) using [Valhalla Meili](https://github.com/valhalla/valhalla/blob/master/docs/meili.md), and sends segments and speeds to the centralized [Open Traffic Datastore](https://github.com/opentraffic/datastore).

## Docker

Set a DOCKER_HOST env var:
  export DOCKER_HOST=$(ip -4 addr show docker0 | grep -Po 'inet \K[\d.]+')

Build/run the python [matcher service](https://github.com/opentraffic/reporter) via docker-compose.

## Kafka & Zookeeper

If interested in running your own Kafka Producer and Consumer, please check out this GitHub repository on Docker Hub for instructions on how to do so:
[kafka-docker](http://wurstmeister.github.io/kafka-docker/)

OR

Once you have the necessary scripts from the [kafka-docker], you can follow these steps:

  Set a DOCKER_HOST env var:
  export DOCKER_HOST=$(ip -4 addr show docker0 | grep -Po 'inet \K[\d.]+')

  Terminal 1:
  docker-compose scale kafka=2
  docker-compse up

  Terminal 2: CREATE TOPIC AND DESCRIBE
  ./start-kafka-shell.sh ${DOCKER_HOST} ${DOCKER_HOST}:2181
  bash-4.3# $KAFKA_HOME/bin/kafka-topics.sh --create --topic topic --partitions 4 --zookeeper $ZK --replication-factor 2
  bash-4.3# $KAFKA_HOME/bin/kafka-topics.sh --describe --topic topic --zookeeper $ZK

  Terminal 3: START PRODUCER(BROKERS)
  ./start-kafka-shell.sh ${DOCKER_HOST} ${DOCKER_HOST}:2181
  bash-4.3# $KAFKA_HOME/bin/kafka-console-producer.sh --broker-list ${DOCKER_HOST}:9092 --topic topic

  Terminal 4: START CONSUMER
  ./start-kafka-shell.sh ${DOCKER_HOST} ${DOCKER_HOST}:2181
  bash-4.3# $KAFKA_HOME/bin/kafka-console-consumer.sh --zookeeper ${DOCKER_HOST}:2181 --topic topic --from-beginning

### To run via docker composer
* move your tarball to `/some/path/to/data/tiles.tar`
  * the path is of your choosing, the name of the tarball is currently required to be `tiles.tar`
* `DATAPATH=/some/path/to/data docker-compose up`

### Exposed Ports/Services
* the container exposes port 8002 for the report and docker-compose maps that port locally
* the container exposes docker-compose maps that port locally
* example browser request from your local machine: [click here](http://localhost:8002/report?json=%7B%22trace%22%3A%5B%7B%22lat%22%3A14.543087%2C%22lon%22%3A121.021019%2C%22time%22%3A1000%7D%2C%7B%22lat%22%3A14.543620%2C%22lon%22%3A121.021652%2C%22time%22%3A1008%7D%2C%7B%22lat%22%3A14.544957%2C%22lon%22%3A121.023247%2C%22time%22%3A1029%7D%2C%7B%22lat%22%3A14.545470%2C%22lon%22%3A121.023811%2C%22time%22%3A1036%7D%2C%7B%22lat%22%3A14.546580%2C%22lon%22%3A121.025124%2C%22time%22%3A1053%7D%2C%7B%22lat%22%3A14.547284%2C%22lon%22%3A121.025932%2C%22time%22%3A1064%7D%2C%7B%22lat%22%3A14.547817%2C%22lon%22%3A121.026665%2C%22time%22%3A1072%7D%2C%7B%22lat%22%3A14.549700%2C%22lon%22%3A121.028839%2C%22time%22%3A1101%7D%2C%7B%22lat%22%3A14.550350%2C%22lon%22%3A121.029610%2C%22time%22%3A1111%7D%2C%7B%22lat%22%3A14.551256%2C%22lon%22%3A121.030693%2C%22time%22%3A1125%7D%2C%7B%22lat%22%3A14.551785%2C%22lon%22%3A121.031395%2C%22time%22%3A1133%7D%2C%7B%22lat%22%3A14.553422%2C%22lon%22%3A121.033340%2C%22time%22%3A1158%7D%2C%7B%22lat%22%3A14.553819%2C%22lon%22%3A121.033806%2C%22time%22%3A1164%7D%2C%7B%22lat%22%3A14.553976%2C%22lon%22%3A121.033997%2C%22time%22%3A1167%7D%5D%7D)

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

## Steps to run the CSV Formatter and Reporter Service Locally or via Docker.

### Get some data!

Download sample probe data and place in a `/data/traffic/<manila>` directory

### Create the reporter_requests.json by converting the data from CSV to JSON

To import probe data and create the json request file to be used as input to the Reporter service, run (passing path to data as argument) from the reporter directory:
`./py/csv_formatter.py /data/traffic/manila > reporter_requests.json`

#### Instead of using Docker

NOTE:  This is taken care of by the docker container. The csv formatter script can be run from your local machine and not inside the container as should the command to curl the requests to the service.
To run the Reporter service and send the created json requests via POST:
start reporter service from the py directory:
`PYTHONPATH=PYTHONPATH:../../valhalla/valhalla/.libs DATASTORE_URL=http://localhost:8003/store? ./py/reporter_service.py ../../conf/manila.json localhost:8002`

Build/run the python [matcher service](https://github.com/opentraffic/reporter) via docker-compose.

### To run via Docker
* move your tarball to `/some/path/to/data/tiles.tar`
  * the path is of your choosing, the name of the tarball is currently required to be `tiles.tar`
* `export DATAPATH=/data/valhalla/manila`
* `export DOCKER_HOST=$(ip -4 addr show docker0 | grep -Po 'inet \K[\d.]+')`
* `sudo docker build -t opentraffic/reporter .`
* `sudo -E /usr/bin/docker-compose up`

 Run the following to curl the reporter requests thru the reporter service via POST from the py directory:

```sh
time cat py/reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/report?
```

OR Curl a specific # of requests thru the reporter service via POST:

```sh
head -n 10 py/reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/report?
```

example:
http://localhost:8002/report?json={"uuid":"100609","trace":[{"lat":14.597706,"lon":120.984148,"time":1480521600},{"lat":14.597706,"lon":120.984148,"time":1480521616},{"lat":14.597706,"lon":120.984148,"time":1480521631},{"lat":14.597706,"lon":120.984148,"time":1480521646},{"lat":14.597706,"lon":120.984148,"time":1480521661},{"lat":14.597706,"lon":120.984148,"time":1480521676},{"lat":14.597706,"lon":120.984148,"time":1480521690},{"lat":14.597706,"lon":120.984148,"time":1480521706},{"lat":14.598095,"lon":120.984111,"time":1480521722},{"lat":14.598095,"lon":120.984111,"time":1480521735},{"lat":14.598408,"lon":120.984153,"time":1480521750},{"lat":14.598408,"lon":120.984153,"time":1480521768}]}

## Authentication

Currently we only support a rudimentary form of authentication between the reporter and the datastore. The idea is that the reporter will be run on premisis (ie. by fleet operator) and will then need to authenticate itself with the centralized datastore architecture. For now this is done via a `secret_key` query parameter in the reporters request url to the datastore. The datastore must be configured to do the authentication. The reporter gets the url for the datastore from an environment variable. This means that adding authentication only requires that one change this url to include the `secret_key` query parameter.

## Flink WIP

First step is to install flink but to get it to work on newer ubuntu you need to make sure you use openjdk8 instead of openjdk9 (the default).

    sudo apt-get install openjdk-8-jdk
    export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-amd64

Then for the most part you follow [this](https://ci.apache.org/projects/flink/flink-docs-release-1.3/quickstart/setup_quickstart.html#quickstart) to get flink running. The quick summary is this:

    git clone --branch master --depth 1 --recursive https://github.com/apache/flink.git
    cd flink
    mvn clean package -DskipTests #this takes a while
    export FLINK_HOME=${PWD}/build-target
    ${FLINK_HOME}/bin/start-local.sh
    tail ${FLINK_HOME}/log/flink-*-jobmanager-*.log    

If you like GUIs then you can have a look at [http://localhost:8081](http://localhost:8081) to see what flink is doing. Later on when you are done running flink you can kill it with:

    ${FLINK_HOME}/bin/stop-local.sh

After you've verified that flink is up and running you can run the accumulator on flink. The accumulator has two modes; file-based for local testing and kafka-based for running in a larger real-time system. To build the accumulator program do:

    mvn clean package

To run it in file mode do:

    ${FLINK_HOME}/bin/flink run -c opentraffic.accumulator.Accumulator target/accumulator-1.0-SNAPSHOT.jar --file some_file --reporter http://localhost:8002/report?

And to run it in kafka mode do:

    ${FLINK_HOME}/bin/flink run -c opentraffic.accumulator.Accumulator target/accumulator-1.0-SNAPSHOT.jar --topic some_topic --bootstrap.servers kafka_brokers --zookeeper.connect zk_quorum --group.id some_id --reporter http://localhost:8002/report?
