from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from state.deeplynx import upload_file_to_deeplynx, download_file_from_deeplynx
from fastapi import HTTPException

from models.dynamic_form import (
    DynamicFormProps,
    create_text_field,
    create_email_field,
    create_number_field,
    create_select_field,
    create_textarea_field,
    create_checkbox_field
)

router = APIRouter(
    prefix="/demo",
    tags=["Demo"]
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


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


@router.get("/ifc-download")
def download_from_deeplynx(record_id: int = 3518):
    try:
        result = download_file_from_deeplynx(record_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ifc")
async def get_ifc_file():
    file_path = DATA_DIR / "sample.ifc"
    try:
        result = upload_file_to_deeplynx(file_path=file_path)
        return {
            "status": "success",
            "deeplynx_response": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
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


@router.get("/nuclear-system-design", response_model=DynamicFormProps)
async def get_nuclear_system_design_form():
    """Get the Nuclear System Design form configuration"""
    return DynamicFormProps(
        title="Design a Nuclear System",
        description=(
            "Describe what you want to build in plain English. The agent asks for any missing "
            "information, shows the proposed topology, runs the sizing pipeline, and saves the "
            "design. You can also load a saved design from the sidebar."
        ),
        submitLabel="Accept Parameters →",
        cancelLabel="Cancel",
        timeout=0,
        fields=[
            # --- System Identity ---
            create_select_field(
                id="system_loop",
                label="Which system are you designing?",
                options=[
                    ("primary_loop", "Primary Loop"),
                    ("bop_loop", "Balance of Plant Loop"),
                    ("intermediate_loop", "Intermediate Loop"),
                ],
                required=True,
                help="Select the nuclear system loop you want to size and configure.",
            ),
            create_select_field(
                id="reactor_type",
                label="Reactor Type",
                options=[
                    ("pwr", "PWR – Pressurized Water Reactor"),
                    ("bwr", "BWR – Boiling Water Reactor"),
                    ("msr", "MSR – Molten Salt Reactor"),
                    ("sfr", "SFR – Sodium Fast Reactor"),
                ],
                required=True,
                help="Select the reactor concept this system will be coupled to.",
            ),
            create_select_field(
                id="safety_classification",
                label="Safety Classification",
                options=[
                    ("class_1", "Class 1 – Pressure Boundary"),
                    ("class_2", "Class 2 – Safety-Related"),
                    ("class_3", "Class 3 – Safety-Related Support"),
                    ("non_nuclear", "Non-Nuclear / Balance of Plant"),
                ],
                required=True,
                help="ASME Section III safety classification for the system.",
            ),
            create_select_field(
                id="coolant",
                label="Coolant",
                options=[
                    ("water", "Water"),
                    ("sodium", "Sodium"),
                    ("co2", "CO₂"),
                    ("helium", "Helium"),
                ],
                required=True,
                help="Primary working coolant for the system.",
            ),
            # --- Thermal Power ---
            create_number_field(
                id="thermal_power_mwth",
                label="Thermal Power (MWth)",
                required=True,
                min_val=1,
                max_val=5000,
                step=1,
                help="Reactor thermal output in megawatts thermal (e.g. 300 for 300 MWth).",
            ),
            # --- Primary Side ---
            create_number_field(
                id="primary_pressure_mpa",
                label="Primary Pressure (MPa)",
                required=True,
                min_val=1.0,
                max_val=25.0,
                step=0.5,
                help="Operating pressure on the primary (reactor) side.",
            ),
            create_number_field(
                id="primary_hot_leg_c",
                label="Hot-Leg Temperature (°C)",
                required=True,
                min_val=100.0,
                max_val=600.0,
                step=5.0,
                help="Coolant temperature leaving the reactor core.",
            ),
            # --- Secondary / Steam Side ---
            create_number_field(
                id="secondary_pressure_mpa",
                label="Steam Pressure (MPa)",
                required=True,
                min_val=0.1,
                max_val=15.0,
                step=0.1,
                help="Steam generator / secondary-side operating pressure.",
            ),
            create_number_field(
                id="condenser_pressure_mpa",
                label="Condenser Pressure (MPa)",
                required=True,
                min_val=0.001,
                max_val=0.1,
                step=0.001,
                help="Turbine exhaust / condenser back-pressure (typical: 0.006–0.01 MPa).",
            ),
            create_number_field(
                id="feedwater_temperature_c",
                label="Feedwater Temperature (°C)",
                required=True,
                min_val=20.0,
                max_val=400.0,
                step=5.0,
                help="Temperature of feedwater entering the steam generator.",
            ),
            create_number_field(
                id="steam_outlet_temperature_c",
                label="Steam Outlet Temperature (°C)",
                required=True,
                min_val=100.0,
                max_val=600.0,
                step=5.0,
                help="Temperature of steam leaving the steam generator.",
            ),
            # --- Optimization ---
            create_select_field(
                id="optimization_objective",
                label="Optimization Objective",
                options=[
                    ("thermal_efficiency", "Maximize Thermal Efficiency"),
                    ("minimize_cost", "Minimize Capital Cost"),
                    ("minimize_mass", "Minimize Component Mass"),
                    ("minimize_volume", "Minimize System Volume"),
                ],
                required=False,
                help="Primary figure of merit used during the automated sizing pipeline.",
            ),
            # --- Notes ---
            create_textarea_field(
                id="notes",
                label="Additional Notes",
                required=False,
                rows=3,
                placeholder="Describe any constraints, design intent, or special requirements...",
                help="Plain-English description of what you want to build. The agent will extract missing details automatically.",
            ),
        ],
    )