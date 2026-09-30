"""Versioned, JSON-compatible public MCP result schemas."""
from typing import Literal
from pydantic import BaseModel, ConfigDict

Vector3 = tuple[float, float, float]


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1"] = "1"
    caveats: list[str]


class CubeInfo(Result):
    shape: tuple[int, int, int]
    voxel_count: int
    atom_count: int
    origin: Vector3
    axes: tuple[Vector3, Vector3, Vector3]
    coordinate_unit: Literal["angstrom"] = "angstrom"
    amplitude_unit: Literal["source-defined"] = "source-defined"
    value_min: float
    value_max: float


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    energy_ev: float
    wavelength_nm: float
    oscillator_strength: float


class TransitionInfo(Result):
    transition_count: int
    energy_unit: Literal["eV"] = "eV"
    wavelength_unit: Literal["nm"] = "nm"
    oscillator_strength_unit: Literal["dimensionless"] = "dimensionless"
    transitions: list[Transition]


class Spectrum(Result):
    transition_count: int
    fwhm_ev: float
    energy_ev: list[float]
    wavelength_nm: list[float]
    intensity_f_per_ev: list[float]
    intensity_unit: Literal["oscillator_strength/eV"] = "oscillator_strength/eV"
    integrated_oscillator_strength: float
    total_oscillator_strength: float


class Export(Result):
    filename: str
    uri: str
    media_type: Literal["text/html", "text/csv"]
    size_bytes: int
    coordinate_unit: Literal["angstrom"] | None = None
    amplitude_unit: Literal["source-defined"] | None = None
    isovalue: float | None = None
    surface_count: int | None = None
    x_unit: Literal["eV", "nm"] | None = None
    intensity_unit: Literal["oscillator_strength/eV"] | None = None
    fwhm_ev: float | None = None
