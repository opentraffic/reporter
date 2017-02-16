#!/usr/bin/env bash

docker login -e ${DOCKER_EMAIL} -u ${DOCKER_USER} -p ${DOCKER_PASS}

docker tag reporter:latest opentraffic/reporter:latest
docker push opentraffic/reporter:latest

docker tag reporter:latest opentraffic/reporter:${CIRCLE_SHA1}
docker push opentraffic/reporter:${CIRCLE_SHA1}
