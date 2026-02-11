#!/usr/bin/env python
"""Verify .env file loading works - requires actual .env file with credentials."""

from pathlib import Path
from storage_client import ConnectionConfig

print("=" * 70)
print("Environment Variable Configuration Verification")
print("=" * 70)

# Check if .env file exists
env_file = Path(".env")

if not env_file.exists():
    print()
    print("❌ No .env file found!")
    print()
    print("To use environment variable configuration:")
    print()
    print("1. Copy the template:")
    print("   $ cp .env.example .env")
    print()
    print("2. Edit .env with your actual credentials:")
    print("   $ vim .env")
    print()
    print("3. Add these required variables:")
    print("   DEEPLYNX_KEY=<your-api-key>")
    print("   DEEPLYNX_SECRET=<your-api-secret>")
    print("   DEEPLYNX_ORG_ID=<your-org-id>")
    print("   DEEPLYNX_PROJECT_ID=<your-project-id>")
    print()
    print("4. Run this script again to verify")
    print()
    print("=" * 70)
    exit(1)

try:
    # Load configuration from .env file
    config = ConnectionConfig.from_env()

    print()
    print("✅ Successfully loaded configuration from .env file!")
    print()
    print(f"   Organization ID: {config.organization_id}")
    print(f"   Project ID: {config.project_id}")
    print(f"   Uses API key auth: {config.uses_api_key}")
    print(f"   Base URL: {config.base_url}")
    print()
    print("You can now use this in your code:")
    print()
    print("   from storage_client import ConnectionConfig, StorageClient")
    print()
    print("   config = ConnectionConfig.from_env()")
    print("   with StorageClient(config) as client:")
    print("       items = client.items.list()")
    print()

except ValueError as e:
    print()
    print(f"❌ Configuration error: {e}")
    print()
    print("Make sure your .env file contains all required variables:")
    print("   DEEPLYNX_KEY")
    print("   DEEPLYNX_SECRET")
    print("   DEEPLYNX_ORG_ID")
    print("   DEEPLYNX_PROJECT_ID")
    print()

except Exception as e:
    print()
    print(f"❌ Unexpected error: {e}")
    print()

print("=" * 70)
