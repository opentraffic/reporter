#!/usr/bin/env bash
set -e

usage() {
  echo "Usage: $0 [prod|dev] [us-east-1]"
  exit 2
}

if [ -z $2 ]; then
  usage
else
  case $1 in
    'prod'|'dev')
      ENV=$1
      ;;
    *)
      usage
      ;;
  esac

  case $2 in
    'us-east-1')
      REGION=$2
      ;;
    *)
      usage
      ;;
  esac
fi

# more bash-friendly output for jq
JQ="jq --raw-output --exit-status"

configure_aws_cli(){
  aws --version
  aws configure set default.region $REGION
  aws configure set default.output json
}

deploy_cluster() {
  family="opentraffic-reporter-$ENV"

  make_task_def
  make_volume_def
  register_definition

  if [[ $(aws ecs update-service --cluster reporter-$ENV --service opentraffic-reporter-$ENV --task-definition $revision | $JQ '.service.taskDefinition') != $revision ]]; then
    echo "Error updating service."
    return 1
  fi

  # wait for older revisions to disappear
  # not really necessary, but nice for demos
  for attempt in {1..60}; do
    if stale=$(aws ecs describe-services --cluster reporter-$ENV --services opentraffic-reporter-$ENV | \
              $JQ ".services[0].deployments | .[] | select(.taskDefinition != \"$revision\") | .taskDefinition"); then
      echo "Waiting for stale deployments:"
      echo "$stale"
      sleep 10
    else
      echo "Deployed!"
      return 0
    fi
  done

  echo "Service update took too long."
  return 1
}

make_task_def(){
  task_template='[
    {
      "name": "opentraffic-reporter-%s",
      "image": "%s.dkr.ecr.%s.amazonaws.com/opentraffic/reporter-%s:%s",
      "essential": true,
      "memoryReservation": 512,
      "cpu": 512,
      "logConfiguration": {
        "logDriver": "awslogs",
          "options": {
          "awslogs-group": "reporter-%s",
          "awslogs-region": "%s"
        }
      },
      "environment": [
        {
          "name": "REDIS_HOST",
          "value": "%s"
        },
        {
          "name": "DATASTORE_URL",
          "value": "%s"
        }
      ],
      "portMappings": [
        {
          "containerPort": 8002,
          "hostPort": 0
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "data",
          "containerPath": "/data/valhalla",
          "readOnly": false
        }
      ]
    }
  ]'

  # figure out vars per env
  redis_host_raw=$(echo $`printf $ENV`_REDIS_HOST)
  redis_host=$(eval echo $redis_host_raw)

  datastore_url_raw=$(echo $`printf $ENV`_DATASTORE_URL)
  datastore_url=$(eval echo $datastore_url_raw)

  task_def=$(printf "$task_template" $ENV $AWS_ACCOUNT_ID $REGION $ENV $CIRCLE_SHA1 $ENV $REGION $redis_host $datastore_url)
}

make_volume_def(){
  volume_template='[
    {
      "name": "data",
      "host": {
        "sourcePath": "/data/valhalla"
      }
    }
  ]'
  volume_def=$(printf "$volume_template")
}

push_ecr_image(){
  eval $(aws ecr get-login --region $REGION)
  docker tag reporter:latest $AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/opentraffic/reporter-$ENV:$CIRCLE_SHA1
  docker push $AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/opentraffic/reporter-$ENV:$CIRCLE_SHA1
}

register_definition() {
  if revision=$(aws ecs register-task-definition --volumes "$volume_template" --container-definitions "$task_def" --family $family | $JQ '.taskDefinition.taskDefinitionArn'); then
    echo "Revision: $revision"
  else
    echo "Failed to register task definition"
    return 1
  fi
}

configure_aws_cli
push_ecr_image
deploy_cluster
