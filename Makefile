.PHONY: build push all

USER_ID := $(shell id -u)
GIT_COMMIT ?=

DOCKER_REGISTRY ?= docker-registry-dev.internal.stuart.com
IMAGE_NAME ?= systems/rds-snapshot-restore

FULL_IMAGE_NAME ?= $(DOCKER_REGISTRY)/$(IMAGE_NAME):latest
FULL_IMAGE_NAME_TEST ?= $(DOCKER_REGISTRY)/$(IMAGE_NAME):test

all: build push

test: build_test push_test

build:
	docker build -t $(IMAGE_NAME):latest .

push:
	docker tag $(IMAGE_NAME):latest $(FULL_IMAGE_NAME)
	docker push $(FULL_IMAGE_NAME)

build_test:
	docker build -t $(IMAGE_NAME):test .

push_test:
	docker tag $(IMAGE_NAME):test $(FULL_IMAGE_NAME_TEST)
	docker push $(FULL_IMAGE_NAME_TEST)
