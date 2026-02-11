#!/usr/bin/env python
"""Test direct API key authentication without token exchange."""

from pathlib import Path
from storage_client import ConnectionConfig
import httpx

def main():
    print("=" * 70)
    print("Testing Direct API Key Authentication")
    print("=" * 70)
    print()

    # Load config
    config = ConnectionConfig.from_env()
    print(f"Organization: {config.organization_id}")
    print(f"Project: {config.project_id}")
    print()

    # Test 1: Try with API key/secret directly in headers
    print("Test 1: Using x-api-key and x-api-secret headers directly")
    print("-" * 70)

    headers = {
        "x-api-key": config.api_key,
        "x-api-secret": config.api_secret,
    }

    endpoint = f"/organizations/{config.organization_id}/projects/{config.project_id}/records"
    url = f"{config.base_url}{endpoint}"

    print(f"URL: {url}")
    print(f"Headers: x-api-key: {config.api_key[:10]}...")
    print(f"         x-api-secret: {config.api_secret[:10]}...")
    print()

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers, params={"limit": 1})

            print(f"Response status: {response.status_code}")

            if response.status_code == 200:
                print("✅ SUCCESS! API key/secret works directly!")
                print()
                print("This means we should NOT be exchanging for JWT tokens.")
                print("The client library needs to be updated to use API keys directly.")
                return 0
            else:
                print(f"Response: {response.text[:500]}")

    except Exception as e:
        print(f"Error: {e}")

    print()

    # Test 2: Try different auth formats
    print("Test 2: Trying alternative header formats")
    print("-" * 70)

    test_formats = [
        {"Authorization": f"ApiKey {config.api_key}:{config.api_secret}"},
        {"api_key": config.api_key, "api_secret": config.api_secret},
        {"X-API-Key": config.api_key, "X-API-Secret": config.api_secret},
    ]

    for i, test_headers in enumerate(test_formats, 1):
        print(f"Format {i}: {list(test_headers.keys())}")
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=test_headers, params={"limit": 1})
                print(f"  Status: {response.status_code}")

                if response.status_code == 200:
                    print(f"  ✅ This format works!")
                    return 0

        except Exception as e:
            print(f"  Error: {e}")

    print()
    print("=" * 70)
    return 1


if __name__ == "__main__":
    exit(main())
