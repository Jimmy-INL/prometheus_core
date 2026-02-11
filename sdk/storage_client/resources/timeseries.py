"""Timeseries resource for synchronous operations."""

from pathlib import Path
from typing import Any, Dict, Optional
from .base import BaseResource


class TimeseriesResource(BaseResource):
    """Handles operations related to timeseries data."""

    def upload(
        self,
        file_path: Path,
        data_source_id: int,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload timeseries data from a file.

        Args:
            file_path: Path to the timeseries data file
            data_source_id: Data source identifier
            description: Optional description

        Returns:
            Upload result information

        Example:
            ```python
            result = client.timeseries.upload(
                Path("sensor_data.csv"),
                data_source_id=456
            )
            ```
        """
        if not file_path.exists():
            raise ValueError(f"File does not exist: {file_path}")

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            data = {}

            if description:
                data["description"] = description

            response = self._client._request(
                "POST",
                f"{self._base_path}/datasources/{data_source_id}/timeseries",
                files=files,
                data=data
            )

        return response.json()

    def query(
        self,
        data_source_id: int,
        sql_query: str,
        file_type: str = "json"
    ) -> Dict[str, Any]:
        """Query timeseries data using SQL.

        Args:
            data_source_id: Data source identifier
            sql_query: SQL query string
            file_type: Output format (json, csv, etc.)

        Returns:
            Query results

        Example:
            ```python
            results = client.timeseries.query(
                data_source_id=456,
                sql_query="SELECT * FROM sensor_data WHERE timestamp > '2024-01-01'",
                file_type="json"
            )
            ```
        """
        payload = {
            "query": sql_query,
            "file_type": file_type,
        }

        response = self._client._request(
            "POST",
            f"{self._base_path}/datasources/{data_source_id}/timeseries/query",
            json=payload
        )

        return response.json()
