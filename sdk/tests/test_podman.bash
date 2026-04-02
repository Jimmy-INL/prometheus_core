CA_BUNDLE_DIR=/hpc-common/users/certs/
CA_BUNDLE=/hpc-common/users/certs/inl_bundle.pem
podman run -it --rm \
  --env CA_BUNDLE="$CA_BUNDLE" \
  --env REQUESTS_CA_BUNDLE="$CA_BUNDLE" \
  --env CURL_CA_BUNDLE="$CA_BUNDLE" \
  --env SSL_CERT_FILE="$CA_BUNDLE" \
  --env NODE_EXTRA_CA_CERTS="$CA_BUNDLE" \
  --volume "$CA_BUNDLE_DIR:$CA_BUNDLE_DIR:ro" \
  mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api:py312 /bin/bash
