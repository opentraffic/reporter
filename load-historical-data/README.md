## Load Historical Data Using Script-based Reporter

This directory contains the following:

- `setup.sh`, which will prepare a system with all the components need to begin loading historical data using the [script-based Reporter](../README.md#script-based-reporter).
- `load.sh`, which is invoked by...
- `run.sh`, which is used to start the loading process for a given month/year

## System Requirements

- Ubuntu 16.04
- the included configuration and setup is tailored to an r3.4xlarge instance using local
  ssd storage. Alterations of the setup script will be required to run from any other instance
  type and have not been tested.
- access to both `s3://grab_historical_data` and to the reporter drop bucket for the environment
  in question: `s3://reporter-drop-{prod, dev}`

The Opsworks stacks `reporter::{prod, dev}::us-east` contain a layer (Load Historical Data) which
has all the required access and configuration, and it's recommended to use the instances currently
set up there.

## Usage

Edit `run.sh` to pass the day/month/year you wish to load. If you want to run an entire month from
a single machine:

```sh
#!/bin/bash

# example: load february: run this via
#   nohup ./run.sh >logs/run.out 2>&1 &
for i in {01..31}; do
  ./load_data.sh $i 03 2017 && rm -rf ./tmp*
done
```

If you want to perform the same load in half the time, use two instances,
run `setup.sh` on both of them, and then split the days across them:

```sh
#!/bin/bash

# example: load half of february: run this via
#   nohup ./run.sh >logs/run.out 2>&1 &
for i in {01..15}; do
  ./load_data.sh $i 03 2017 && rm -rf ./tmp*
done
```

```sh
#!/bin/bash

# example: load the other half of february: run this via
#   nohup ./run.sh >logs/run.out 2>&1 &
for i in {16..31}; do
  ./load_data.sh $i 03 2017 && rm -rf ./tmp*
done
```

You can continue with this model to break down a month into as few days as you like spread across N
machines to decrease the time required to load a day's worth of data. Present measurements indicate
that a single day of data made up of 130mb parts will take ~2 hours to process with this configuration.
