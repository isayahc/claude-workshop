"""Plotly orbital isosurfaces and spectra without external JavaScript services."""
import numpy as np
import plotly.graph_objects as go
from skimage.measure import marching_cubes
from orbital_viewer.data import Grid, broaden, HC


def orbital_figure(grid: Grid, level: float, opacity: float, atoms: bool = True) -> go.Figure:
    """Extract signed isosurfaces using the full grid-to-world affine transform."""
    fig = go.Figure()
    for sign, color, name in [(1, "#eed66c", "Positive phase"), (-1, "#40c9e2", "Negative phase")]:
        threshold = sign * level
        if grid.values.min() < threshold < grid.values.max():
            vertices, faces, _, _ = marching_cubes(grid.values, level=threshold)
            vertices = vertices @ grid.axes + grid.origin
            fig.add_trace(go.Mesh3d(x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
                i=faces[:, 0], j=faces[:, 1], k=faces[:, 2], color=color, opacity=opacity,
                name=name, showlegend=True, hoverinfo="skip", lighting=dict(ambient=.5, diffuse=.8, specular=.25)))
    if atoms and len(grid.atoms):
        positions = grid.atoms[:, 2:5]
        numbers = grid.atoms[:, 0].astype(int)
        # Distance-based inferred connectivity; never presented as calculated bond order.
        radii = {1: .31, 6: .76, 7: .71, 8: .66, 9: .57, 14: 1.11, 15: 1.07, 16: 1.05, 17: 1.02}
        from scipy.spatial import cKDTree
        bond_x, bond_y, bond_z = [], [], []
        for a, b in cKDTree(positions).query_pairs(3.6):
            distance = np.linalg.norm(positions[a] - positions[b])
            if .2 < distance < 1.2 * (radii.get(numbers[a], 1.2) + radii.get(numbers[b], 1.2)):
                for coords, axis in [(bond_x, 0), (bond_y, 1), (bond_z, 2)]:
                    coords.extend([positions[a, axis], positions[b, axis], None])
        fig.add_trace(go.Scatter3d(x=bond_x, y=bond_y, z=bond_z, mode="lines",
            line=dict(color="#8391aa", width=5), hoverinfo="skip", showlegend=False))
        colors = {1: "#edf3fb", 6: "#68778d", 7: "#719aff", 8: "#f47683", 14: "#bf99ef"}
        fig.add_trace(go.Scatter3d(x=positions[:, 0], y=positions[:, 1], z=positions[:, 2],
            mode="markers", marker=dict(size=[4 if n == 1 else 7 for n in numbers],
            color=[colors.get(n, "#ba96df") for n in numbers]), text=[f"Atomic number {n}" for n in numbers],
            hovertemplate="%{text}<extra></extra>", showlegend=False))
    axis = dict(visible=False)
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0b111b",
        font_color="#edf3fb", scene=dict(xaxis=axis, yaxis=axis, zaxis=axis, aspectmode="data",
        bgcolor="#0b111b", camera=dict(eye=dict(x=1.5, y=1.5, z=.9))),
        legend=dict(orientation="h", x=.02, y=.02), uirevision=grid.title)
    return fig


def spectrum_figure(table: np.ndarray, fwhm: float, wavelength: bool) -> go.Figure:
    """Show broadened absorption and sticks with distinct intensity axes."""
    energy, intensity = broaden(table, fwhm)
    x, sticks = (HC / energy, HC / table[:, 0]) if wavelength else (energy, table[:, 0])
    fig = go.Figure(go.Scatter(x=x, y=intensity, line=dict(color="#a5f0ce", width=3),
                              fill="tozeroy", name="Gaussian envelope"))
    for position, strength in zip(sticks, table[:, 1]):
        fig.add_trace(go.Scatter(x=[position, position], y=[0, strength], mode="lines",
            line=dict(color="#eed66c", width=2), yaxis="y2", showlegend=False, name="Oscillator strength"))
    fig.update_layout(height=330, template="plotly_dark", paper_bgcolor="#0b111b", plot_bgcolor="#0b111b",
        margin=dict(l=40, r=40, t=20, b=40), xaxis_title="Wavelength (nm)" if wavelength else "Energy (eV)",
        yaxis_title="Envelope (f / eV)", yaxis2=dict(title="Stick strength (f)", overlaying="y", side="right", rangemode="tozero"),
        showlegend=False)
    return fig
