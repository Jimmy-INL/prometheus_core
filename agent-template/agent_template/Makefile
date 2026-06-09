COMPOSE := docker compose
UNAME   := $(shell uname)

COMPOSE_BASE := docker-compose.yml

# On Linux, layer in docker-compose.linux.yml if you have created one (e.g. to
# add `extra_hosts: host.docker.internal:host-gateway`). It is optional — the
# wildcard means we only pass -f for it when the file actually exists.
ifeq ($(UNAME), Linux)
COMPOSE_FILES := -f $(COMPOSE_BASE) $(if $(wildcard docker-compose.linux.yml),-f docker-compose.linux.yml,)
else
COMPOSE_FILES := -f $(COMPOSE_BASE)
endif

.PHONY: help up up-fg down logs

help: ##@ (Default) Print listing of key targets with their descriptions
	@printf "\nUsage: make <command>\n"
	@grep -F -h "##@" $(MAKEFILE_LIST) | grep -Fv grep | grep -Fv 'FS =' | sed 's/\\$$//' | \
	awk 'BEGIN {FS = ":*[[:space:]]*##@[[:space:]]*"}; \
	{ \
		if ($$2 == "") next; \
		else if ($$0 ~ /^#/) printf "\n\n%s\n", $$2; \
		else if ($$1 == "") printf "     %-20s%s\n", "", $$2; \
		else printf "\n    \033[34m%-20s\033[0m %s", $$1, $$2; \
	}'
	@printf "\n\n"

##@
##@ Compose
##@

up: ##@ Build and start the agent (detached)
	$(COMPOSE) $(COMPOSE_FILES) up --build -d

up-fg: ##@ Build and start the agent (foreground)
	$(COMPOSE) $(COMPOSE_FILES) up --build

down: ##@ Stop and remove the agent
	$(COMPOSE) $(COMPOSE_FILES) down

logs: ##@ Tail agent logs (SERVICE=name for one service)
	$(COMPOSE) $(COMPOSE_FILES) logs -f $(SERVICE)
