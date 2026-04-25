"""Regression tests that keep sync and async resource behavior aligned."""

from __future__ import annotations

from types import SimpleNamespace

from prometheus_api.storage_client.async_resources.items import AsyncItemsResource
from prometheus_api.storage_client.async_resources.search import AsyncSearchResource
from prometheus_api.storage_client.models.item import ItemCreate, ItemUpdate
from prometheus_api.storage_client.resources.items import ItemsResource
from prometheus_api.storage_client.resources.search import SearchResource


class Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class SyncClient:
    def __init__(self, payload):
        self.config = SimpleNamespace(organization_id=1, project_id=2)
        self.calls = []
        self._payload = payload

    def _get_data_source_id(self):
        return 7

    def _request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return Response(self._payload)


class AsyncClient(SyncClient):
    async def _get_data_source_id(self):
        return 7

    async def _request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return Response(self._payload)


def item_payload(**overrides):
    payload = {
        "id": 123,
        "name": "Sample",
        "description": "A sample item",
        "properties": {"kind": "test"},
        "classId": 9,
        "originalId": "orig-1",
        "lastUpdatedAt": "2026-04-25T12:00:00Z",
        "tags": [],
        "dataSourceId": 7,
    }
    payload.update(overrides)
    return payload


async def test_item_create_payloads_match_between_sync_and_async():
    sync_client = SyncClient(item_payload())
    async_client = AsyncClient(item_payload())

    item = ItemCreate(
        name="Sample",
        description="A sample item",
        properties={"kind": "test"},
        class_id=9,
        original_id="orig-1",
    )

    ItemsResource(sync_client).create(item)
    await AsyncItemsResource(async_client).create(item)

    assert sync_client.calls == async_client.calls
    method, path, kwargs = sync_client.calls[0]
    assert method == "POST"
    assert path == "/organizations/1/projects/2/records"
    assert kwargs["json"] == {
        "name": "Sample",
        "description": "A sample item",
        "properties": {"kind": "test"},
        "original_id": "orig-1",
        "class_id": 9,
    }
    assert kwargs["params"] == {"dataSourceId": 7}


async def test_item_update_payloads_match_between_sync_and_async():
    sync_client = SyncClient(item_payload(name="Updated"))
    async_client = AsyncClient(item_payload(name="Updated"))

    update = ItemUpdate(
        name="Updated",
        description="Updated description",
        properties={"kind": "updated"},
        class_id=10,
        original_id="orig-2",
    )

    ItemsResource(sync_client).update(123, update)
    await AsyncItemsResource(async_client).update(123, update)

    assert sync_client.calls == async_client.calls
    assert sync_client.calls[0] == (
        "PUT",
        "/organizations/1/projects/2/records/123",
        {
            "json": {
                "name": "Updated",
                "description": "Updated description",
                "properties": {"kind": "updated"},
                "class_id": 10,
                "original_id": "orig-2",
            }
        },
    )


async def test_search_query_payloads_and_parsing_match_between_sync_and_async():
    response_payload = [
        item_payload(
            properties='{"kind": "search"}',
            tags='[{"id": 4, "name": "indexed"}]',
        )
    ]
    sync_client = SyncClient(response_payload)
    async_client = AsyncClient(response_payload)

    sync_result = SearchResource(sync_client).query("sample")
    async_result = await AsyncSearchResource(async_client).query("sample")

    assert sync_client.calls == async_client.calls
    assert sync_client.calls[0] == (
        "GET",
        "/organizations/1/query/records",
        {"params": {"userQuery": "sample", "projectIds": [2]}},
    )
    assert sync_result.items[0] == async_result.items[0]
    assert async_result.items[0].properties == {"kind": "search"}
    assert async_result.items[0].tags[0].name == "indexed"
