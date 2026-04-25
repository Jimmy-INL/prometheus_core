# Running on INL HPC

Notes specific to running `prometheus-api` inside INL's HPC environment, where you need to mount the INL CA bundle and (for git-based installs) work around SSL chain issues.

## Running the container with podman + INL CA bundle

INL HPC nodes provide the INL CA bundle at `/hpc-common/users/certs/inl_bundle.pem`. Mount it into the container and point the standard SSL/CA env vars at it so HTTPS calls to internal services validate.

```bash
CA_BUNDLE_DIR=/hpc-common/users/certs/
CA_BUNDLE=/hpc-common/users/certs/inl_bundle.pem

podman run -it --rm \
  --env CA_BUNDLE="$CA_BUNDLE" \
  --env REQUESTS_CA_BUNDLE="$CA_BUNDLE" \
  --env CURL_CA_BUNDLE="$CA_BUNDLE" \
  --env SSL_CERT_FILE="$CA_BUNDLE" \
  --env NODE_EXTRA_CA_CERTS="$CA_BUNDLE" \
  --volume "$CA_BUNDLE_DIR:$CA_BUNDLE_DIR:ro" \
  --env-file .env \
  mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest /bin/bash
```

Add the `--env-file .env` (or individual `--env` flags) to inject DeepLynx credentials.

## SSL errors when pip-installing from `github.inl.gov`

If `pip install git+https://github.inl.gov/...` fails with SSL errors, your system's CA chain doesn't include INL's intermediate. Either point pip at the bundle:

```bash
REQUESTS_CA_BUNDLE=/hpc-common/users/certs/inl_bundle.pem \
  pip install git+https://github.inl.gov/genesis/prometheus_api.git
```

Or, as a temporary workaround, bypass verification for that host:

```bash
pip install --trusted-host github.inl.gov \
  git+https://github.inl.gov/genesis/prometheus_api.git
```

Prefer the CA-bundle approach in any environment that handles credentials or production data.
