#!/usr/bin/env python
"""Test the OAuth token endpoint directly."""

from storage_client import ConnectionConfig
import httpx

config = ConnectionConfig.from_env()

print("Testing OAuth token endpoint...")
print(f"URL: {config.base_url}/oauth/tokens")
print()

payload = {
    "apiKey": config.api_key,
    "apiSecret": config.api_secret,
    "expirationMinutes": None
}

print(f"Payload keys: {list(payload.keys())}")
print()

with httpx.Client(timeout=10.0) as client:
    response = client.post(
        f"{config.base_url}/oauth/tokens",
        json=payload,
        headers={"Content-Type": "application/json"}
    )

    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print()
    print(f"Response text: {response.text}")
    print()

    if response.status_code == 200:
        try:
            data = response.json()
            print(f"JSON data: {data}")
            if "token" in data:
                token = data["token"]
                print(f"Token length: {len(token)}")
                print(f"Token preview: {token[:50]}...")
        except Exception as e:
            print(f"Error parsing JSON: {e}")
