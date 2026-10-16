"""Offline rehearsal lifetime checks; no server, database or provider calls."""
import pytest
from run_milestone3_live import valid_lifetime


@pytest.mark.parametrize('seconds,minutes',[(1800,30),(7200,120),(7200,180),(60,30)])
def test_bounded_rehearsal_window(seconds,minutes):
    assert valid_lifetime(seconds,minutes)


@pytest.mark.parametrize('seconds,minutes',[(7201,180),(59,30),(7200,30),(1800,29),(1800,181),(True,30),(1800,30.0)])
def test_rehearsal_cannot_outlive_supported_interview(seconds,minutes):
    assert not valid_lifetime(seconds,minutes)
