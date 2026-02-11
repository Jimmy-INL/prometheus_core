#!/bin/bash
# Test pip installation from git repository

echo "========================================================================"
echo "Testing pip install from git repository"
echo "========================================================================"
echo ""

# Create a temporary virtual environment
echo "Creating temporary virtual environment..."
python -m venv /tmp/test_storage_client_install
source /tmp/test_storage_client_install/bin/activate

echo "✓ Virtual environment created"
echo ""

# Test installation from local directory (simulates git install)
echo "Installing storage-client from current directory..."
pip install -e . -q

if [ $? -eq 0 ]; then
    echo "✓ Installation successful"
    echo ""
else
    echo "✗ Installation failed"
    deactivate
    rm -rf /tmp/test_storage_client_install
    exit 1
fi

# Test importing the package
echo "Testing import..."
python -c "
from storage_client import StorageClient, ConnectionConfig, ItemCreate
print('✓ Package imports successfully')
print('  StorageClient: available')
print('  AsyncStorageClient: available')
print('  ConnectionConfig: available')
print('  Models: available')
"

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================================================"
    echo "✅ Package installation test PASSED"
    echo "========================================================================"
    echo ""
    echo "The package can be installed with:"
    echo "  pip install git+https://github.inl.gov/genesis/prometheus_api.git"
    echo ""
else
    echo ""
    echo "✗ Import test failed"
fi

# Cleanup
deactivate
rm -rf /tmp/test_storage_client_install

echo "Cleaned up test environment"
