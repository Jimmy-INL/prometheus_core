import requests
from typing import Optional
from pathlib import Path

BASE_URL = "https://deeplynx.inl.gov/api/v1"
API_KEY = "api_key"
API_SECRET = "secret"

ORGANIZATION_ID = 1
PROJECT_ID = 54


def get_token() -> str:
    url = f"{BASE_URL}/oauth/tokens"

    payload = {
        "apiKey": API_KEY,
        "apiSecret": API_SECRET
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    return response.text

def upload_file_to_deeplynx(
    file_path: str,
    metadata_path: Optional[str] = None,
    data_source_id: Optional[int] = None,
    object_storage_id: Optional[int] = None,
    sensitivity_label_ids: Optional[list[int]] = None
) -> dict:
    """
    Uploads a file to DeepLynx and returns the API response.
    """

    token = get_token()

    url = f"{BASE_URL}/organizations/{ORGANIZATION_ID}/projects/{PROJECT_ID}/files"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    params = {}
    if data_source_id:
        params["dataSourceId"] = data_source_id
    if object_storage_id:
        params["objectStorageId"] = object_storage_id
    if sensitivity_label_ids:
        params["sensitivityLabelIds"] = sensitivity_label_ids

    with open(file_path, "rb") as file_obj:
        files = {"file": file_obj}

        if metadata_path:
            with open(metadata_path, "rb") as metadata_obj:
                files["metadata"] = metadata_obj
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    files=files
                )
        else:
            response = requests.post(
                url,
                headers=headers,
                params=params,
                files=files
            )

    response.raise_for_status()
    return response.json()

def download_file_from_deeplynx(
    record_id: int,
    save_path: Optional[str] = None
) -> dict:
    """
    Downloads a file from DeepLynx.

    Args:
        record_id: The record ID that contains file information.
        save_path: Optional path to save the file. If None, filename
                   will be inferred from headers.

    Returns:
        Dictionary containing file path and metadata.
    """

    token = get_token()

    url = (
        f"{BASE_URL}/organizations/{ORGANIZATION_ID}"
        f"/projects/{PROJECT_ID}/files/{record_id}"
    )

    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()

    # Try to determine filename from headers
    content_disposition = response.headers.get("Content-Disposition")

    if not save_path:
        if content_disposition and "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[-1].strip('"')
        else:
            filename = f"deeplynx_file_{record_id}"

        save_path = filename

    save_path = Path(save_path)

    # Stream download to file
    with open(save_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return {
        "status": "success",
        "file_path": str(save_path.resolve()),
        "content_type": response.headers.get("Content-Type"),
        "content_length": response.headers.get("Content-Length")
    }