#!/usr/bin/env python
"""Test different API base paths."""

from pathlib import Path
from storage_client import ConnectionConfig
import httpx

def main():
    print("=" * 70)
    print("Testing Different API Paths")
    print("=" * 70)
    print()

    config = ConnectionConfig.from_env()

    headers = {
        "x-api-key": config.api_key,
        "x-api-secret": config.api_secret,
    }

    base_urls = [
        "https://deeplynx.inl.gov/api/v1",
        "https://deeplynx.inl.gov/api",
        "https://deeplynx.inl.gov",
    ]

    endpoints = [
        f"/organizations/{config.organization_id}/projects/{config.project_id}/records",
        f"/projects/{config.project_id}/records",
        f"/api/organizations/{config.organization_id}/projects/{config.project_id}/records",
    ]

    print(f"Testing with org={config.organization_id}, project={config.project_id}")
    print()

    for base_url in base_urls:
        print(f"Base URL: {base_url}")
        print("-" * 70)

        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            # Skip obviously wrong combinations
            if "/api/api" in url:
                continue

            print(f"  Trying: {url}")

            try:
                with httpx.Client(timeout=5.0) as client:
                    response = client.get(
                        url,
                        headers=headers,
                        params={"limit": 1}
                    )

                    print(f"    Status: {response.status_code}")

                    if response.status_code == 200:
                        print(f"    ✅ SUCCESS!")
                        print()
                        print(f"Correct path: {url}")
                        return 0
                    elif response.status_code != 404:
                        # Not 404 means the endpoint exists but auth might be wrong
                        try:
                            print(f"    Response: {response.json()}")
                        except:
                            print(f"    Response: {response.text[:100]}")

            except Exception as e:
                print(f"    Error: {e}")

        print()

    print("=" * 70)
    print("No working path found.")
    print()
    print("Please check:")
    print("1. Are your API credentials correct and active?")
    print("2. Does your API key have access to org 1, project 32?")
    print("3. Try generating new API credentials in DeepLynx")
    return 1


if __name__ == "__main__":
    exit(main())
