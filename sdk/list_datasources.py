#!/usr/bin/env python
"""List available data sources for the project."""

from storage_client import ConnectionConfig
import httpx
import json

config = ConnectionConfig.from_env()

print("Getting JWT token...")
with httpx.Client(timeout=10.0) as client:
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

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Try to list data sources (uses /projects endpoint, not /organizations)
    endpoint = f"{config.base_url}/projects/{config.project_id}/datasources"
    print(f"GET {endpoint}")
    print()

    response = client.get(endpoint, headers=headers)

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"\nFound {len(data)} data sources:")
        print(json.dumps(data, indent=2))

        if data:
            print("\n" + "="*70)
            print("Data Source IDs available:")
            for ds in data:
                ds_id = ds.get('id')
                ds_name = ds.get('name', 'Unnamed')
                print(f"  ID: {ds_id} - Name: {ds_name}")
            print("\nAdd one of these to your .env file:")
            print(f"DEEPLYNX_DATA_SOURCE_ID={data[0].get('id')}")
    else:
        print(f"Response: {response.text}")
