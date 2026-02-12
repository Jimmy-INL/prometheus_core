"""VTK-based pipeline for reading and converting Exodus II files."""

import json
from pathlib import Path

import vtk

from .exceptions import ConversionError, InvalidExodusFileError
from .models import ConvertRequest, ExodusMetadata


def create_exodus_reader(file_path: Path) -> vtk.vtkExodusIIReader:
    """Create and configure an Exodus II reader."""
    reader = vtk.vtkExodusIIReader()
    reader.SetFileName(str(file_path))
    reader.UpdateInformation()
    return reader


def extract_metadata(reader: vtk.vtkExodusIIReader) -> ExodusMetadata:
    """Extract metadata from an Exodus II reader."""
    # Get time information
    info = reader.GetExecutive().GetOutputInformation(0)
    num_timesteps = 0
    time_values = []

    if info.Has(vtk.vtkStreamingDemandDrivenPipeline.TIME_STEPS()):
        time_values = list(info.Get(vtk.vtkStreamingDemandDrivenPipeline.TIME_STEPS()))
        num_timesteps = len(time_values)

    # Get variable names
    nodal_variables = []
    for i in range(reader.GetNumberOfPointResultArrays()):
        nodal_variables.append(reader.GetPointResultArrayName(i))

    element_variables = []
    for i in range(reader.GetNumberOfElementResultArrays()):
        element_variables.append(reader.GetElementResultArrayName(i))

    global_variables = []
    for i in range(reader.GetNumberOfGlobalResultArrays()):
        global_variables.append(reader.GetGlobalResultArrayName(i))

    # Get element blocks
    element_blocks = []
    for i in range(reader.GetNumberOfElementBlockArrays()):
        block_name = reader.GetElementBlockArrayName(i)
        element_blocks.append({"index": i, "name": block_name})

    # Enable all arrays to get bounds
    for name in nodal_variables:
        reader.SetPointResultArrayStatus(name, 1)
    for name in element_variables:
        reader.SetElementResultArrayStatus(name, 1)
    for block in element_blocks:
        reader.SetElementBlockArrayStatus(block["name"], 1)

    reader.Update()
    output = reader.GetOutput()

    # Get bounds and counts from the output
    bounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    num_nodes = 0
    num_elements = 0

    if output:
        output.GetBounds(bounds)
        # Iterate through blocks to count
        iter = output.NewIterator()
        iter.InitTraversal()
        while not iter.IsDoneWithTraversal():
            block = iter.GetCurrentDataObject()
            if block and hasattr(block, "GetNumberOfPoints"):
                num_nodes += block.GetNumberOfPoints()
            if block and hasattr(block, "GetNumberOfCells"):
                num_elements += block.GetNumberOfCells()
            iter.GoToNextItem()

    bounds = tuple(bounds)

    return ExodusMetadata(
        num_timesteps=num_timesteps,
        time_values=time_values,
        nodal_variables=nodal_variables,
        element_variables=element_variables,
        global_variables=global_variables,
        element_blocks=element_blocks,
        bounds=bounds,
        num_nodes=num_nodes,
        num_elements=num_elements,
    )


def extract_surface(input_data: vtk.vtkDataObject) -> vtk.vtkPolyData:
    """Extract surface from a dataset (handles multi-block)."""
    if isinstance(input_data, vtk.vtkMultiBlockDataSet):
        # Use composite geometry filter for multi-block
        geometry_filter = vtk.vtkCompositeDataGeometryFilter()
        geometry_filter.SetInputData(input_data)
        geometry_filter.Update()
        return geometry_filter.GetOutput()
    else:
        # Single block - use surface filter
        surface_filter = vtk.vtkDataSetSurfaceFilter()
        surface_filter.SetInputData(input_data)
        surface_filter.Update()
        return surface_filter.GetOutput()


def apply_decimation(polydata: vtk.vtkPolyData, target_reduction: float) -> vtk.vtkPolyData:
    """Apply decimation to reduce triangle count."""
    if target_reduction <= 0 or target_reduction >= 1:
        return polydata

    decimate = vtk.vtkQuadricDecimation()
    decimate.SetInputData(polydata)
    decimate.SetTargetReduction(target_reduction)
    decimate.Update()
    return decimate.GetOutput()


def compute_normals(polydata: vtk.vtkPolyData) -> vtk.vtkPolyData:
    """Compute normals for the polydata."""
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(polydata)
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.SplittingOff()
    normals.Update()
    return normals.GetOutput()


def clean_polydata(polydata: vtk.vtkPolyData) -> vtk.vtkPolyData:
    """Clean polydata by merging duplicate points."""
    clean = vtk.vtkCleanPolyData()
    clean.SetInputData(polydata)
    clean.Update()
    return clean.GetOutput()


def write_vtp(polydata: vtk.vtkPolyData, output_path: Path, compress: bool = True):
    """Write polydata to VTP file."""
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(str(output_path))
    writer.SetInputData(polydata)
    if compress:
        writer.SetCompressorTypeToZLib()
    else:
        writer.SetCompressorTypeToNone()
    writer.Write()


def get_array_range(polydata: vtk.vtkPolyData, array_name: str) -> tuple[float, float]:
    """Get the scalar range for a named array."""
    point_data = polydata.GetPointData()
    cell_data = polydata.GetCellData()

    array = point_data.GetArray(array_name)
    if array is None:
        array = cell_data.GetArray(array_name)

    if array is None:
        return (0.0, 0.0)

    return array.GetRange()


def convert_timestep(
    reader: vtk.vtkExodusIIReader,
    timestep_index: int,
    request: ConvertRequest,
) -> vtk.vtkPolyData:
    """Convert a single timestep to polydata."""
    reader.SetTimeStep(timestep_index)
    reader.Update()

    output = reader.GetOutput()
    if output is None:
        raise ConversionError(f"Failed to read timestep {timestep_index}")

    # Extract surface
    polydata = extract_surface(output)

    # Optional decimation
    if request.decimate is not None and request.decimate > 0:
        polydata = apply_decimation(polydata, request.decimate)

    # Clean duplicate points
    polydata = clean_polydata(polydata)

    # Compute normals if requested
    if request.include_normals:
        polydata = compute_normals(polydata)

    return polydata


def run_conversion(request: ConvertRequest) -> dict:
    """
    Run the full conversion pipeline.

    Returns manifest data dictionary.
    """
    input_path = request.input_path
    output_dir = request.output_dir

    # Validate input file exists
    if not input_path.exists():
        raise InvalidExodusFileError(f"File not found: {input_path}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create reader and extract metadata
    reader = create_exodus_reader(input_path)
    metadata = extract_metadata(reader)

    # Configure which variables to include
    # First, disable all
    for name in metadata.nodal_variables:
        reader.SetPointResultArrayStatus(name, 0)
    for name in metadata.element_variables:
        reader.SetElementResultArrayStatus(name, 0)

    # Enable requested variables (or all if none specified)
    vars_to_enable = request.variables or (metadata.nodal_variables + metadata.element_variables)
    for name in vars_to_enable:
        if name in metadata.nodal_variables:
            reader.SetPointResultArrayStatus(name, 1)
        if name in metadata.element_variables:
            reader.SetElementResultArrayStatus(name, 1)

    # Configure element blocks
    if request.blocks:
        for block in metadata.element_blocks:
            status = 1 if block["name"] in request.blocks else 0
            reader.SetElementBlockArrayStatus(block["name"], status)
    else:
        # Enable all blocks
        for block in metadata.element_blocks:
            reader.SetElementBlockArrayStatus(block["name"], 1)

    # Determine which timesteps to process
    if request.timestep_mode == "single":
        timestep_indices = [request.timestep_index or 0]
    elif request.timestep_mode == "stride":
        stride = request.timestep_stride or 1
        timestep_indices = list(range(0, metadata.num_timesteps, stride))
    else:  # "all"
        timestep_indices = list(range(metadata.num_timesteps))

    # Handle case with no timesteps
    if not timestep_indices:
        timestep_indices = [0]

    # Convert each timestep
    files = []
    array_ranges = {}

    for i, ts_idx in enumerate(timestep_indices):
        polydata = convert_timestep(reader, ts_idx, request)

        # Write VTP file
        filename = f"surface_t{i:04d}.vtp"
        output_path = output_dir / filename
        write_vtp(polydata, output_path, request.compress)

        time_value = metadata.time_values[ts_idx] if ts_idx < len(metadata.time_values) else 0.0
        files.append(
            {
                "index": i,
                "timestep_index": ts_idx,
                "time_value": time_value,
                "filename": filename,
            }
        )

        # Track array ranges
        for name in vars_to_enable:
            range_val = get_array_range(polydata, name)
            if name not in array_ranges:
                array_ranges[name] = list(range_val)
            else:
                array_ranges[name][0] = min(array_ranges[name][0], range_val[0])
                array_ranges[name][1] = max(array_ranges[name][1], range_val[1])

    # Determine which variables are point vs cell data
    point_vars = [v for v in vars_to_enable if v in metadata.nodal_variables]
    cell_vars = [v for v in vars_to_enable if v in metadata.element_variables]

    # Build manifest
    manifest = {
        "version": "1.0",
        "num_timesteps": len(files),
        "files": files,
        "variables": {
            "point": point_vars,
            "cell": cell_vars,
        },
        "array_ranges": array_ranges,
        "bounds": list(metadata.bounds),
    }

    # Write manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Write metadata
    meta_path = output_dir / "meta.json"
    with open(meta_path, "w") as f:
        json.dump(metadata.to_dict(), f, indent=2)

    return manifest
