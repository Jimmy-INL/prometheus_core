#!/bin/bash
# Run integration tests for storage client

echo "========================================================================"
echo "Running Storage Client Integration Tests"
echo "========================================================================"
echo ""
echo "These tests require:"
echo "  - A .env file with valid credentials"
echo "  - Connection to DeepLynx database"
echo "  - Test items will be created and cleaned up"
echo ""
echo "Press Ctrl+C to cancel or wait 3 seconds to continue..."
sleep 3

echo ""
echo "Running tests..."
echo ""

# Run only integration tests
pytest tests/test_integration.py -v --tb=short -m integration

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "========================================================================"
    echo "✅ All integration tests passed!"
    echo "========================================================================"
else
    echo "========================================================================"
    echo "❌ Some integration tests failed"
    echo "========================================================================"
fi

exit $exit_code
