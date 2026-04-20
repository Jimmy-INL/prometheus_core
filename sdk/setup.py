"""Setup configuration for the storage client library."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="prometheus-api",
    version="0.1.0",
    author="INL Genesis",
    author_email="daniel.schwen@inl.gov",
    description="Storage client and agent utilities for building A2A multi-agent systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.inl.gov/genesis/prometheus_api",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.12",
    install_requires=[
        "httpx>=0.24.0",
        "pydantic>=2.0.0",
        "python-dateutil>=2.8.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "agent": [
            "starlette>=0.27.0",
            "uvicorn[standard]>=0.27.0",
            "httpx>=0.26.0",
            "a2a-sdk[http-server]>=0.3.23,<1",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
        ],
    },
)
