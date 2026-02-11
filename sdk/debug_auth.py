#!/usr/bin/env python
"""Debug script to diagnose authentication issues."""

import os
from pathlib import Path
from storage_client import ConnectionConfig
import httpx

def main():
    print("=" * 70)
    print("Authentication Debug")
    print("=" * 70)
    print()

    # Check if .env file exists
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ No .env file found!")
        return 1

    # Load and display configuration (masked)
    print("1. Loading configuration...")
    try:
        config = ConnectionConfig.from_env()
        print("✓ Configuration loaded")
        print(f"  Organization ID: {config.organization_id}")
        print(f"  Project ID: {config.project_id}")
        print(f"  Base URL: {config.base_url}")
        print(f"  Uses API key: {config.uses_api_key}")
        print(f"  Uses JWT: {config.uses_jwt}")

        # Mask sensitive data
        if config.api_key:
            masked_key = config.api_key[:4] + "..." + config.api_key[-4:] if len(config.api_key) > 8 else "***"
            print(f"  API Key: {masked_key} (length: {len(config.api_key)})")
        if config.api_secret:
            masked_secret = config.api_secret[:4] + "..." if len(config.api_secret) > 4 else "***"
            print(f"  API Secret: {masked_secret} (length: {len(config.api_secret)})")
        print()
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return 1

    # Test basic connectivity
    print("2. Testing basic connectivity...")
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(config.base_url)
            print(f"✓ Base URL accessible (status: {response.status_code})")
    except Exception as e:
        print(f"❌ Cannot reach base URL: {e}")
        return 1
    print()

    # Test authentication endpoint
    print("3. Testing authentication...")
    try:
        with httpx.Client(base_url=config.base_url, timeout=10.0) as client:
            # Try to get a token using the API key/secret
            headers = {
                "x-api-key": config.api_key,
                "x-api-secret": config.api_secret,
            }

            print(f"   Sending request to: {config.base_url}/auth/token")
            print(f"   Headers: x-api-key: {config.api_key[:4]}...")
            print()

            response = client.post(
                "/auth/token",
                headers=headers,
                timeout=config.timeout
            )

            print(f"   Response status: {response.status_code}")

            if response.status_code == 200:
                print("   ✓ Authentication successful!")
                data = response.json()
                if "token" in data:
                    token = data["token"]
                    print(f"   ✓ JWT token received (length: {len(token)})")
                    print(f"   Token preview: {token[:20]}...")
                else:
                    print("   ⚠ Response doesn't contain 'token' field")
                    print(f"   Response: {data}")
            elif response.status_code == 401:
                print("   ❌ Authentication failed (401 Unauthorized)")
                print()
                print("   Possible issues:")
                print("   - API key or secret is incorrect")
                print("   - API key/secret doesn't have permission for this org/project")
                print("   - API key might be expired or revoked")
                print()
                print("   Response:")
                try:
                    print(f"   {response.json()}")
                except:
                    print(f"   {response.text}")
                return 1
            else:
                print(f"   ❌ Unexpected status code: {response.status_code}")
                print(f"   Response: {response.text}")
                return 1
    except Exception as e:
        print(f"   ❌ Authentication test failed: {e}")
        return 1
    print()

    # Test accessing a simple endpoint with auth
    print("4. Testing authenticated API access...")
    try:
        with httpx.Client(base_url=config.base_url, timeout=10.0) as client:
            # Get token first
            headers = {
                "x-api-key": config.api_key,
                "x-api-secret": config.api_secret,
            }
            token_response = client.post("/auth/token", headers=headers)

            if token_response.status_code != 200:
                print("   ❌ Cannot get auth token")
                return 1

            token = token_response.json().get("token")

            # Try to list records with the token
            auth_headers = {
                "Authorization": f"Bearer {token}"
            }

            endpoint = f"/organizations/{config.organization_id}/projects/{config.project_id}/records"
            print(f"   Testing endpoint: {endpoint}")
            print(f"   Using Bearer token authentication")
            print()

            list_response = client.get(
                endpoint,
                headers=auth_headers,
                params={"limit": 1}
            )

            print(f"   Response status: {list_response.status_code}")

            if list_response.status_code == 200:
                print("   ✓ Successfully accessed API with authentication!")
                data = list_response.json()
                print(f"   Response contains {len(data.get('records', []))} records")
            elif list_response.status_code == 401:
                print("   ❌ Still unauthorized with JWT token")
                print()
                print("   This might mean:")
                print("   - The API key doesn't have access to this org/project")
                print("   - The organization_id or project_id is incorrect")
                try:
                    print(f"   Response: {list_response.json()}")
                except:
                    print(f"   Response: {list_response.text}")
                return 1
            elif list_response.status_code == 404:
                print("   ❌ Org/Project not found (404)")
                print()
                print("   Please verify:")
                print(f"   - DEEPLYNX_ORG_ID={config.organization_id}")
                print(f"   - DEEPLYNX_PROJECT_ID={config.project_id}")
                return 1
            else:
                print(f"   ❌ Unexpected response: {list_response.status_code}")
                try:
                    print(f"   Response: {list_response.json()}")
                except:
                    print(f"   Response: {list_response.text}")
                return 1

    except Exception as e:
        print(f"   ❌ API access test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    print()

    print("=" * 70)
    print("✅ All authentication checks passed!")
    print("=" * 70)
    print()
    print("Your credentials are working correctly.")
    print("The issue might be elsewhere. Try running test_connection.py again.")
    return 0


if __name__ == "__main__":
    exit(main())
