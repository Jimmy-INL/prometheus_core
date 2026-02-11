"""Example of using environment variables for configuration."""

from storage_client import ConnectionConfig, StorageClient, ItemCreate
from pathlib import Path


def example_default_env():
    """Load configuration from .env file in current directory."""
    print("=== Loading from default .env file ===")

    # This will automatically load from .env if it exists
    config = ConnectionConfig.from_env()

    print(f"Loaded config for org {config.organization_id}, project {config.project_id}")
    print(f"Using API key auth: {config.uses_api_key}")
    print(f"Base URL: {config.base_url}")


def example_specific_env_file():
    """Load configuration from a specific .env file."""
    print("\n=== Loading from specific .env file ===")

    # Load from a specific .env file
    env_path = Path("config") / "production.env"

    # This example shows the pattern - file may not exist
    try:
        config = ConnectionConfig.from_env(env_file=env_path)
        print(f"Loaded from {env_path}")
    except FileNotFoundError:
        print(f".env file not found at {env_path} (this is just an example)")


def example_override_params():
    """Load from environment but override specific parameters."""
    print("\n=== Loading from env with parameter overrides ===")

    # Load from .env but override organization/project IDs
    config = ConnectionConfig.from_env(
        organization_id=999,  # Override the env var
        project_id=888,       # Override the env var
        timeout=60.0          # Custom timeout
    )

    print(f"Config with overrides: org={config.organization_id}, project={config.project_id}")
    print(f"Timeout: {config.timeout}")


def example_client_usage():
    """Use environment-based config with the client."""
    print("\n=== Using env config with client ===")

    try:
        config = ConnectionConfig.from_env()

        with StorageClient(config) as client:
            # Create an item
            item = client.items.create(ItemCreate(
                name="Item created with env config",
                properties={"source": "environment variables"}
            ))

            print(f"✓ Successfully created item {item.id}: {item.name}")

            # Clean up
            client.items.delete(item.id)
            print(f"✓ Cleaned up item {item.id}")

    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nMake sure you have a .env file with the required variables:")
        print("  DEEPLYNX_KEY")
        print("  DEEPLYNX_SECRET")
        print("  DEEPLYNX_ORG_ID")
        print("  DEEPLYNX_PROJECT_ID")
    except Exception as e:
        print(f"Error: {e}")


def example_manual_env_vars():
    """Example showing direct environment variable access."""
    print("\n=== Manual environment variable inspection ===")

    import os

    # Check what's available
    env_vars = {
        "DEEPLYNX_KEY": os.getenv("DEEPLYNX_KEY"),
        "DEEPLYNX_SECRET": os.getenv("DEEPLYNX_SECRET"),
        "DEEPLYNX_ORG_ID": os.getenv("DEEPLYNX_ORG_ID"),
        "DEEPLYNX_PROJECT_ID": os.getenv("DEEPLYNX_PROJECT_ID"),
        "DEEPLYNX_BASE_URL": os.getenv("DEEPLYNX_BASE_URL"),
    }

    print("Environment variables found:")
    for key, value in env_vars.items():
        if value:
            # Mask sensitive values
            if "KEY" in key or "SECRET" in key:
                display = value[:4] + "..." if len(value) > 4 else "***"
            else:
                display = value
            print(f"  {key}: {display}")
        else:
            print(f"  {key}: (not set)")


def main():
    """Run all examples."""
    print("=" * 60)
    print("Environment Variable Configuration Examples")
    print("=" * 60)

    # Show how to use environment variables
    example_default_env()
    example_specific_env_file()
    example_override_params()
    example_manual_env_vars()

    # Try actual client usage if credentials are available
    print("\n" + "=" * 60)
    print("Testing actual client connection")
    print("=" * 60)
    example_client_usage()

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("\nTo use environment variables:")
    print("1. Copy .env.example to .env")
    print("2. Fill in your credentials")
    print("3. Run this script or your own code")
    print("=" * 60)


if __name__ == "__main__":
    main()
