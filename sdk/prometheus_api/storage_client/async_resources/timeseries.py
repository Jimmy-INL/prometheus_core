"""Async timeseries resource."""

from pathlib import Path
from typing import Any, Dict, Optional
from .base import AsyncBaseResource


class AsyncTimeseriesResource(AsyncBaseResource):
    """Handles async operations related to timeseries data."""

    async def upload(
        self, file_path: Path, data_source_id: int, description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload timeseries data from a file asynchronously."""
        if not file_path.exists():
            raise ValueError(f"File does not exist: {file_path}")

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            data = {}

            if description:
                data["description"] = description

            response = await self._client._request(
                "POST",
                f"{self._base_path}/datasources/{data_source_id}/timeseries",
                files=files,
                data=data,
            )

        data = response.json()
        return data if isinstance(data, dict) else {"result": data}

    async def query(
        self, data_source_id: int, sql_query: str, file_type: str = "json"
    ) -> Dict[str, Any]:
        """Query timeseries data using SQL asynchronously."""
        payload = {
            "query": sql_query,
            "file_type": file_type,
        }

        response = await self._client._request(
            "POST", f"{self._base_path}/datasources/{data_source_id}/timeseries/query", json=payload
        )

        data = response.json()
        return data if isinstance(data, dict) else {"result": data}
