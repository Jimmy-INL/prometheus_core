from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(
    prefix="/demo",
    tags=["Demo"]
)

from models.dynamic_form import (
    DynamicFormProps,
    create_text_field,
    create_email_field,
    create_number_field,
    create_select_field,
    create_textarea_field,
    create_checkbox_field
)

@router.get("/autodone", response_model=DynamicFormProps)
async def get_registration_form():
    """Get the registration form configuration"""
    return DynamicFormProps(
        title="AutoDONE",
        description="Please fill out all required fields",
        submitLabel="Execute",
        cancelLabel="Cancel",
        timeout=0,
        fields=[
            # --- Required Inputs ---
            create_number_field(
                id="flow_rate",
                label="Flow Rate (GPM)",
                required=True,
                min_val=0,
                max_val=10000,
                step=0.1,
                help="Volumetric flow rate in gallons per minute"
            ),
            create_number_field(
                id="system_pressure",
                label="System Pressure (PSI)",
                required=True,
                min_val=0,
                max_val=5000,
                step=0.1,
                help="Operating system pressure in pounds per square inch"
            ),
            create_number_field(
                id="inlet_temperature",
                label="Inlet Temperature (°F)",
                required=True,
                min_val=-460,
                max_val=2000,
                step=0.1,
                help="Fluid temperature before the heat exchanger"
            ),
            create_number_field(
                id="outlet_temperature",
                label="Outlet Temperature (°F)",
                required=True,
                min_val=-460,
                max_val=2000,
                step=0.1,
                help="Fluid temperature after the heat exchanger"
            ),
            # --- Optional Inputs ---
            create_number_field(
                id="design_pressure",
                label="Design Pressure (PSI)",
                required=False,
                min_val=0,
                max_val=10000,
                step=0.1,
                help="Maximum allowable working pressure"
            ),
            create_number_field(
                id="pipe_diameter",
                label="Pipe Diameter (inches)",
                required=False,
                min_val=0.125,
                max_val=120,
                step=0.125,
                help="Nominal pipe diameter in inches"
            ),
            create_select_field(
                id="pipe_schedule",
                label="Pipe Schedule",
                options=[
                    ("sch_40", "Schedule 40"),
                    ("sch_80", "Schedule 80"),
                    ("sch_160", "Schedule 160"),
                    ("sch_xxs", "Double Extra Strong"),
                ],
                required=False,
                help="Pipe wall thickness schedule"
            ),
            create_select_field(
                id="fluid_type",
                label="Fluid Type",
                options=[
                    ("water", "Water"),
                    ("steam", "Steam"),
                    ("thermal_oil", "Thermal Oil"),
                    ("glycol", "Glycol Solution"),
                ],
                required=False,
                help="Working fluid in the system"
            ),
            create_number_field(
                id="fouling_factor",
                label="Fouling Factor (ft²·°F·hr/BTU)",
                required=False,
                min_val=0,
                max_val=0.01,
                step=0.0001,
                help="Resistance to heat transfer due to deposit buildup"
            ),
            create_textarea_field(
                id="notes",
                label="Additional Notes",
                required=False,
                rows=3,
                placeholder="Any additional information or constraints...",
                help="Optional notes for the analysis"
            ),
        ]
    )

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

@router.get("/ifc")
async def get_ifc_file():
    return FileResponse(
        DATA_DIR / "sample.ifc",
        media_type="application/x-ifc",
        filename="sample.ifc",
    )

@router.get("/exodus")
async def get_exodus_file():
    return FileResponse(
        DATA_DIR / "sample.e",
        media_type="application/octet-stream",
        filename="sample.e",
    )

@router.get("/ecar")
async def get_ecar_file():
    return FileResponse(
        DATA_DIR / "ecar.pdf",
        media_type="application/pdf",
        filename="ecar.pdf",
    )