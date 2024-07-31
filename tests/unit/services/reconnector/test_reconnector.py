"""
Copyright (c) 2023 Proton AG

This file is part of Proton VPN.

Proton VPN is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Proton VPN is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with ProtonVPN.  If not, see <https://www.gnu.org/licenses/>.
"""
from unittest.mock import Mock, patch, PropertyMock

import pytest

from proton.vpn.connection import states, events
from proton.vpn.connection.exceptions import AuthenticationError
from proton.vpn.core.connection import VPNConnectorWrapper

from proton.vpn.app.gtk.services import VPNDataRefresher
from proton.vpn.app.gtk.services.reconnector.network_monitor import NetworkMonitor
from proton.vpn.app.gtk.services.reconnector.reconnector import VPNReconnector
from proton.vpn.app.gtk.services.reconnector.session_monitor import SessionMonitor
from proton.vpn.app.gtk.services.reconnector.vpn_monitor import VPNMonitor
from proton.vpn.app.gtk.utils.executor import AsyncExecutor
from tests.unit.testing_utils import process_gtk_events


@pytest.fixture
def async_executor():
    return Mock(AsyncExecutor)


@pytest.fixture
def vpn_connector():
    return Mock(VPNConnectorWrapper)


@pytest.fixture
def vpn_data_refresher():
    return Mock(VPNDataRefresher)


@pytest.fixture
def vpn_monitor():
    return Mock(VPNMonitor)


@pytest.fixture
def network_monitor():
    return Mock(NetworkMonitor)


@pytest.fixture
def session_monitor():
    return Mock(SessionMonitor)


def test_enable_enables_vpn_and_network_and_session_monitors(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    reconnector.enable()

    vpn_monitor.enable.assert_called_once()
    network_monitor.enable.assert_called_once()
    session_monitor.enable.assert_called_once()


def test_enable_raises_runtime_error_if_vpn_data_refresher_is_not_ready(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    """
    The reconnector retrieves the server list and the client configuration
    required to initiate a reconnection from its VPNDataRefresher instance.
    For this reason, it cannot be enabled if the VPNDataRefresher is not
    ready. That is, the VPNDataRefresher did not retrieve the server list
    and/or the client configuration yet.
    """
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    vpn_data_refresher.is_vpn_data_ready = False

    with pytest.raises(RuntimeError):
        reconnector.enable()


def test_disable_disables_vpn_and_network_and_session_monitors(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    reconnector.disable()

    vpn_monitor.disable.assert_called_once()
    network_monitor.disable.assert_called_once()
    session_monitor.disable.assert_called_once()


def test_did_vpn_drop_returns_false_if_there_is_not_a_vpn_connection(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    vpn_connector.current_connection = None
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    assert not reconnector.did_vpn_drop


@pytest.mark.parametrize("state", [
    state() for state in states.State.__subclasses__()
])
def test_did_vpn_drop_returns_true_only_if_the_current_connection_state_is_error(
        state,
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    vpn_connector.current_state = state
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    expected_result = isinstance(state, states.Error)
    assert reconnector.did_vpn_drop is expected_result


@pytest.mark.parametrize("did_vpn_drop, is_connection_error_fatal, scheduled_reconnection_expected", [
    (False, False, False),
    (True, False, False),
    (True, True, True)
])
def test_schedule_reconnection_is_called_once_network_connectivity_is_detected_only_if_vpn_connection_dropped_and_connection_error_is_not_fatal(
        did_vpn_drop, is_connection_error_fatal, scheduled_reconnection_expected,
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    with patch.object(VPNReconnector, "did_vpn_drop", new_callable=PropertyMock) as did_vpn_drop_patch, \
            patch.object(VPNReconnector, "is_connection_error_fatal", new_callable=PropertyMock) as is_connection_error_fatal_patch, \
            patch.object(VPNReconnector, "schedule_reconnection"):
        # Mock whether a VPN connection dropped happened or not
        did_vpn_drop_patch.return_value = did_vpn_drop
        # and whether reconnection is possible or not
        is_connection_error_fatal_patch.return_value = is_connection_error_fatal

        # Simulate network up.
        network_monitor.network_up_callback()

        assert reconnector.schedule_reconnection.called is scheduled_reconnection_expected


@pytest.mark.parametrize("did_vpn_drop, is_connection_error_fatal, scheduled_reconnection_expected", [
    (False, False, False),
    (True, False, False),
    (True, True, True)
])
def test_schedule_reconnection_is_called_once_user_session_is_unlocked_only_if_vpn_connection_dropped_and_connection_error_is_not_fatal(
        did_vpn_drop, is_connection_error_fatal, scheduled_reconnection_expected,
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    with patch.object(VPNReconnector, "did_vpn_drop", new_callable=PropertyMock) as did_vpn_drop_patch, \
            patch.object(VPNReconnector, "is_connection_error_fatal", new_callable=PropertyMock) as is_connection_error_fatal_patch, \
            patch.object(VPNReconnector, "schedule_reconnection"):
        # Mock whether a VPN connection dropped happened or not
        did_vpn_drop_patch.return_value = did_vpn_drop
        is_connection_error_fatal_patch.return_value = is_connection_error_fatal

        # Simulate user session unlocked.
        session_monitor.session_unlocked_callback()

        assert reconnector.schedule_reconnection.called is scheduled_reconnection_expected


@patch("proton.vpn.app.gtk.services.reconnector.reconnector.GLib")
def test_schedule_reconnection_only_schedule_a_reconnection_if_there_is_not_one_already_scheduled(
    glib_mock,
    vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    glib_mock.timeout_add_seconds.return_value = 1

    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    reconnection_scheduled = reconnector.schedule_reconnection()
    assert reconnection_scheduled
    glib_mock.timeout_add.assert_called_once()

    reconnection_scheduled = reconnector.schedule_reconnection()
    assert not reconnection_scheduled
    # assert that Glib was not called a second time.
    glib_mock.timeout_add.assert_called_once()


def test_on_vpn_drop_raises_exception_on_authentication_denied_error(
    vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    # Set current VPN state to authentication denied error, currently considered as a fatal error.
    vpn_connector.current_state = states.Error(
        context=states.StateContext(event=events.AuthDenied(context=None))
    )

    # Simulate a VPN drop.
    vpn_monitor.vpn_drop_callback(vpn_connector.current_state.context.event)

    # An authentication error should have been raised since we currently fail to reconnect in such case.
    with pytest.raises(AuthenticationError):
        process_gtk_events()


@patch("proton.vpn.app.gtk.services.reconnector.reconnector.random")
@patch("proton.vpn.app.gtk.services.reconnector.reconnector.GLib")
def test_on_vpn_drop_a_reconnection_attempt_is_scheduled_with_an_exponential_backoff_delay(
    glib_mock, random_mock,
    vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    """After each reconnection attempt, the backoff delay should increase
    exponentially."""
    VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )
    vpn_connector.current_state = states.Error()

    glib_mock.timeout_add_seconds.return_value = 1
    random_mock.uniform.return_value = 1  # Get rid of randomness.

    for number_of_attempts in range(4):
        vpn_monitor.vpn_drop_callback(vpn_connector.current_state.context.event)  # Simulate VPN drop.

        glib_mock.timeout_add.assert_called_once()
        delay_in_ms, reconnect_func = glib_mock.timeout_add.call_args_list[0].args

        # Assert that the backoff delay increases as expected after each reconnection attempt.
        expected_delay_in_ms = 2**number_of_attempts * 1000
        assert delay_in_ms == expected_delay_in_ms, \
            f"On reconnection attempt number {number_of_attempts} a " \
            f"backoff delay of {expected_delay_in_ms} ms was expected."

        # Simulate GLib running the scheduled reconnection attempt.
        reconnect_func()

        glib_mock.reset_mock()


@pytest.mark.parametrize("is_network_up,is_session_unlocked", [
    (True, False),
    (True, False),
    (False, False)
])
@patch("proton.vpn.app.gtk.services.reconnector.reconnector.random")
@patch("proton.vpn.app.gtk.services.reconnector.reconnector.GLib")
def test_reconnection_is_rescheduled_if_connection_error_is_not_fatal_when_network_is_down_or_session_is_locked(
    glib_mock, random_mock,
    is_network_up, is_session_unlocked,
    vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    """
    The requirements for a reconnection attempt are:
    1. that there is network connectivity and
    2. that the user session is unlocked (a requirement imposed by NM).
    If any of those requirements are not met, then the reconnection should not take place,
    and it should be rescheduled instead. This is what's tested by this test.
    """
    VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    # Set current VPN state to a non fatal error.
    vpn_connector.current_state = states.Error(
        context=states.StateContext(event=events.Timeout(context=None))
    )

    glib_mock.timeout_add_seconds.return_value = 1
    random_mock.uniform.return_value = 1  # Get rid of randomness.

    # Simulate VPN drop.
    vpn_monitor.vpn_drop_callback(vpn_connector.current_state.context.event)

    # Make sure a reconnection attempt is scheduled.
    glib_mock.timeout_add.assert_called_once()
    delay_in_ms, reconnect_func = glib_mock.timeout_add.call_args_list[0].args
    assert delay_in_ms == 1000

    # Simulate network up/down.
    network_monitor.is_network_up = is_network_up
    # Simulate session [un]locked
    session_monitor.is_session_unlocked = is_session_unlocked

    # Simulate GLib running the scheduled reconnection attempt.
    reconnect_func()

    # Assert that the reconnection did not happen (as network is down and/or session is locked)
    vpn_connector.connect.assert_not_called()

    # Assert that a new reconnection attempt was scheduled with the expected delay
    assert glib_mock.timeout_add.call_count == 2
    delay_in_ms, reconnect_func = glib_mock.timeout_add.call_args_list[1].args
    assert delay_in_ms == 2000


@patch("proton.vpn.app.gtk.services.reconnector.reconnector.random")
@patch("proton.vpn.app.gtk.services.reconnector.reconnector.GLib")
def test_on_vpn_up_resets_retry_counter_and_removes_pending_scheduled_attempt(
        glib_mock, random_mock,
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    """After the VPN connection has been restored, the retry counter that
    increases the backoff delay should be reset, and if there is a pending
    scheduled reconnection attempt then it should be unscheduled."""
    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    glib_mock.timeout_add_seconds.return_value = 1
    random_mock.uniform.return_value = 1  # Get rid of randomness.

    reconnector.schedule_reconnection()

    glib_mock.timeout_add.assert_called_once()
    delay_in_ms, reconnect_func = glib_mock.timeout_add.call_args_list[0].args

    # Simulate GLib running the scheduled reconnection attempt.
    reconnect_func()

    assert reconnector.retry_counter == 1

    # Schedule a pending reconnection attempt.
    reconnector.schedule_reconnection()

    assert reconnector.is_reconnection_scheduled

    vpn_monitor.vpn_up_callback()  # Simulate VPN up event.

    # Assert that the retry counter is reset
    assert reconnector.retry_counter == 0
    # and the pending scheduled connection has been unscheduled.
    assert not reconnector.is_reconnection_scheduled


def test_on_vpn_drop_trigger_force_refresh_after_expired_certificate_event_is_received(
    vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
):
    event = events.ExpiredCertificate()

    reconnector = VPNReconnector(
        vpn_connector, vpn_data_refresher, vpn_monitor, network_monitor, session_monitor, async_executor
    )

    vpn_monitor.vpn_drop_callback(event)
    vpn_data_refresher.force_refresh_certificate.assert_called_once()
