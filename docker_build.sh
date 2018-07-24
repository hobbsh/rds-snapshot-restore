#!/bin/bash
#
# Build the docker image

APP="rds-snapshot-restore"
REPO="wylie"
GIT_SHA=$(git rev-parse --short HEAD)
NEW_IMAGE="$REPO/$APP:$GIT_SHA"

docker build -t $APP .

if [ $? -eq 0 ];
  IMAGE_ID=$(docker images | grep -E ^$APP | awk '{print $3}')

  docker tag $IMAGE_ID $NEW_IMAGE
  docker push $NEW_IMAGE
else
  echo "Someting went wrong building the image. Exiting"
  exit 1
fi
