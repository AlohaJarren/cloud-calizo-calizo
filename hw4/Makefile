# Makefile helpers for HW4
# Usage: make help

PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION ?= us-west1
IMAGE_TAG ?= 1
IMAGE_PATH := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/hw4/hw4:$(IMAGE_TAG)

.PHONY: help
help:
	@echo "Targets:"
	@echo "  run            - run app locally (requires ADC)"
	@echo "  build          - docker build"
	@echo "  docker-run     - run container locally on :8080"
	@echo "  deploy         - build+deploy to Cloud Run 'hw4'"
	@echo "  url            - print deployed URL"
	@echo "  smoke          - quick health + form test against local or remote"

.PHONY: run
run:
	PROJECT_ID=$(PROJECT_ID) DATASTORE_NAMESPACE=cs530-hw4 DATASTORE_KIND=CS530_SongsHW4 SECRET_KEY=dev \
	python hw4/app.py

.PHONY: build
build:
	docker build -f hw4/Dockerfile -t hw4:local .

.PHONY: docker-run
docker-run:
	docker run --rm -p 8080:8080 \
	  -e PROJECT_ID=$(PROJECT_ID) \
	  -e DATASTORE_NAMESPACE=cs530-hw4 \
	  -e DATASTORE_KIND=CS530_SongsHW4 \
	  -e SECRET_KEY=dev \
	  hw4:local

.PHONY: deploy
deploy:
	bash hw4/deploy_cloud_run.sh $(PROJECT_ID) $(REGION)

.PHONY: url
url:
	@cat hw4/url.txt

.PHONY: smoke
smoke:
	bash hw4/smoke_test.sh $(SMOKE_URL)
