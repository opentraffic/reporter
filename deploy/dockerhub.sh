#!/usr/bin/env bash
set -e

echo "Logging into dockerhub..."
docker login -e "${DOCKER_EMAIL}" -u "${DOCKER_USER}" -p "${DOCKER_PASS}"

echo "Tagging and pushing latest build..."
docker tag reporter:latest opentraffic/reporter:latest
docker push opentraffic/reporter:latest

echo "Tagging and pushing ${CIRCLE_SHA1}..."
docker tag reporter:latest opentraffic/reporter:${CIRCLE_SHA1}
docker push opentraffic/reporter:${CIRCLE_SHA1}

echo "Done!"
