# syntax=docker/dockerfile:1

# ---- base (shared) ----
FROM node:22.19.0-bookworm-slim AS base
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=certs ca-bundle.pem /usr/local/share/ca-certificates/ca-bundle.crt
RUN update-ca-certificates

ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt \
    NPM_CONFIG_cafile=/etc/ssl/certs/ca-certificates.crt

# ---- deps ----
FROM base AS deps
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN --mount=type=cache,id=prometheus-npm-cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund --include=optional || \
    npm install --no-audit --no-fund --include=optional

# ---- dev ----
FROM deps AS dev
COPY frontend-react/. .
EXPOSE 5150
ENV HOST=0.0.0.0
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5150"]

# ---- build (prod) ----
FROM deps AS build
COPY frontend-react/. .
RUN npm run build

# ---- prod ----
FROM nginx:alpine AS prod
COPY frontend-react/nginx1.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
