"""Public MCP schemas, scientific results, file boundaries, and actual stdio calls."""
from datetime import timedelta
from pathlib import Path
import shutil
import subprocess
import sys

import anyio
import jsonschema
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
import numpy as np
import pytest

from orbital_viewer.data import BOHR, HC
from orbital_viewer.mcp_files import MAX_FILE_BYTES, FileAccessError, LocalFiles
from orbital_viewer.mcp_server import create_server

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def data_dir(tmp_path):
    path = tmp_path / "data"
    shutil.copytree(ROOT / "examples" / "mcp", path, ignore=shutil.ignore_patterns("exports"))
    return path


async def successful_call(session, schemas, name, arguments):
    result = await session.call_tool(name, arguments)
    assert not result.isError, result.content
    assert result.structuredContent is not None
    jsonschema.validate(result.structuredContent, schemas[name].outputSchema)
    assert result.structuredContent["schema_version"] == "1"
    assert result.structuredContent["caveats"]
    return result.structuredContent


@pytest.mark.anyio
async def test_stdio_session_discovers_calls_and_exports(data_dir, tmp_path):
    """Launch from an unrelated cwd, communicate over JSON-RPC, validate every result schema."""
    output = tmp_path / "exports"
    params = StdioServerParameters(command=sys.executable, args=[
        "-m", "orbital_viewer.mcp_server", "--data-dir", str(data_dir), "--output-dir", str(output)
    ], cwd=str(tmp_path))
    with anyio.fail_after(60):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert set(tools) == {"inspect_cube", "inspect_transitions", "broaden_spectrum", "export_orbital", "export_spectrum"}
                for tool in tools.values():
                    jsonschema.Draft202012Validator.check_schema(tool.inputSchema)
                    jsonschema.Draft202012Validator.check_schema(tool.outputSchema)
                    assert tool.inputSchema["required"] == ["filename"]
                    assert tool.annotations.openWorldHint is False
                    assert tool.annotations.destructiveHint is False
                    assert tool.annotations.readOnlyHint == tool.name.startswith(("inspect_", "broaden_"))
                assert tools["broaden_spectrum"].inputSchema["properties"]["fwhm_ev"]["exclusiveMinimum"] == 0
                assert set(tools["export_spectrum"].inputSchema["properties"]["format"]["enum"]) == {"csv", "html"}

                info = await successful_call(session, tools, "inspect_cube", {"filename": "signed-field.cube"})
                assert info["shape"] == [2, 2, 2] and info["voxel_count"] == 8
                assert info["atom_count"] == 1 and info["coordinate_unit"] == "angstrom"
                assert info["axes"][1] == [0.5, 1, 0]
                assert [info["value_min"], info["value_max"]] == [-1, 1]
                transitions = await successful_call(session, tools, "inspect_transitions", {"filename": "transitions.csv"})
                assert transitions["transition_count"] == 4
                assert transitions["transitions"][0]["wavelength_nm"] == pytest.approx(HC / 3.65)
                orca = await successful_call(session, tools, "inspect_transitions", {"filename": "synthetic-orca.out"})
                assert [t["energy_ev"] for t in orca["transitions"]] == pytest.approx([4, 5])
                assert [t["oscillator_strength"] for t in orca["transitions"]] == [0.72, 0.26]
                spectrum = await successful_call(session, tools, "broaden_spectrum", {"filename": "transitions.csv", "fwhm_ev": .18})
                assert len(spectrum["energy_ev"]) == len(spectrum["intensity_f_per_ev"]) == 1600
                np.testing.assert_allclose(spectrum["wavelength_nm"], HC / np.array(spectrum["energy_ev"]))
                assert spectrum["integrated_oscillator_strength"] == pytest.approx(1.19, rel=1e-5)
                assert spectrum["total_oscillator_strength"] == pytest.approx(1.19)
                assert not output.exists(), "Read-only tools must not create exports"

                csv = await successful_call(session, tools, "export_spectrum", {"filename": "transitions.csv"})
                csv_path = output / csv["filename"]
                assert csv_path.as_uri() == csv["uri"] and csv_path.stat().st_size == csv["size_bytes"]
                assert csv_path.read_text().startswith("energy_ev,wavelength_nm,intensity_f_per_ev\n")
                curve = np.loadtxt(csv_path, delimiter=",", skiprows=1)
                np.testing.assert_allclose(curve, np.column_stack((spectrum["energy_ev"], spectrum["wavelength_nm"], spectrum["intensity_f_per_ev"])))
                html = await successful_call(session, tools, "export_spectrum", {"filename": "transitions.csv", "format": "html", "x_unit": "nm"})
                text = (output / html["filename"]).read_text()
                assert "Wavelength (nm)" in text and "Envelope (f / eV)" in text.replace("\\u002f", "/")
                assert '<script src="https://' not in text
                assert html["x_unit"] == "nm" and html["intensity_unit"] == "oscillator_strength/eV"
                orbital = await successful_call(session, tools, "export_orbital", {"filename": "signed-field.cube", "isovalue": .5})
                assert orbital["surface_count"] == 2 and orbital["isovalue"] == .5
                text = (output / orbital["filename"]).read_text()
                assert "Positive phase" in text and "Negative phase" in text
                assert '<script src="https://' not in text
                another = await successful_call(session, tools, "export_orbital", {"filename": "signed-field.cube", "isovalue": 2})
                assert another["filename"] != orbital["filename"]
                assert another["surface_count"] == 0
                assert any("No isosurface" in note for note in another["caveats"])
                assert len(list(output.iterdir())) == 4
                # An error must not break the protocol or poison the next request.
                error = await session.call_tool("inspect_transitions", {"filename": "missing.csv"})
                assert error.isError and str(data_dir) not in str(error.content)
                await successful_call(session, tools, "inspect_cube", {"filename": "signed-field.cube"})


@pytest.mark.anyio
@pytest.mark.parametrize("name,args", [
    ("inspect_cube", {}),
    ("inspect_cube", {"filename": ""}),
    ("broaden_spectrum", {"filename": "transitions.csv", "fwhm_ev": 0}),
    ("broaden_spectrum", {"filename": "transitions.csv", "fwhm_ev": -1}),
    ("broaden_spectrum", {"filename": "transitions.csv", "fwhm_ev": float("nan")}),
    ("broaden_spectrum", {"filename": "transitions.csv", "fwhm_ev": float("inf")}),
    ("broaden_spectrum", {"filename": "transitions.csv", "fwhm_ev": 101}),
    ("export_orbital", {"filename": "signed-field.cube", "opacity": 1.5}),
    ("export_orbital", {"filename": "signed-field.cube", "isovalue": 0}),
    ("export_spectrum", {"filename": "transitions.csv", "format": "pdf"}),
    ("export_spectrum", {"filename": "transitions.csv", "x_unit": "cm-1"}),
])
async def test_tool_argument_validation(data_dir, name, args):
    async with create_connected_server_and_client_session(create_server(data_dir)) as session:
        result = await session.call_tool(name, args)
        assert result.isError
        assert not (data_dir / "exports").exists()


@pytest.mark.anyio
@pytest.mark.parametrize("filename,content,tool", [
    ("bad.cube", "broken", "inspect_cube"),
    ("bad.csv", "wrong,columns\n1,2", "inspect_transitions"),
    ("bad.csv", "energy_ev,oscillator_strength\n1,-1", "broaden_spectrum"),
    ("bad.csv", "energy_ev,oscillator_strength\n-1,1", "inspect_transitions"),
    ("bad.csv", "energy_ev,oscillator_strength\n1,nan", "inspect_transitions"),
    ("bad.out", "Not supported ORCA output", "inspect_transitions"),
    ("bad.csv", "energy_ev,oscillator_strength\n1e308,1e308", "broaden_spectrum"),
])
async def test_malformed_inputs_return_useful_errors(data_dir, filename, content, tool):
    (data_dir / filename).write_text(content)
    async with create_connected_server_and_client_session(create_server(data_dir)) as session:
        result = await session.call_tool(tool, {"filename": filename})
        assert result.isError
        assert "Traceback" not in str(result.content) and str(data_dir) not in str(result.content)
        assert any(word in str(result.content) for word in ("CUBE", "CSV", "numeric"))


@pytest.mark.anyio
async def test_voxel_atom_transition_limits_and_safe_internal_errors(data_dir, monkeypatch):
    cube = (data_dir / "signed-field.cube").read_text()
    async with create_connected_server_and_client_session(create_server(data_dir)) as session:
        for oversized in [cube.replace("-2 1 0 0", "-1000001 1 0 0"), cube.replace("1 0 0 0", "10001 0 0 0", 1)]:
            (data_dir / "large.cube").write_text(oversized)
            result = await session.call_tool("inspect_cube", {"filename": "large.cube"})
            assert result.isError and "limits" in str(result.content)
        (data_dir / "large.csv").write_text("energy_ev,oscillator_strength\n" + "1,0.1\n" * 10_001)
        result = await session.call_tool("broaden_spectrum", {"filename": "large.csv"})
        assert result.isError and "10,000 transitions" in str(result.content)
        with (data_dir / "oversized.csv").open("wb") as stream:
            stream.truncate(MAX_FILE_BYTES + 1)
        result = await session.call_tool("inspect_transitions", {"filename": "oversized.csv"})
        assert result.isError and "40 MiB" in str(result.content)
        def broken_parser(*args):
            raise RuntimeError("Private implementation /secret/server/path")
        monkeypatch.setattr("orbital_viewer.mcp_server.read_cube", broken_parser)
        result = await session.call_tool("inspect_cube", {"filename": "signed-field.cube"})
        assert result.isError and "Private" not in str(result.content) and "/secret" not in str(result.content)


@pytest.mark.anyio
async def test_bohr_single_orbital_and_sampling_warning(data_dir):
    cube = (data_dir / "signed-field.cube").read_text().replace("-2 ", "2 ")
    cube = cube.replace("1 0 0 0", "-1 0 0 0", 1).replace("-1 -1 -1 -1", "1 244\n-1 -1 -1 -1")
    (data_dir / "bohr.cube").write_text(cube)
    async with create_connected_server_and_client_session(create_server(data_dir)) as session:
        result = await session.call_tool("inspect_cube", {"filename": "bohr.cube"})
        assert not result.isError
        assert result.structuredContent["axes"][1] == pytest.approx([BOHR / 2, BOHR, 0])
        result = await session.call_tool("broaden_spectrum", {"filename": "transitions.csv", "fwhm_ev": 1e-5})
        assert not result.isError
        assert any("Sampling warning" in note for note in result.structuredContent["caveats"])


@pytest.mark.parametrize("filename", ["../outside.csv", "/tmp/outside.csv", "C:/outside.csv", "C:outside.csv", "\\\\host\\share\\outside.csv", "nested/../../outside.csv", "nul\0.csv"])
def test_path_restrictions(data_dir, filename):
    with pytest.raises(FileAccessError, match="relative"):
        LocalFiles(data_dir).read_text(filename, {".csv"})


def test_file_size_type_encoding_and_symlink_boundaries(data_dir, tmp_path):
    files = LocalFiles(data_dir)
    large = data_dir / "large.csv"
    with large.open("wb") as stream:
        stream.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises(FileAccessError, match="40 MiB"):
        files.read_text("large.csv", {".csv"})
    (data_dir / "directory.csv").mkdir()
    with pytest.raises(FileAccessError, match="regular file"):
        files.read_text("directory.csv", {".csv"})
    (data_dir / "bad.csv").write_bytes(b"\xff")
    with pytest.raises(FileAccessError, match="UTF-8"):
        files.read_text("bad.csv", {".csv"})
    with pytest.raises(FileAccessError, match="Unsupported"):
        files.read_text("secrets.txt", {".csv"})
    outside = tmp_path / "outside.csv"
    outside.write_text("secret")
    try:
        (data_dir / "escape.csv").symlink_to(outside)
        (data_dir / "escape-dir").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    for filename in ("escape.csv", "escape-dir/outside.csv"):
        with pytest.raises(FileAccessError, match="inside"):
            files.read_text(filename, {".csv"})


def test_no_streamlit_import_and_data_directory_required(tmp_path):
    result = subprocess.run([sys.executable, "-c", "from orbital_viewer.mcp_server import create_server; import sys; assert 'streamlit' not in sys.modules"], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([sys.executable, "-m", "orbital_viewer.mcp_server"], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and "--data-dir" in result.stderr and result.stdout == ""


def test_read_growth_and_export_limits(data_dir, tmp_path, monkeypatch):
    from types import SimpleNamespace
    import stat
    from orbital_viewer import mcp_files
    files = LocalFiles(data_dir, tmp_path / "exports")
    monkeypatch.setattr(mcp_files, "MAX_FILE_BYTES", 64)
    (data_dir / "grown.csv").write_bytes(b"x" * 65)
    # Simulate a file growing after the descriptor's size check.
    with monkeypatch.context() as patch:
        patch.setattr(mcp_files.os, "fstat", lambda fd: SimpleNamespace(st_mode=stat.S_IFREG, st_size=0))
        with pytest.raises(FileAccessError, match="40 MiB"):
            files.read_text("grown.csv", {".csv"})
    monkeypatch.setattr(mcp_files, "MAX_EXPORT_BYTES", 64)
    with pytest.raises(FileAccessError, match="100 MiB"):
        files.export("x" * 65, ".html")
    assert not files.output_dir.exists()
    files.output_dir.write_text("existing content")
    with pytest.raises(FileAccessError, match="Could not write"):
        files.export("new content", ".csv")
    assert files.output_dir.read_text() == "existing content"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX special-file check")
def test_fifo_is_rejected_without_blocking(data_dir):
    import os
    os.mkfifo(data_dir / "pipe.csv")
    with pytest.raises(FileAccessError, match="regular file"):
        LocalFiles(data_dir).read_text("pipe.csv", {".csv"})
