#!/bin/bash
trap "kill 0" EXIT
which parallel &> /dev/null
if [ $? != 0 ]; then
        echo "parallel is required please install it"
        echo "sudo apt-get install parallel"
        exit 1
fi
set -e

function usage {
  echo -e "Usage:\n-f day file to process\n" 1>&2
  echo "Example: AWS_DEFAULT_PROFILE=opentraffic $0 -f 2017_01_01_partial.gz -b localhost:9092 -t raw" 1>&2
  echo "Note: bucket listing is not recursive" 1>&2
  echo "Note: data is pipe delimited: date|id|x|x|x|x|x|x|x|lat|lon|x|x with date format: %Y-%m-%d %H:%M:%S" 1>&2
  exit 1
}

while getopts ":s:f:b:t:" opt; do
  case $opt in
    f) day_file="${OPTARG}"
    ;;
    b) bootstrap="${OPTARG}"
    ;;
    t) topic="${OPTARG}"
    ;;
    \?) echo "Invalid option -${OPTARG}" 1>&2 && usage
    ;;
  esac
done

hash=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)
key_with='lambda line: line.split("|")[1]'
value_with="lambda line: re.sub(r'(.*:[0-5][0-9]\\|)([0-9]+)(\\|.*)', r'\\1\\2${hash}\\3', line)"

if [[ -z ${day_file} ]] || [[ -z ${bootstrap} ]] || [[ -z ${topic} ]]; then
  echo "Missing required option" 1>&2 && usage
fi

echo "day_file=${day_file}"
echo "bootstrap=${bootstrap}"
echo "topic=${topic}"
#send to kafka producer
zcat ${day_file} | ./cat_to_kafka.py --bootstrap ${bootstrap} --topic ${topic} --key-with "${key_with}" --value-with "${value_with}" -

