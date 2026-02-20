from typing import List, Optional, Any, Literal, Union
from pydantic import BaseModel, Field, field_validator


class SelectOption(BaseModel):
    """Option for select dropdown fields"""
    value: str
    label: str


class FormField(BaseModel):
    """Configuration for a single form field"""
    id: str = Field(..., description="Unique identifier for the field")
    label: str = Field(..., description="Display label for the field")
    value: Union[str, bool, int, float] = Field(default="", description="Initial/default value")
    required: bool = Field(default=False, description="Whether the field is required")
    input_type: Literal[
        "text", "textarea", "select", "checkbox", 
        "number", "email", "password", "date", "datetime"
    ] = Field(default="text", description="Type of input field")
    
    # Optional fields
    placeholder: Optional[str] = Field(default=None, description="Placeholder text")
    help: Optional[str] = Field(default=None, description="Help text displayed below field")
    disabled: Optional[bool] = Field(default=False, description="Whether field is disabled")
    
    # Select-specific
    options: Optional[List[SelectOption]] = Field(default=None, description="Options for select fields")
    
    # Number-specific
    min: Optional[Union[int, float]] = Field(default=None, description="Minimum value for number fields")
    max: Optional[Union[int, float]] = Field(default=None, description="Maximum value for number fields")
    step: Optional[Union[int, float]] = Field(default=None, description="Step value for number fields")
    
    # Textarea-specific
    rows: Optional[int] = Field(default=None, description="Number of rows for textarea")
    
    # Checkbox-specific
    checkboxLabel: Optional[str] = Field(default=None, description="Custom label for checkbox")
    
    @field_validator('options')
    @classmethod
    def validate_options_for_select(cls, v, info):
        """Ensure options are provided for select fields"""
        if info.data.get('input_type') == 'select' and not v:
            raise ValueError("options must be provided for select input_type")
        return v



class DynamicFormProps(BaseModel):
    """Props for the DynamicForm component"""
    fields: List[FormField] = Field(..., description="List of form fields")
    title: Optional[str] = Field(default="Form", description="Form title")
    description: Optional[str] = Field(default=None, description="Form description")
    submitLabel: Optional[str] = Field(default="Submit", description="Submit button label")
    cancelLabel: Optional[str] = Field(default="Cancel", description="Cancel button label")
    timeout: Optional[int] = Field(default=0, description="Timeout in seconds (0 = no timeout)")
    
    def to_chainlit_props(self) -> dict:
        """Convert to dictionary for Chainlit CustomElement props"""
        return self.model_dump(exclude_none=True)



class FormResponse(BaseModel):
    """Response data from form submission"""
    data: dict[str, Any] = Field(..., description="Form field values keyed by field id")
    
    def get(self, field_id: str, default: Any = None) -> Any:
        """Get a field value by id"""
        return self.data.get(field_id, default)
    
    def get_str(self, field_id: str, default: str = "") -> str:
        """Get a field value as string"""
        value = self.data.get(field_id, default)
        return str(value) if value is not None else default
    
    def get_bool(self, field_id: str, default: bool = False) -> bool:
        """Get a field value as boolean"""
        value = self.data.get(field_id, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)
    
    def get_int(self, field_id: str, default: int = 0) -> int:
        """Get a field value as integer"""
        value = self.data.get(field_id, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_float(self, field_id: str, default: float = 0.0) -> float:
        """Get a field value as float"""
        value = self.data.get(field_id, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default


# Helper functions
def create_text_field(
    id: str,
    label: str,
    required: bool = False,
    placeholder: Optional[str] = None,
    help: Optional[str] = None,
    value: str = ""
) -> FormField:
    """Helper to create a text field"""
    return FormField(
        id=id,
        label=label,
        required=required,
        input_type="text",
        placeholder=placeholder,
        help=help,
        value=value
    )


def create_email_field(
    id: str,
    label: str,
    required: bool = False,
    placeholder: Optional[str] = None,
    help: Optional[str] = None,
    value: str = ""
) -> FormField:
    """Helper to create an email field"""
    return FormField(
        id=id,
        label=label,
        required=required,
        input_type="email",
        placeholder=placeholder,
        help=help,
        value=value
    )


def create_select_field(
    id: str,
    label: str,
    options: List[tuple[str, str]],  # List of (value, label) tuples
    required: bool = False,
    value: str = "",
    help: Optional[str] = None
) -> FormField:
    """Helper to create a select field"""
    return FormField(
        id=id,
        label=label,
        required=required,
        input_type="select",
        options=[SelectOption(value=v, label=l) for v, l in options],
        value=value,
        help=help
    )


def create_textarea_field(
    id: str,
    label: str,
    required: bool = False,
    rows: int = 4,
    placeholder: Optional[str] = None,
    help: Optional[str] = None,
    value: str = ""
) -> FormField:
    """Helper to create a textarea field"""
    return FormField(
        id=id,
        label=label,
        required=required,
        input_type="textarea",
        rows=rows,
        placeholder=placeholder,
        help=help,
        value=value
    )


def create_checkbox_field(
    id: str,
    label: str,
    checkbox_label: Optional[str] = None,
    required: bool = False,
    value: bool = False,
    help: Optional[str] = None
) -> FormField:
    """Helper to create a checkbox field"""
    return FormField(
        id=id,
        label=label,
        required=required,
        input_type="checkbox",
        checkboxLabel=checkbox_label,
        value=value,
        help=help
    )


def create_number_field(
    id: str,
    label: str,
    required: bool = False,
    min_val: Optional[Union[int, float]] = None,
    max_val: Optional[Union[int, float]] = None,
    step: Optional[Union[int, float]] = None,
    placeholder: Optional[str] = None,
    help: Optional[str] = None,
    value: Union[int, float, str] = ""
) -> FormField:
    """Helper to create a number field"""
    return FormField(
        id=id,
        label=label,
        required=required,
        input_type="number",
        min=min_val,
        max=max_val,
        step=step,
        placeholder=placeholder,
        help=help,
        value=value
    )


def create_date_field(
    id: str,
    label: str,
    required: bool = False,
    help: Optional[str] = None,
    value: str = ""
) -> FormField:
    """Helper to create a date field"""
    return FormField(
        id=id,
        label=label,
        required=required,
        input_type="date",
        help=help,
        value=value
    )
