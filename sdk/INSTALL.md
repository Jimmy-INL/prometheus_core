# Installation

There are three supported ways to use `prometheus-api`, in order of preference:

1. **[Container](#container-recommended)** — pull a published image and run it. Easiest path; no Python toolchain required.
2. **[Library](#library)** — install the package into your own Python environment.
3. **[Development checkout](#development)** — clone the repo and use `uv` to work on `prometheus-api` itself.

> Running on INL's HPC and need CA-bundle / podman details? See [docs/hpc.md](docs/hpc.md).

---

## Container (recommended)

Multi-arch images (`linux/amd64`, `linux/arm64`) are published to INL's MooseHarbor registry:

```bash
docker pull mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest
```

You can substitute `latest` with a specific git short-SHA tag (see `make build-push` output, or browse MooseHarbor) for reproducible builds.

Run the image, mounting a `.env` based on `.env.example` so DeepLynx credentials are available:

```bash
docker run -it --rm \
  --env-file .env \
  mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest /bin/bash
```

---

## Library

Install from the git repository into your own venv. Use `pip` or `uv pip`:

```bash
pip install git+https://github.inl.gov/genesis/prometheus_api.git
```

To pin to a specific branch, tag, or commit:

```bash
pip install git+https://github.inl.gov/genesis/prometheus_api.git@<ref>
```

To opt into OpenTelemetry tracing, install the `[tracing]` extra:

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[tracing]"
```

After installing, sanity-check the import:

```bash
python -c "from prometheus_api.storage_client import StorageClient; from prometheus_api.agent import PrometheusAgent; print('ok')"
```

Then copy `.env.example` to `.env` and fill in your DeepLynx credentials (see `README.md` for the variable reference).

---

## Development

The project is `uv`-managed. To work on `prometheus-api` itself:

```bash
git clone https://github.inl.gov/genesis/prometheus_api.git
cd prometheus_api
uv sync
make check    # ruff + mypy
make test     # pytest (unit only; integration tests need .env)
make hooks    # optional: install local pre-commit/pre-push checks
```

`uv sync` creates `.venv/` and installs everything from `uv.lock`, including the `dev` dependency group. Run any tool through `uv run` (e.g., `uv run pytest tests/test_models.py`) or use the Makefile targets.

For architecture, conventions, and the full list of common commands, see [DEVELOPMENT.md](DEVELOPMENT.md).
