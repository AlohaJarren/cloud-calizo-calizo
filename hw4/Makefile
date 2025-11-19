# Makefile helpers for HW4
# Usage: make help

PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION ?= us-west1

.PHONY: help
help:
	@echo "run           - run locally (ADC required)"
	@echo "deploy        - build+deploy to Cloud Run"
	@echo "url           - print deployed URL"
	@echo "smoke         - smoke test against URL"

.PHONY: run
run:
	PROJECT_ID=$(PROJECT_ID) DATASTORE_NAMESPACE=cs530-hw4 DATASTORE_KIND=CS530_SongsHW4 SECRET_KEY=dev \
	python hw4/app.py

.PHONY: deploy
deploy:
	bash hw4/deploy_cloud_run.sh $(PROJECT_ID) $(REGION)

.PHONY: url
url:
	@cat hw4/url.txt

.PHONY: smoke
smoke:
	bash hw4/smoke_test.sh $$(cat hw4/url.txt)
