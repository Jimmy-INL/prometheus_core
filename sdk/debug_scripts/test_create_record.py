#!/usr/bin/env python
"""Test creating a record directly to see what format works."""

from storage_client import ConnectionConfig
import httpx
import json

config = ConnectionConfig.from_env()

print("Getting JWT token...")
with httpx.Client(timeout=10.0) as client:
    # Get token
    token_response = client.post(
        f"{config.base_url}/oauth/tokens",
        json={
            "apiKey": config.api_key,
            "apiSecret": config.api_secret,
            "expirationMinutes": None
        },
        headers={"Content-Type": "application/json"}
    )

    token = token_response.text.strip()
    print(f"✓ Got token (length: {len(token)})")
    print()

    # Try creating a record
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    endpoint = f"{config.base_url}/organizations/{config.organization_id}/projects/{config.project_id}/records"
    print(f"POST {endpoint}")
    print()

    # Try minimal payload first
    payloads_to_try = [
        {
            "name": "Test Record",
            "description": "Test description",
            "properties": {"test": True}
        },
        {
            "name": "Test Record",
            "properties": {"test": True}
        },
        {
            "name": "Test Record"
        },
    ]

    for i, payload in enumerate(payloads_to_try, 1):
        print(f"Attempt {i}: {json.dumps(payload, indent=2)}")
        response = client.post(endpoint, json=payload, headers=headers)

        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
        print()

        if response.status_code == 200 or response.status_code == 201:
            print("✅ Success!")
            print(f"Full response: {json.dumps(response.json(), indent=2)}")
            break
