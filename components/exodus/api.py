"""Public API for the Exodus II converter library."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from .cache import compute_dataset_id, get_cache_path, is_cached
from .exceptions import InvalidExodusFileError
from .models import ConvertRequest, ConvertResult
from .vtk_pipeline import create_exodus_reader, extract_metadata, run_conversion


# Shared executor for async wrappers (uses same pool as exodus_integration)
_vtk_executor: ThreadPoolExecutor | None = None


def _get_vtk_executor() -> ThreadPoolExecutor:
    """Get or create the VTK thread pool executor."""
    global _vtk_executor
    if _vtk_executor is None:
        _vtk_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vtk-api-")
    return _vtk_executor


def inspect_exodus(input_path: Path) -> dict:
    """
    Inspect an Exodus II file and return metadata.

    Args:
        input_path: Path to the Exodus II file.

    Returns:
        Dictionary containing file metadata including timesteps,
        variables, element blocks, bounds, and counts.

    Raises:
        InvalidExodusFileError: If the file cannot be read.
    """
    if isinstance(input_path, str):
        input_path = Path(input_path)

    if not input_path.exists():
        raise InvalidExodusFileError(f"File not found: {input_path}")

    try:
        reader = create_exodus_reader(input_path)
        metadata = extract_metadata(reader)
        return metadata.to_dict()
    except Exception as e:
        raise InvalidExodusFileError(f"Failed to read Exodus file: {e}") from e


def convert_exodus(
    request: ConvertRequest,
    cache_root: Path | None = None,
) -> ConvertResult:
    """
    Convert an Exodus II file to web-friendly VTP format.

    Args:
        request: Conversion request parameters.
        cache_root: Optional root directory for caching. If provided,
            converted datasets will be cached and reused.

    Returns:
        ConvertResult with dataset ID, output paths, and metadata.

    Raises:
        InvalidExodusFileError: If the input file is invalid.
        ConversionError: If conversion fails.
    """
    # Compute dataset ID for caching
    request_dict = asdict(request)
    dataset_id = compute_dataset_id(request.input_path, request_dict)

    # Determine output directory
    if cache_root:
        output_dir = get_cache_path(cache_root, dataset_id)

        # Check if already cached
        if is_cached(cache_root, dataset_id):
            manifest_path = output_dir / "manifest.json"
            meta_path = output_dir / "meta.json"

            import json

            with open(meta_path) as f:
                metadata = json.load(f)

            return ConvertResult(
                dataset_id=dataset_id,
                output_dir=output_dir,
                manifest_path=manifest_path,
                metadata=metadata,
            )
    else:
        output_dir = request.output_dir

    # Update request with resolved output directory
    request.output_dir = output_dir

    # Run conversion
    run_conversion(request)

    # Load full metadata
    import json

    meta_path = output_dir / "meta.json"
    with open(meta_path) as f:
        metadata = json.load(f)

    return ConvertResult(
        dataset_id=dataset_id,
        output_dir=output_dir,
        manifest_path=output_dir / "manifest.json",
        metadata=metadata,
    )


async def inspect_exodus_async(input_path: Path) -> dict:
    """
    Async wrapper for inspect_exodus.

    Runs VTK inspection in a thread pool to avoid blocking the event loop.

    Args:
        input_path: Path to the Exodus II file.

    Returns:
        Dictionary containing file metadata.

    Raises:
        InvalidExodusFileError: If the file cannot be read.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_vtk_executor(), lambda: inspect_exodus(input_path))


async def convert_exodus_async(
    request: ConvertRequest,
    cache_root: Path | None = None,
) -> ConvertResult:
    """
    Async wrapper for convert_exodus.

    Runs VTK conversion in a thread pool to avoid blocking the event loop.
    This is important for large files that may take significant time to process.

    Args:
        request: Conversion request parameters.
        cache_root: Optional root directory for caching.

    Returns:
        ConvertResult with dataset ID, output paths, and metadata.

    Raises:
        InvalidExodusFileError: If the input file is invalid.
        ConversionError: If conversion fails.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_vtk_executor(), lambda: convert_exodus(request, cache_root=cache_root))
