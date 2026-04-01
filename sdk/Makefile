UNAME := $(shell uname -s)

##@
##@ Help
##@

.PHONY: help
help: ##@ (Default) Print listing of key targets with their descriptions
	@printf "\nUsage: make <command>\n"
ifeq ($(UNAME), Linux)
	@grep -F -h "##@" $(MAKEFILE_LIST) | grep -F -v grep -F | sed -e 's/\\$$//' | awk 'BEGIN {FS = ":*[[:space:]]*##@[[:space:]]*"}; \
	{ \
			if($$2 == "") \
					pass; \
			else if($$0 ~ /^#/) \
					printf "\n\n%s\n", $$2; \
			else if($$1 == "") \
					printf "     %-20s%s\n", "", $$2; \
			else \
					printf "\n    \033[34m%-20s\033[0m %s", $$1, $$2; \
	}'
	@printf "\n\n"
else ifeq ($(UNAME), Darwin)
	@grep -F -h "##@" $(MAKEFILE_LIST) | grep -F -v grep -F | sed -e 's/\\$$//' | awk 'BEGIN {FS = ":*[[:space:]]*##@[[:space:]]*"}; \
	{ \
			if($$2 == "") \
					next; \
			else if($$0 ~ /^#/) \
					printf "\n\n%s\n", $$2; \
			else if($$1 == "") \
					printf "     %-20s%s\n", "", $$2; \
			else \
					printf "\n    \033[34m%-20s\033[0m %s", $$1, $$2; \
	}'
	@printf "\n\n"
else
	@printf "\nmake help not supported on $(UNAME)\n"
endif

##@
##@ Docker
##@

IMAGE_REPO ?=
IMAGE_TAG ?= $(shell git rev-parse --short HEAD)
PUSH_LATEST ?= true

docker-bp: ##@ Docker build and push (IMAGE_REPO=<repo> [IMAGE_TAG=<tag>] [PUSH_LATEST=true|false])
ifndef IMAGE_REPO
	$(error IMAGE_REPO is required. Example: make docker-bp IMAGE_REPO=ghcr.io/my-org/prometheus-api)
endif
	@echo "Building $(IMAGE_REPO):$(IMAGE_TAG)"
	DOCKER_BUILDKIT=1 docker build -t "$(IMAGE_REPO):$(IMAGE_TAG)" .
	@echo "Pushing $(IMAGE_REPO):$(IMAGE_TAG)"
	docker push "$(IMAGE_REPO):$(IMAGE_TAG)"
ifeq ($(PUSH_LATEST),true)
	@echo "Tagging $(IMAGE_REPO):latest"
	docker tag "$(IMAGE_REPO):$(IMAGE_TAG)" "$(IMAGE_REPO):latest"
	@echo "Pushing $(IMAGE_REPO):latest"
	docker push "$(IMAGE_REPO):latest"
endif
	@echo "Done"

##@
##@ Podman
##@

podman-bp: ##@ Podman build and push to registry
	podman login mooseharbor.hpc.inl.gov
	podman build --platform linux/amd64 -t mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest .
