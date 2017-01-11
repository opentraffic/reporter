FROM ubuntu:16.04
MAINTAINER Grant Heffernan <grant@mapzen.com>

# env
ENV DEBIAN_FRONTEND noninteractive

ENV MATCHER_CONF_FILE ${MATCHER_CONF_FILE:-"/etc/valhalla.json"}
ENV MATCHER_BIND_ADDR ${MATCHER_BIND_ADDR:-"0.0.0.0"}
ENV MATCHER_LISTEN_PORT ${MATCHER_LISTEN_PORT:-"8002"}

# install dependencies
RUN apt-get update && apt-get install -y \
      python \
      software-properties-common

RUN apt-add-repository -y ppa:kevinkreiser/prime-server
RUN apt-add-repository -y ppa:valhalla-routing/valhalla
RUN apt-get update && apt-get install -y \
      python-valhalla

# install code & default config
ADD ./py /reporter
ADD http://raw.githubusercontent.com/valhalla/conf/master/valhalla.json /etc/valhalla.json

# cleanup
RUN apt-get clean && \
      rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

EXPOSE ${MATCHER_LISTEN_PORT}

CMD /reporter/reporter_service.py ${MATCHER_CONF_FILE} ${MATCHER_BIND_ADDR}:${MATCHER_LISTEN_PORT}
