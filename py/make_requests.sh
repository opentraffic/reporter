#!/bin/bash
trap "kill 0" EXIT
which parallel &> /dev/null
if [ $? != 0 ]; then
        echo "parallel is required please install it"
        echo "sudo apt-get install parallel"
        exit 1
fi
set -e

if [ -z $3 ]; then
  echo "Usage: $0 s3://some_bucket/some_path some_file_regex some_reporter_url [concurrency=$(nproc)]" 1>&2
  echo "Example: AWS_DEFAULT_PROFILE=big_data $0 s3://heaps_of_data/2016_11/ 2016_11_01.*gz http://opentraffic.io/report? 16"
  echo "Note: bucket listing is not recursive" 1>&2
  echo "Note: data is pipe delimited: date|id|x|x|x|x|x|x|x|lat|lon|x|x with date format: %Y-%m-%d %H:%M:%S" 
  exit 1
fi

dir=$(echo ${1} | sed -e 's@/\?$@/@g')
pre=${2}
url=${3}
par=${4}

#get all the list of files we'll be working with
echo "Retrieving file list from s3"
files=$(aws s3 ls ${dir} | awk '{print $4}' | grep -E ${pre} | tr '\n' ' ')
echo "Processing $(echo ${files} | tr ' ' '\n' | wc -l) files"

#start downloading them in the background
(
for file in ${files}; do
  if [[ ! -e ${file} ]]; then
    echo "Retrieving ${file} from s3"
    aws s3 cp ${dir}${file} . &> /dev/null
  fi
done
) &

#start making requests in the foreground
./wait_cat.py ${files} | zcat - | ./to_json.py - | parallel --no-notice -j ${par} curl ${url} -w '\\n' -s --data '{}'
