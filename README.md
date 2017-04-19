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

## Authentication

Currently we only support a rudimentary form of authentication between the reporter and the datastore. The idea is that the reporter will be run on premisis (ie. by fleet operator) and will then need to authenticate itself with the centralized datastore architecture. For now this is done via a `secret_key` query parameter in the reporters request url to the datastore. The datastore must be configured to do the authentication. The reporter gets the url for the datastore from an environment variable. This means that adding authentication only requires that one change this url to include the `secret_key` query parameter.
