"""Scientific data invariants and malformed-input regression tests."""
import numpy as np
import pytest
from orbital_viewer.data import BOHR, read_cube, read_transitions, broaden, demo_grid
from orbital_viewer.plots import orbital_figure


def cube(count: int = 2, nat: int = 1, values: str = '0 1 2 3 4 5 6 7') -> str:
    """Create a minimal CUBE fixture with nonzero origin and skewed axes."""
    return f"test\nfield\n{nat} 1 2 3\n{count} 1 0 0\n{count} .5 1 0\n{count} 0 0 1\n6 0 1 2 3\n" + ('1 244\n' if nat < 0 else '') + values


def test_cube_units_order_and_mo_record() -> None:
    """Preserve CUBE ordering, affine axes, unit conversion and orbital-ID skipping."""
    grid = read_cube(cube(nat=-1))
    np.testing.assert_allclose(grid.origin, np.array([1, 2, 3]) * BOHR)
    assert grid.values[1, 0, 1] == 5
    assert grid.axes[1, 0] == .5 * BOHR
    np.testing.assert_allclose(read_cube(cube(count=-2)).atoms[0, 2:], [1, 2, 3])


@pytest.mark.parametrize('text', [cube(values='1 2'), cube(values='nan 1 2 3 4 5 6 7'), 'broken', cube().replace('2 0 0 1', '-2 0 0 1')])
def test_invalid_cube(text: str) -> None:
    """Reject incomplete, non-finite and inconsistent-unit input."""
    with pytest.raises(ValueError):
        read_cube(text)


def test_spectrum_area_and_csv_validation() -> None:
    """Gaussian integral conserves oscillator strength, and bad CSV is rejected."""
    table = read_transitions('energy_ev,oscillator_strength\n4.241,.72\n', 'a.csv')
    x, y = broaden(table, .18)
    assert np.trapezoid(y, x) == pytest.approx(.72, rel=1e-5)
    for text in ['energy_ev,oscillator_strength\n-1,2', 'energy_ev,oscillator_strength\n1,-2', 'energy_ev,oscillator_strength\n1,nan', 'wrong,columns\n1,2']:
        with pytest.raises(ValueError):
            read_transitions(text, 'a.csv')


def test_mesh_has_both_phases() -> None:
    """Both surfaces survive extraction and no mesh exists above field extrema."""
    grid = demo_grid()
    fig = orbital_figure(grid, .05, .7, False)
    assert len(fig.data) == 2
    assert all(len(trace.x) > 100 for trace in fig.data)
    assert len(orbital_figure(grid, 100, .7, False).data) == 0
