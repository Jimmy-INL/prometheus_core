"""Validate volume mounts and filesystem paths."""


def _get_volumes(svc: dict) -> list[str]:
    """Get volume strings from a service definition."""
    return [str(v) for v in svc.get("volumes", [])]


def test_litellm_config_bind_mount(compose_data):
    volumes = _get_volumes(compose_data["services"]["litellm"])
    assert any("litellm_config.yaml:/app/config.yaml" in v for v in volumes), (
        "litellm service should bind-mount litellm_config.yaml"
    )


def test_litellm_config_file_exists(project_root):
    assert (project_root / "litellm_config.yaml").exists()


def test_shared_dir_exists(project_root):
    assert (project_root / "shared").is_dir()


def test_shared_bind_mount_backend(compose_data):
    volumes = _get_volumes(compose_data["services"]["backend"])
    assert any("./shared:/app/shared" in v for v in volumes), (
        "backend should mount ./shared:/app/shared"
    )


def test_shared_bind_mount_client_agent(compose_data):
    volumes = _get_volumes(compose_data["services"]["client-agent"])
    assert any("./shared:/app/shared" in v for v in volumes), (
        "client-agent should mount ./shared:/app/shared"
    )


def test_named_volumes_declared(compose_data):
    volumes = compose_data.get("volumes", {})
    assert "litellm-db-data" in volumes
    assert "valkey-data" in volumes
    assert "mesh-cache" in volumes


def test_mesh_cache_volume(compose_data):
    """Converted VTP timesteps must survive a backend restart.

    The cache is content-hash keyed, so a container-local /tmp meant every restart
    re-ran the (expensive, VTK-heavy) Exodus conversion for artifacts it had already
    converted. PROMETHEUS_MESH_CACHE_DIR has to agree with the mount point.
    """
    backend = compose_data["services"]["backend"]
    volumes = _get_volumes(backend)
    assert any("mesh-cache:/var/cache/prometheus-mesh" in v for v in volumes)
    assert backend["environment"]["PROMETHEUS_MESH_CACHE_DIR"] == "/var/cache/prometheus-mesh"


def test_postgres_data_volume(compose_data):
    volumes = _get_volumes(compose_data["services"]["litellm-db"])
    assert any("litellm-db-data:/var/lib/postgresql/data" in v for v in volumes)


def test_valkey_data_volume(compose_data):
    volumes = _get_volumes(compose_data["services"]["redis"])
    assert any("valkey-data:/data" in v for v in volumes)
