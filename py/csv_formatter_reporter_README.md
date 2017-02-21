# Steps to run the CSV Formatter and Reporter Service Locally or via Docker.

### Get some data!

Download sample GRAB data and place in a /data/traffic/<manila> directory

### Create the reporter_requests.json by converting the data from CSV to JSON

To import the manila data sample from GRAB and create the json request file to be used as input to the Reporter service, run (passing path to data as argument) from the reporter directory:
./py/csv_formatter.py /data/traffic/manila > reporter_requests.json

#### Instead of using Docker

NOTE:  This is taken care of by the docker container. The csv formatter script can be run locally on your mac and not inside the container as should the command to curl the requests to the service.
To run the Reporter service and send the created json requests via POST:
start reporter service from the py directory:
PYTHONPATH=PYTHONPATH:../../valhalla/valhalla/.libs REDIS_HOST=localhost DATASTORE_URL=http://localhost:8003/store? ./py/reporter_service.py ../../conf/manila.json localhost:8002

Build/run the python [matcher service](https://github.com/opentraffic/reporter) via docker-compose.


### To run via Docker
* move your tarball to `/some/path/to/data/tiles.tar`
  * the path is of your choosing, the name of the tarball is currently required to be `tiles.tar`
* export DATAPATH=/data/valhalla/manila
* sudo docker build -t opentraffic/reporter .
* sudo -E /usr/bin/docker-compose up

 Run the following to curl the reporter requests thru the reporter service via POST from the py directory:
time cat py/reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/segment_match?

OR

 Curl a specific # of requests thru the reporter service via POST:
head -n 10 py/reporter_requests.json | parallel --progress -j7 curl -s --data '{}' -o /dev/null http://localhost:8002/segment_match?


example:
http://localhost:8002/segment_match?json={"uuid":"100609","trace":[{"lat":14.597706,"lon":120.984148,"time":1480521600},{"lat":14.597706,"lon":120.984148,"time":1480521616},{"lat":14.597706,"lon":120.984148,"time":1480521631},{"lat":14.597706,"lon":120.984148,"time":1480521646},{"lat":14.597706,"lon":120.984148,"time":1480521661},{"lat":14.597706,"lon":120.984148,"time":1480521676},{"lat":14.597706,"lon":120.984148,"time":1480521690},{"lat":14.597706,"lon":120.984148,"time":1480521706},{"lat":14.598095,"lon":120.984111,"time":1480521722},{"lat":14.598095,"lon":120.984111,"time":1480521735},{"lat":14.598408,"lon":120.984153,"time":1480521750},{"lat":14.598408,"lon":120.984153,"time":1480521768}]}
