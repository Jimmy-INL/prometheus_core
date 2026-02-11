# Debug Scripts

These scripts were used during development to debug DeepLynx API integration issues.
They are kept for historical reference but are not needed for normal use.

## Scripts

- `debug_auth.py` - Debug authentication flow step-by-step
- `test_api_paths.py` - Test different API endpoint path variations
- `test_create_record.py` - Test record creation payload formats
- `test_direct_auth.py` - Test various authentication header formats
- `test_env_example.py` - Test environment variable loading
- `test_oauth_token.py` - Test OAuth token endpoint directly

## When These Were Useful

During development, we encountered:
1. ❌ Wrong OAuth endpoint (`/auth/token` vs `/oauth/tokens`)
2. ❌ Wrong field names (PascalCase vs snake_case)
3. ❌ JWT token format (JSON vs plain text)
4. ❌ Missing required fields
5. ❌ Data source ID not being sent

These scripts helped diagnose each issue.

## Current Debugging Tools

For current debugging, use the main utilities:

```bash
# Test connection
python ../test_connection.py

# List data sources
python ../list_datasources.py

# Verify installation
python ../verify_installation.py

# Run test suite
pytest ../tests/test_integration.py -v
```

## Note

These debug scripts may be outdated as the API has been fixed.
The real test suite is in `../tests/test_integration.py`.
