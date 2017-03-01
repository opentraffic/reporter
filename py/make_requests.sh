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
  echo -e "Usage:\n-s s3 bucket url\n-f regex to use with grep to get interesting files\n-u reporter url\n-j concurrency for posting requests\n-b whether to run in the downloads in the background or not\n" 1>&2
  echo "Example: AWS_DEFAULT_PROFILE=big_data $0 -s s3://heaps_of_data/2016_11/ -f 2016_11_01.*gz -u http://opentraffic.io/report? -j 16 -b" 1>&2
  echo "Note: bucket listing is not recursive" 1>&2
  echo "Note: data is pipe delimited: date|id|x|x|x|x|x|x|x|lat|lon|x|x with date format: %Y-%m-%d %H:%M:%S" 1>&2
  exit 1
}

par=$(nproc)
unset bgrnd
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
    b) bgrnd="${OPTARG}"
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


if [[ ! -z ${bgrnd+x} ]]; then
  echo "Continuously POST'ing..."
  #start downloading them in the background
  (
    for file in ${files}; do
      echo "Retrieving ${file} from s3"
      aws s3 cp ${s3_dir}${file} . &> /dev/null
      echo "Retrieved ${file} from s3"
    done
  ) &
  #start making requests in the foreground
  ./wait_cat.py --delete ${files} | zcat - | ./to_post_body.py - | parallel --no-notice -j ${par} wget ${url} -O - -q --post-data '{}'\; echo ""
else
  for file in ${files}; do
    #download in the foreground
    echo "Retrieving ${file} from s3" && aws s3 cp ${s3_dir}${file} . &> /dev/null
    #make requests with just this file
    zcat ${file} | ./to_post_body.py - | parallel --no-notice -j ${par} wget ${url} -O - -q --post-data '{}'\; echo ""
    #done with this
    echo "Finished POST'ing ${file}" && rm -f ${file}
  done
fi


