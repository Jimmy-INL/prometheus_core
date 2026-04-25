"""Pagination utility functions."""

from typing import Iterator, List, TypeVar, Callable

T = TypeVar("T")


def paginate_iterator(
    fetch_page: Callable[[int, int], List[T]], page_size: int = 100, start_page: int = 1
) -> Iterator[T]:
    """Helper to iterate over paginated results.

    Args:
        fetch_page: Function that takes (page, page_size) and returns list of items
        page_size: Number of items per page
        start_page: Starting page number

    Yields:
        Individual items from all pages

    Example:
        ```python
        def fetch(page, size):
            return client.items.list(page=page, page_size=size).items

        for item in paginate_iterator(fetch, page_size=50):
            print(item.name)
        ```
    """
    page = start_page
    while True:
        items = fetch_page(page, page_size)
        if not items:
            break

        yield from items

        if len(items) < page_size:
            break

        page += 1
