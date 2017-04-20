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
  echo -e "Usage:\n-s s3 bucket url\n-f regex to use with grep to get interesting files\n-u reporter url\n-j concurrency for posting requests\n" 1>&2
  echo "Example: AWS_DEFAULT_PROFILE=big_data $0 -s s3://heaps_of_data/2016_11/ -f 2016_11_01.*gz -u http://opentraffic.io/report? -j 16" 1>&2
  echo "Note: bucket listing is not recursive" 1>&2
  echo "Note: data is pipe delimited: date|id|x|x|x|x|x|x|x|lat|lon|x|x with date format: %Y-%m-%d %H:%M:%S" 1>&2
  exit 1
}

par=$(nproc)
while getopts ":s:f:u:j:b" opt; do
  case $opt in
    s) s3_dir=$(echo ${OPTARG} | sed -e 's@/\?$@/@g')
    ;;
    f) file_re="${OPTARG}"
    ;;
    u) url="${OPTARG}"
    ;;
    j) par="${OPTARG}"
    ;;
    \?) echo "Invalid option -${OPTARG}" 1>&2 && usage
    ;;
  esac
done

if [[ -z ${s3_dir} ]] || [[ -z ${file_re} ]] || [[ -z ${url} ]]; then
  echo "Missing required option" 1>&2 && usage
fi

#get all the list of files we'll be working with
echo "Retrieving file list from s3"
files=$(aws s3 ls ${s3_dir} | awk '{print $4}' | grep -E ${file_re} | tr '\n' ' ')
echo "Processing $(echo ${files} | tr ' ' '\n' | wc -l) files"


for file in ${files}; do
  #download in the foreground
  echo "Retrieving ${file} from s3" && aws s3 cp ${s3_dir}${file} . &> /dev/null
  #make requests with just this file
  zcat ${file} | sort | ./to_post_body.py --time-between 0 --batch-size 1 - | parallel --no-notice -j ${par} wget ${url} -O - -q --post-data '{}'\; echo ""
  #done with this
  echo "Finished POST'ing ${file}" && rm -f ${file}
done


