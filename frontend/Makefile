##@
##@ Frontend React
##@

.PHONY: dev build lint typecheck check install

dev: ##@ Start Vite dev server
	npm run dev -- --port 5150

build: ##@ Build for production
	npm run build

lint: ##@ Run eslint
	npm run lint

typecheck: ##@ Run TypeScript type checker
	npm run typecheck

check: ##@ Run all checks (lint + typecheck)
check: lint typecheck

install: ##@ Install dependencies
	npm install
	