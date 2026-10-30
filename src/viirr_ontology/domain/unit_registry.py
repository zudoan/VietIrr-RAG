"""Unit dimensions, standard physical unit registry, and parameter compatibility logic.

Enforces physical dimension consistency:
- WaterLevel requires LENGTH (m, cm, mm).
- Discharge requires FLOW_RATE (m3/s, l/s).
- StorageCapacity requires VOLUME (million_m3, m3, billion_m3).
- WaterQuality requires CONCENTRATION (mg/l) or RATIO (%).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class UnitDimension(str, Enum):
    """Physical dimensions for hydraulic engineering parameters."""

    LENGTH = "LENGTH"
    FLOW_RATE = "FLOW_RATE"
    VOLUME = "VOLUME"
    CONCENTRATION = "CONCENTRATION"
    RATIO = "RATIO"
    UNKNOWN = "UNKNOWN"


# Mapping from normalized unit strings to their physical dimension
UNIT_TO_DIMENSION: dict[str, UnitDimension] = {
    # Length
    "m": UnitDimension.LENGTH,
    "mét": UnitDimension.LENGTH,
    "met": UnitDimension.LENGTH,
    "metre": UnitDimension.LENGTH,
    "meter": UnitDimension.LENGTH,
    "cm": UnitDimension.LENGTH,
    "mm": UnitDimension.LENGTH,
    # Flow rate (Volume / Time)
    "m3/s": UnitDimension.FLOW_RATE,
    "m³/s": UnitDimension.FLOW_RATE,
    "m3/giây": UnitDimension.FLOW_RATE,
    "m3/giay": UnitDimension.FLOW_RATE,
    "l/s": UnitDimension.FLOW_RATE,
    "lit/s": UnitDimension.FLOW_RATE,
    # Volume
    "m3": UnitDimension.VOLUME,
    "m³": UnitDimension.VOLUME,
    "triệu m3": UnitDimension.VOLUME,
    "trieu m3": UnitDimension.VOLUME,
    "million_m3": UnitDimension.VOLUME,
    "10^6 m3": UnitDimension.VOLUME,
    "10^6 m3": UnitDimension.VOLUME,
    "10^6m3": UnitDimension.VOLUME,
    "$10{m3}$": UnitDimension.VOLUME,
    "10{m3}": UnitDimension.VOLUME,
    "10{m3": UnitDimension.VOLUME,
    "$10^m3$": UnitDimension.VOLUME,
    "10^m3": UnitDimension.VOLUME,
    "$10^{6}m3$": UnitDimension.VOLUME,
    "tỷ m3": UnitDimension.VOLUME,
    "ty m3": UnitDimension.VOLUME,
    "billion_m3": UnitDimension.VOLUME,
    "10^9 m3": UnitDimension.VOLUME,
    # Concentration
    "mg/l": UnitDimension.CONCENTRATION,
    "mg/L": UnitDimension.CONCENTRATION,
    "ppm": UnitDimension.CONCENTRATION,
    # Ratio / Percentage
    "%": UnitDimension.RATIO,
    "phần trăm": UnitDimension.RATIO,
    "phan tram": UnitDimension.RATIO,
    "percent": UnitDimension.RATIO,
}

# Parameter patterns mapped to their valid physical dimensions
PARAMETER_ALLOWED_DIMENSIONS: dict[str, set[UnitDimension]] = {
    # Water levels
    "waterlevel": {UnitDimension.LENGTH},
    "water_level": {UnitDimension.LENGTH},
    "mực nước": {UnitDimension.LENGTH},
    "muc nuoc": {UnitDimension.LENGTH},
    "mndbt": {UnitDimension.LENGTH},
    "mnc": {UnitDimension.LENGTH},
    "mnltk": {UnitDimension.LENGTH},
    "mnlkt": {UnitDimension.LENGTH},
    "cao trình": {UnitDimension.LENGTH},
    "cao trinh": {UnitDimension.LENGTH},
    "cao trình đáy": {UnitDimension.LENGTH},
    "cao trinh day": {UnitDimension.LENGTH},
    # Flow rates
    "discharge": {UnitDimension.FLOW_RATE},
    "flow_rate": {UnitDimension.FLOW_RATE},
    "lưu lượng": {UnitDimension.FLOW_RATE},
    "luu luong": {UnitDimension.FLOW_RATE},
    "lưu lượng xả": {UnitDimension.FLOW_RATE},
    "lưu lượng đến": {UnitDimension.FLOW_RATE},
    "q_xả": {UnitDimension.FLOW_RATE},
    "q_đến": {UnitDimension.FLOW_RATE},
    # Storage capacities
    "storagecapacity": {UnitDimension.VOLUME},
    "storage_capacity": {UnitDimension.VOLUME},
    "dung tích": {UnitDimension.VOLUME},
    "dung tich": {UnitDimension.VOLUME},
    "dung tích toàn bộ": {UnitDimension.VOLUME},
    "dung tích hữu ích": {UnitDimension.VOLUME},
    "dung tích chết": {UnitDimension.VOLUME},
    "dung tích phòng lũ": {UnitDimension.VOLUME},
    "thể tích": {UnitDimension.VOLUME},
    # Water quality
    "waterqualityparameter": {UnitDimension.CONCENTRATION, UnitDimension.RATIO},
    "chất lượng nước": {UnitDimension.CONCENTRATION, UnitDimension.RATIO},
    "do": {UnitDimension.CONCENTRATION},
    "bod": {UnitDimension.CONCENTRATION},
    "bod5": {UnitDimension.CONCENTRATION},
    "cod": {UnitDimension.CONCENTRATION},
    "tss": {UnitDimension.CONCENTRATION},
    "độ mặn": {UnitDimension.CONCENTRATION, UnitDimension.RATIO},
}


def normalize_unit_string(unit: str) -> str:
    """Normalize unit string by stripping whitespace and lowercasing."""
    if not unit:
        return ""
    return unit.strip().lower()


def get_unit_dimension(unit: str) -> UnitDimension:
    """Retrieve the physical dimension for a given unit string."""
    norm = normalize_unit_string(unit)
    return UNIT_TO_DIMENSION.get(norm, UnitDimension.UNKNOWN)


def check_unit_compatibility(parameter_name: str, unit_str: str) -> tuple[bool, str]:
    """Check whether the given unit is physically compatible with the parameter.

    Enforces:
    1. Exact canonical parameter matching priority.
    2. Detection and rejection of ambiguous multi-parameter phrases (e.g. 'đo lưu lượng và mực nước').
    3. Proper dimension verification without arbitrary substring order.

    Returns:
        (is_compatible, explanation_message)
    """
    if not parameter_name or not unit_str:
        return False, "Parameter name and unit string must both be provided"

    norm_param = parameter_name.strip().lower()
    norm_unit = normalize_unit_string(unit_str)

    dimension = get_unit_dimension(norm_unit)
    if dimension == UnitDimension.UNKNOWN:
        return False, f"Unknown physical unit '{unit_str}'"

    # 1. Exact match priority for canonical parameter keys
    if norm_param in PARAMETER_ALLOWED_DIMENSIONS:
        allowed_dimensions = PARAMETER_ALLOWED_DIMENSIONS[norm_param]
    else:
        # 2. Substring matching with multi-parameter ambiguity detection
        matched_keys: list[str] = [
            param_key for param_key in PARAMETER_ALLOWED_DIMENSIONS if param_key in norm_param
        ]

        if not matched_keys:
            return False, f"Parameter '{parameter_name}' not recognized in hydraulic unit registry"

        # Check for multiple conflicting physical dimensions
        detected_dims: set[UnitDimension] = set()
        for k in matched_keys:
            detected_dims.update(PARAMETER_ALLOWED_DIMENSIONS[k])

        # Water quality parameters may legitimately have both CONCENTRATION and RATIO
        is_water_quality_dual = detected_dims.issubset({UnitDimension.CONCENTRATION, UnitDimension.RATIO})

        # If more than one dimension family is detected, report ambiguity
        if len(detected_dims) > 1 and not is_water_quality_dual:
            dim_names = ", ".join(sorted(d.value for d in detected_dims))
            return (
                False,
                f"Ambiguous multi-parameter phrase '{parameter_name}': multiple conflicting dimensions "
                f"detected [{dim_names}]. Canonical parameter identifier must be specified.",
            )

        allowed_dimensions = detected_dims

    if dimension in allowed_dimensions:
        return True, f"Unit '{unit_str}' (dimension {dimension.value}) is compatible with '{parameter_name}'"

    allowed_str = ", ".join(sorted(d.value for d in allowed_dimensions))
    return (
        False,
        f"Incompatible unit dimension: '{unit_str}' has dimension {dimension.value}, "
        f"but parameter '{parameter_name}' requires dimension in [{allowed_str}]",
    )


UNIT_SCALE_TO_BASE: dict[str, tuple[UnitDimension, float]] = {
    # Length -> base unit: m
    "m": (UnitDimension.LENGTH, 1.0),
    "mét": (UnitDimension.LENGTH, 1.0),
    "met": (UnitDimension.LENGTH, 1.0),
    "metre": (UnitDimension.LENGTH, 1.0),
    "meter": (UnitDimension.LENGTH, 1.0),
    "cm": (UnitDimension.LENGTH, 0.01),
    "mm": (UnitDimension.LENGTH, 0.001),
    "km": (UnitDimension.LENGTH, 1000.0),
    # Flow rate -> base unit: m3/s
    "m3/s": (UnitDimension.FLOW_RATE, 1.0),
    "m³/s": (UnitDimension.FLOW_RATE, 1.0),
    "m3/giây": (UnitDimension.FLOW_RATE, 1.0),
    "m3/giay": (UnitDimension.FLOW_RATE, 1.0),
    "l/s": (UnitDimension.FLOW_RATE, 0.001),
    "lit/s": (UnitDimension.FLOW_RATE, 0.001),
    # Volume -> base unit: m3
    "m3": (UnitDimension.VOLUME, 1.0),
    "m³": (UnitDimension.VOLUME, 1.0),
    "triệu m3": (UnitDimension.VOLUME, 1e6),
    "trieu m3": (UnitDimension.VOLUME, 1e6),
    "million_m3": (UnitDimension.VOLUME, 1e6),
    "10^6 m3": (UnitDimension.VOLUME, 1e6),
    "10^6m3": (UnitDimension.VOLUME, 1e6),
    "tỷ m3": (UnitDimension.VOLUME, 1e9),
    "ty m3": (UnitDimension.VOLUME, 1e9),
    "billion_m3": (UnitDimension.VOLUME, 1e9),
    "10^9 m3": (UnitDimension.VOLUME, 1e9),
    # Concentration -> base unit: mg/l
    "mg/l": (UnitDimension.CONCENTRATION, 1.0),
    "mg/L": (UnitDimension.CONCENTRATION, 1.0),
    "ppm": (UnitDimension.CONCENTRATION, 1.0),
    # Ratio -> base unit: %
    "%": (UnitDimension.RATIO, 1.0),
    "phần trăm": (UnitDimension.RATIO, 1.0),
    "phan tram": (UnitDimension.RATIO, 1.0),
    "percent": (UnitDimension.RATIO, 1.0),
}


def to_base_unit_value(value: float, unit_str: Optional[str]) -> tuple[float, UnitDimension]:
    """Convert a value with given unit to its physical dimension's base unit.
    Returns (scaled_base_value, dimension).
    """
    if unit_str is None or not str(unit_str).strip():
        return value, UnitDimension.UNKNOWN
    u_norm = normalize_unit_string(unit_str)
    info = UNIT_SCALE_TO_BASE.get(u_norm)
    if info is not None:
        dim, scale = info
        return value * scale, dim
    dim = get_unit_dimension(u_norm)
    return value, dim


