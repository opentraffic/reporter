FROM ubuntu:16.04
MAINTAINER Grant Heffernan <grant@mapzen.com>

# env
ENV DEBIAN_FRONTEND noninteractive

ENV VALHALLA_VERSION "2.1.5"

ENV MATCHER_DATA_DIR ${MATCHER_DATA_DIR:-"/data/valhalla"}
ENV MATCHER_CONF_FILE ${MATCHER_CONF_FILE:-"/etc/valhalla.json"}
ENV MATCHER_TILE_EXTRACT ${MATCHER_TILE_EXTRACT:-"tiles.tar"}
ENV MATCHER_BIND_ADDR ${MATCHER_BIND_ADDR:-"0.0.0.0"}
ENV MATCHER_LISTEN_PORT ${MATCHER_LISTEN_PORT:-"8002"}

# install dependencies
RUN apt-get update && apt-get install -y \
      python \
      python-redis \
      python-requests \
      software-properties-common

RUN apt-add-repository -y ppa:kevinkreiser/prime-server
RUN apt-add-repository -y ppa:valhalla-routing/valhalla
RUN apt-get update && apt-get install -y \
      valhalla${VALHALLA_VERSION}-bin \
      python-valhalla${VALHALLA_VERSION}

# install code & config
ADD ./py /reporter
RUN valhalla_build_config \
      --mjolnir-tile-dir ${MATCHER_DATA_DIR} \
      --mjolnir-tile-extract ${MATCHER_DATA_DIR}/${MATCHER_TILE_EXTRACT} \
      >${MATCHER_CONF_FILE}

# cleanup
RUN apt-get clean && \
      rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

EXPOSE ${MATCHER_LISTEN_PORT}

CMD /reporter/reporter_service.py ${MATCHER_CONF_FILE} ${MATCHER_BIND_ADDR}:${MATCHER_LISTEN_PORT}
