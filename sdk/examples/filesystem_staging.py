"""Example: publish and stage files with DeepLynx fsspec put/get hooks."""

from pathlib import Path
import tempfile

from fsspec import filesystem
from prometheus_api.storage_client import ConnectionConfig


def main():
    """Publish local data to deeplynx:// and stage it back locally."""
    config = ConnectionConfig.from_env()
    fs = filesystem("deeplynx", config=config)

    # Create a temporary local source file to publish.
    source_dir = Path(tempfile.gettempdir()) / "deeplynx-fsspec-example"
    source_dir.mkdir(parents=True, exist_ok=True)
    local_source = source_dir / "payload.txt"
    local_source.write_text("staging and publishing payload", encoding="utf-8")

    remote_path = "deeplynx://exchange/entity-a/payload.txt"
    local_staged = source_dir / "payload-staged.txt"

    # Publish: local -> deeplynx://
    fs.put(str(local_source), remote_path)
    print(f"Published to {remote_path}")

    # Stage: deeplynx:// -> local
    fs.get(remote_path, str(local_staged))
    print(f"Staged to {local_staged}")

    print(f"Staged content: {local_staged.read_text(encoding='utf-8')}")


if __name__ == "__main__":
    main()
