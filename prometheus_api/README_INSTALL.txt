QUICK INSTALLATION GUIDE
========================

Install from GitHub:

    pip install git+https://github.inl.gov/genesis/prometheus_api.git

Or clone and install in development mode:

    git clone https://github.inl.gov/genesis/prometheus_api.git
    cd prometheus_api
    pip install -e .

Setup credentials:

    cp .env.example .env
    vim .env  # Add your DeepLynx credentials

Verify installation:

    python test_connection.py

See INSTALL.md for detailed installation options.
