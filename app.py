"""Run with `streamlit run app.py` to explore local orbital calculations."""
import io
import zipfile
import numpy as np
import streamlit as st
from orbital_viewer.data import Grid, read_cube, read_transitions, demo_grid, HC, broaden
from orbital_viewer.plots import orbital_figure, spectrum_figure

st.set_page_config(page_title="Orbital Studio", page_icon="⚛", layout="wide")
st.markdown("""<style>
.block-container {padding-top:2rem; max-width:1600px}
h1 {letter-spacing:-.045em; font-weight:650!important}
[data-testid="stMetric"] {background:#141e2c; padding:16px; border-radius:12px}
</style>""", unsafe_allow_html=True)
st.caption("ORBITAL STUDIO  /  COMPUTATIONAL CHEMISTRY")
st.title("See the shape of an excitation.")
st.write("Explore orbital phases, compare hole–electron pairs, and inspect absorption spectra.")

with st.sidebar:
    st.header("Workspace")
    mode = st.radio("Data source", ["Illustrative demo", "My calculations"])
    st.divider()
    st.subheader("Surface controls")
    fraction = st.slider("Isovalue (% of each field's max |ψ|)", 1, 80, 18)
    absolute = st.checkbox("Use a shared absolute isovalue")
    absolute_level = st.number_input("Absolute |ψ| threshold", min_value=.000001, value=.03, format="%.6f") if absolute else None
    opacity = st.slider("Surface opacity", .15, 1., .72, .05)
    show_atoms = st.checkbox("Show atoms and inferred bonds", True)
    st.caption("Yellow: positive ψ · Cyan: negative ψ. Colors indicate wavefunction phase, not charge.")
    st.divider()
    st.caption("Files are processed by this Python app. Run locally to keep calculation data on your computer.")

@st.cache_data(max_entries=12, show_spinner=False)
def load_grid(content: bytes, name: str) -> Grid:
    """Cache validated scalar grids across surface-control interactions."""
    return read_cube(content.decode("utf-8"), name)

@st.cache_data(max_entries=4, show_spinner=False)
def load_spectrum(content: bytes, name: str) -> np.ndarray:
    """Cache spectrum parsing while preserving validation errors."""
    return read_transitions(content.decode("utf-8"), name)

grids = {}
spectrum = None
if mode == "Illustrative demo":
    st.info("ILLUSTRATIVE DEMO · Analytic benzene-like π fields and synthetic transitions. These are not calculated molecular orbitals or NTOs.")
    grids = {"Illustrative hole-like field": demo_grid(0), "Illustrative electron-like field": demo_grid(1)}
    spectrum = np.array([[3.65, .09], [4.241, .72], [4.85, .26], [5.4, .12]])
else:
    with st.expander("Import calculation files", expanded=True):
        st.write("Upload one scalar orbital per CUBE file. Select hole/electron assignments below; filenames are not treated as scientific metadata.")
        uploads = st.file_uploader("Orbital CUBE files", type=["cube", "cub"], accept_multiple_files=True)
        spec_file = st.file_uploader("Absorption transitions", type=["csv", "out", "log"])
        st.caption("CSV columns: energy_ev, oscillator_strength. ORCA output support depends on cclib's parser. Binary .gbw/.nto files must first be exported to CUBE using ORCA.")
        for index, upload in enumerate(uploads):
            try:
                grids[f"{index + 1}. {upload.name}"] = load_grid(upload.getvalue(), upload.name)
            except (ValueError, UnicodeError) as exc:
                st.error(f"{upload.name}: {exc}")
        if spec_file:
            try:
                spectrum = load_spectrum(spec_file.getvalue(), spec_file.name)
            except (ValueError, UnicodeError) as exc:
                st.error(f"{spec_file.name}: {exc}")
        st.download_button("Download CSV template", "energy_ev,oscillator_strength\n4.241,0.72\n", "transitions_template.csv", "text/csv")

orbital_tab, spectrum_tab, guide_tab = st.tabs(["Orbital explorer", "Absorption spectrum", "Workflow & interpretation"])
with orbital_tab:
    if not grids:
        st.info("Upload CUBE files to start, or choose Illustrative demo in the sidebar.")
    else:
        pairing = st.toggle("Compare hole / electron", value=True)
        names = list(grids)
        columns = st.columns(2) if pairing else [st.container()]
        figures = {}
        for i, column in enumerate(columns):
            with column:
                role = ("Hole orbital", "Electron orbital")[i] if pairing else "Orbital"
                name = st.selectbox(role, names, index=min(i, len(names)-1), key=f"orbital_{i}")
                grid = grids[name]
                maximum = float(np.max(np.abs(grid.values)))
                level = absolute_level if absolute_level is not None else maximum * fraction / 100
                st.caption(f"Isovalue ±{level:.5g} · Grid {' × '.join(map(str, grid.values.shape))} · Coordinates in Å")
                if not grid.values.min() < level < grid.values.max() and not grid.values.min() < -level < grid.values.max():
                    st.warning("No isosurface at this threshold. Lower the isovalue.")
                fig = orbital_figure(grid, level, opacity, show_atoms)
                figures[role] = fig
                st.plotly_chart(fig, width="stretch", key=f"view_{i}")
                st.download_button(f"Export {role.lower()} HTML", fig.to_html(include_plotlyjs=True), f"orbital_{i}.html", "text/html", key=f"export_{i}")
        if pairing:
            st.caption("Views rotate independently. Use a shared absolute threshold for amplitude comparisons; relative thresholds scale each field separately. Assignments are user-selected, not inferred NTO pairings.")
        with st.expander("Batch export all loaded orbitals"):
            st.write("Generate an offline, interactive HTML view for every loaded grid with the current surface settings.")
            if st.button("Prepare ZIP"):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                    for i, (name, grid) in enumerate(grids.items()):
                        level = absolute_level if absolute_level is not None else float(np.max(np.abs(grid.values))) * fraction / 100
                        figure = orbital_figure(grid, level, opacity, show_atoms)
                        archive.writestr(f"orbital_{i+1}.html", figure.to_html(include_plotlyjs=True))
                    archive.writestr("manifest.txt", "\n".join(f"orbital_{i+1}.html: {name}" for i, name in enumerate(grids)))
                st.download_button("Download orbital views", buffer.getvalue(), "orbital_views.zip", "application/zip")
with spectrum_tab:
    if spectrum is None:
        st.info("Upload a transition CSV or supported ORCA output to see its absorption spectrum.")
    else:
        left, right = st.columns([2, 1])
        with left:
            fwhm = st.slider("Gaussian broadening · FWHM (eV)", .02, .8, .18, .01)
        with right:
            unit = st.selectbox("Horizontal axis", ["Energy (eV)", "Wavelength (nm)"])
        a, b, c = st.columns(3)
        strongest = spectrum[np.argmax(spectrum[:, 1])]
        a.metric("Transitions", len(spectrum))
        b.metric("Strongest transition", f"{strongest[0]:.3f} eV")
        c.metric("Corresponding wavelength", f"{HC / strongest[0]:.1f} nm")
        st.plotly_chart(spectrum_figure(spectrum, fwhm, unit.startswith("Wavelength")), width="stretch")
        st.caption("Gaussian broadening is computed in eV. The nm view relabels photon energy; envelope intensity remains f/eV, not a density per nm. This is not a calibrated experimental absorbance spectrum.")
        st.dataframe({"State (row order)": np.arange(1, len(spectrum)+1), "Energy (eV)": spectrum[:, 0],
                      "Wavelength (nm)": HC / spectrum[:, 0], "Oscillator strength": spectrum[:, 1]}, width="stretch", hide_index=True)
        x, y = broaden(spectrum, fwhm)
        output = io.StringIO()
        np.savetxt(output, np.column_stack((x, HC/x, y)), delimiter=",", header="energy_ev,wavelength_nm,intensity_f_per_ev", comments="")
        st.download_button("Export broadened spectrum CSV", output.getvalue(), "spectrum.csv", "text/csv")
with guide_tab:
    st.subheader("From calculation to comparison")
    st.markdown("""
1. Run your electronic-structure calculation externally. For NTOs, request the relevant excited-state analysis in ORCA.
2. Export each desired orbital to a separate Gaussian CUBE file with `orca_plot`. This app does not run ORCA or reconstruct orbitals from a screenshot.
3. Upload multiple CUBE files once, select your hole and electron fields, and adjust the surface threshold.
4. Upload the calculation output or a CSV of excitation energies and oscillator strengths. Export figures or a batch of all orbital views.

**What the surfaces mean.** Surfaces show constant signed wavefunction amplitude. Probability density is proportional to |ψ|². Positive/negative colors are not electron/hole charge or probabilities.

**Comparison limits.** Use files from the same molecular geometry and coordinate frame for a meaningful spatial comparison. Molecules are not automatically aligned. Bond lines are inferred from distances and do not encode bond order. CUBE amplitude units are inherited from the calculation.

**Supported files.** Scalar CUBE and single-orbital CUBE with orbital-ID records, Bohr or angstrom grids, including skewed axes. Multi-field cubes are rejected. Maximum 4 million voxels per file; uploads are limited to 40 MB each. ORCA output extraction uses cclib; unsupported outputs show an error and can be supplied as CSV instead.

[ORCA excited-state documentation](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/tddft.html) · [cclib parsed data](https://cclib.github.io/data.html)
""")
