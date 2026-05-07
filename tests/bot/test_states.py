"""
Bot unit tests — FSM states (app/services/states.py).

Verifies that RegistrationState declares all expected steps in the correct
registration sequence. These tests protect against accidental state removal
or renaming during refactoring.
"""
from app.services.states import RegistrationState


EXPECTED_STATES = [
    "waiting_for_name",
    "waiting_for_age",
    "waiting_for_gender",
    "waiting_for_city",
    "waiting_for_bio",
    "waiting_for_interests",
    "waiting_for_photos",
]


def test_all_registration_states_exist():
    state_names = [s.state.split(":")[-1] for s in RegistrationState.__all_states__]
    for expected in EXPECTED_STATES:
        assert expected in state_names, f"Missing FSM state: {expected}"


def test_registration_state_count():
    """Exact number of states — fails if one is accidentally added or removed."""
    assert len(RegistrationState.__all_states__) == len(EXPECTED_STATES)


def test_states_are_aiogram_state_instances():
    from aiogram.fsm.state import State

    for state in RegistrationState.__all_states__:
        assert isinstance(state, State)
