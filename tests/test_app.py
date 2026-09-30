"""Smoke-test the app's demo and empty upload workflow."""
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_demo_and_upload_modes() -> None:
    """Both entry points render without exceptions or fabricated uploaded results."""
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ['Orbital explorer', 'Absorption spectrum', 'Workflow & interpretation']
    app.sidebar.radio[0].set_value('My calculations').run()
    assert not app.exception
    assert any('Upload CUBE' in message.value for message in app.info)
