#!/bin/bash
set -e

#get java
apt-get install openjdk-8-jdk
export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-amd64

#flink env vars
FLINK_CLONE="${1}"
: ${FLINK_CLONE:="flink"}
export FLINK_HOME=${FLINK_CLONE}/build-target

#see if we can start it
set +e
${FLINK_HOME}/bin/start-local.sh
if [ $? -eq 0 ]; then
  exit 0
fi
set -e

#build flink
git clone --branch master --depth 1 --recursive https://github.com/apache/flink.git ${FLINK_CLONE}
cd ${FLINK_CLONE}
mvn clean package -DskipTests #this takes a while

#start it again
${FLINK_HOME}/bin/start-local.sh
tail ${FLINK_HOME}/log/flink-*-jobmanager-*.log
