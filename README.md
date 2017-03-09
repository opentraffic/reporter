# Open Traffic Reporter

Open Traffic Reporter is part of OTv2, the new Open Traffic platform under development. It will take the place of OTv1's [Traffic Engine](https://github.com/opentraffic/traffic-engine) component.

Reporter takes in raw GPS probe data, matches it to [OSMLR segments](https://github.com/opentraffic/osmlr/blob/master/docs/intro.md) using [Valhalla Meili](https://github.com/valhalla/valhalla/blob/master/docs/meili.md), and sends segments and speeds to the centralized [Open Traffic Datastore](https://github.com/opentraffic/datastore).

## Docker

Build/run the python [matcher service](https://github.com/opentraffic/reporter) via docker-compose.

### To run via docker composer
* move your tarball to `/some/path/to/data/tiles.tar`
  * the path is of your choosing, the name of the tarball is currently required to be `tiles.tar`
* `DATAPATH=/some/path/to/data docker-compose up`

### Exposed Ports/Services
* the container exposes port 8002 for the report and docker-compose maps that port locally
* the container exposes port 6379 for redis and docker-compose maps that port locally
* example browser request from your local machine: [click me](http://localhost:8002/segment_match?json={"trace":[ {"lat":14.543087,"lon":121.021019,"time":1000}, {"lat":14.543620,"lon":121.021652,"time":1008}, {"lat":14.544957,"lon":121.023247,"time":1029}, {"lat":14.545470,"lon":121.023811,"time":1036}, {"lat":14.546580,"lon":121.025124,"time":1053}, {"lat":14.547284,"lon":121.025932,"time":1064}, {"lat":14.547817,"lon":121.026665,"time":1072}, {"lat":14.549700,"lon":121.028839,"time":1101}, {"lat":14.550350,"lon":121.029610,"time":1111}, {"lat":14.551256,"lon":121.030693,"time":1125}, {"lat":14.551785,"lon":121.031395,"time":1133}, {"lat":14.553422,"lon":121.033340,"time":1158}, {"lat":14.553819,"lon":121.033806,"time":1164}, {"lat":14.553976,"lon":121.033997,"time":1167}]})

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

NOTE:  This is taken care of by the docker container. The csv formatter script can be run locally on your mac and not inside the container as should the command to curl the requests to the service.
To run the Reporter service and send the created json requests via POST:
start reporter service from the py directory:
`PYTHONPATH=PYTHONPATH:../../valhalla/valhalla/.libs REDIS_HOST=localhost DATASTORE_URL=http://localhost:8003/store? ./py/reporter_service.py ../../conf/manila.json localhost:8002`

Build/run the python [matcher service](https://github.com/opentraffic/reporter) via docker-compose.

### To run via Docker
* move your tarball to `/some/path/to/data/tiles.tar`
  * the path is of your choosing, the name of the tarball is currently required to be `tiles.tar`
* `export DATAPATH=/data/valhalla/manila`
* `sudo docker build -t opentraffic/reporter .`
* `sudo -E /usr/bin/docker-compose up`

 Run the following to curl the reporter requests thru the reporter service via POST from the py directory:

```sh
time cat py/reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/segment_match?
```

OR Curl a specific # of requests thru the reporter service via POST:

```sh
head -n 10 py/reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/segment_match?
```

example:
http://localhost:8002/segment_match?json={"uuid":"100609","trace":[{"lat":14.597706,"lon":120.984148,"time":1480521600},{"lat":14.597706,"lon":120.984148,"time":1480521616},{"lat":14.597706,"lon":120.984148,"time":1480521631},{"lat":14.597706,"lon":120.984148,"time":1480521646},{"lat":14.597706,"lon":120.984148,"time":1480521661},{"lat":14.597706,"lon":120.984148,"time":1480521676},{"lat":14.597706,"lon":120.984148,"time":1480521690},{"lat":14.597706,"lon":120.984148,"time":1480521706},{"lat":14.598095,"lon":120.984111,"time":1480521722},{"lat":14.598095,"lon":120.984111,"time":1480521735},{"lat":14.598408,"lon":120.984153,"time":1480521750},{"lat":14.598408,"lon":120.984153,"time":1480521768}]}
