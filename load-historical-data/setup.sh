#!/bin/bash
set -e

planet_file_date="2017_09_27-13_04_01"
workdir="/mnt/load_historical_data"

# basic sanity check
if [ ! -f /etc/lsb-release ]; then
  echo "This machine isn't running Ubuntu. Exiting!"
  exit 1
fi

# for r3.4xlarge
if [ ! -d ${workdir} ]; then
  echo "Creating xfs filesystem on /dev/xvdb"
  sudo mkfs -t xfs /dev/xvdb && sudo mount /dev/xvdb /mnt
  sudo mkdir -p ${workdir} && sudo chown $(whoami) ${workdir}
fi

#get deps
sudo add-apt-repository -y ppa:valhalla-core/valhalla
sudo apt-get update
sudo apt-get install -y \
  python \
  python-pip \
  python-valhalla \
  valhalla-bin \
  python-boto3

cp run.sh ${workdir}
cp load_data.sh ${workdir}
cp ../py/reporter_service.py ${workdir}
cp ../py/simple_reporter.py ${workdir}

pushd ${workdir}

if [ ! -d logs ]; then
  mkdir logs
fi

#get data into the config
if [ ! -f planet_${planet_file_date}.tar ]; then
  echo "Downloading planet tarball"
  wget -O planet_${planet_file_date}.tar \
    https://s3.amazonaws.com/reporter-tiles/planet_${planet_file_date}/planet_${planet_file_date}.tar
fi

# build config
valhalla_build_config \
  --mjolnir-tile-extract \
  planet_${planet_file_date}.tar \
  --meili-default-max-route-time-factor 2 \
  > conf.json

echo "Setup is complete! Go to ${workdir} and use run.sh to start loading historical data."
