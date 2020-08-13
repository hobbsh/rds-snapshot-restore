.PHONY: build push all

USER_ID := $(shell id -u)
GIT_COMMIT ?=

DOCKER_REGISTRY ?= docker-registry-dev.internal.stuart.com
IMAGE_NAME ?= systems/rds-snapshot-restore

FULL_IMAGE_NAME ?= $(DOCKER_REGISTRY)/$(IMAGE_NAME):latest

all:
	make build
	make push

build:
	docker build -t $(IMAGE_NAME):latest .

push:
	docker tag $(IMAGE_NAME):latest $(FULL_IMAGE_NAME)
	docker push $(FULL_IMAGE_NAME)
