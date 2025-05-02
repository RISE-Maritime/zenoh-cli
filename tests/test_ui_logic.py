import pytest
import sys
import os
import json
import io
import contextlib
import tempfile
from unittest.mock import MagicMock, patch, call, ANY

import zenoh
import networkx as nx

# Import the main module to test
import zenoh_cli


@pytest.fixture
def mock_zenoh_session():
    """Fixture to create a mock Zenoh session."""
    with patch("zenoh.open") as mock_open:
        mock_session = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_session
        yield mock_session


def test_info_command(mock_zenoh_session, capsys):
    """Test the info command."""
    # Setup mock session info
    mock_zenoh_session.zid.return_value = "test-zid"
    mock_zenoh_session.info.routers_zid.return_value = ["router1", "router2"]
    mock_zenoh_session.info.peers_zid.return_value = ["peer1", "peer2"]

    # Create mock arguments
    args = MagicMock()

    # Call the info function
    zenoh_cli.info(mock_zenoh_session, None, None, args)

    # Capture output
    captured = capsys.readouterr()

    # Check output
    assert "zid: test-zid" in captured.out
    assert "routers: ['router1', 'router2']" in captured.out
    assert "peers: ['peer1', 'peer2']" in captured.out


def test_scout_command(capsys):
    """Test the scout command with mocked scout functionality."""
    with patch("zenoh.scout") as mock_scout:
        # Create a mock scout with predefined hello responses
        mock_scout_instance = MagicMock()
        mock_scout.return_value = mock_scout_instance
        mock_scout_instance.__iter__.return_value = ["hello1", "hello2"]

        # Create mock arguments
        args = MagicMock()
        args.what = "peer|router"
        args.timeout = 1.0

        # Capture output
        with patch("threading.Timer") as mock_timer:
            # Create a lambda function matching the actual implementation
            mock_stop_func = lambda: mock_scout_instance.stop()
            mock_timer.return_value = MagicMock(stop=mock_stop_func)

            zenoh_cli.scout(None, None, None, args)

            # Verify timer was created with the correct stop function
            mock_timer.assert_called_once()
            assert mock_timer.call_args[0][0] == 1.0

            # Capture output
            captured = capsys.readouterr()

            # Check output
            assert "hello1" in captured.out
            assert "hello2" in captured.out


def test_delete_command(mock_zenoh_session):
    """Test the delete command."""
    # Create mock arguments
    args = MagicMock()
    args.key = ["test/key1", "test/key2"]

    # Call the delete function
    zenoh_cli.delete(mock_zenoh_session, None, None, args)

    # Verify delete was called for each key
    assert mock_zenoh_session.delete.call_count == 2
    mock_zenoh_session.delete.assert_any_call("test/key1")
    mock_zenoh_session.delete.assert_any_call("test/key2")


def test_put_command(mock_zenoh_session):
    """Test the put command with various scenarios."""
    # Test simple put
    args = MagicMock()
    args.key = "test/key"
    args.value = "test_value"
    args.line = None
    args.encoder = "text"

    zenoh_cli.put(mock_zenoh_session, None, None, args)
    mock_zenoh_session.put.assert_called_once_with(
        key_expr="test/key", payload=b"test_value"
    )

    # Reset mock
    mock_zenoh_session.put.reset_mock()

    # Test put with line parsing
    args.line = "{key}: {value}"
    args.key = None
    args.value = None

    # Simulate stdin
    with patch("sys.stdin", io.StringIO("test/line: test_line_value")):
        zenoh_cli.put(mock_zenoh_session, None, None, args)
        mock_zenoh_session.put.assert_called_once_with(
            key_expr="test/line", payload=b"test_line_value"
        )


def test_get_command(mock_zenoh_session, capsys):
    """Test the get command."""
    # Create mock get response
    mock_response = MagicMock()
    mock_response.ok.key_expr = "test/key"
    mock_response.ok.payload.to_bytes.return_value = b"test_value"
    mock_zenoh_session.get.return_value = [mock_response]

    # Setup arguments
    args = MagicMock()
    args.selector = "test/*"
    args.value = None
    args.line = "{value}"
    args.encoder = "text"
    args.decoder = "text"

    # Call get function
    zenoh_cli.get(mock_zenoh_session, None, None, args)

    # Capture output
    captured = capsys.readouterr()

    # Check output
    assert "test_value" in captured.out


def test_subscribe_command(mock_zenoh_session):
    """Test the subscribe command."""
    # Setup arguments
    args = MagicMock()
    args.key = ["test/key1", "test/key2"]
    args.line = "{value}"
    args.decoder = "text"

    # Simulate a sample
    sample = MagicMock()
    sample.key_expr = "test/key1"
    sample.payload.to_bytes.return_value = b"test_value"

    # Patch the time.sleep to prevent infinite loop
    with patch("time.sleep", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit):
            zenoh_cli.subscribe(mock_zenoh_session, None, None, args)

    # Verify subscribers were declared
    assert mock_zenoh_session.declare_subscriber.call_count == 2

    # Use assert_has_calls instead of pytest.any
    mock_zenoh_session.declare_subscriber.assert_has_calls(
        [call("test/key1", ANY), call("test/key2", ANY)], any_order=True
    )


def test_network_command(mock_zenoh_session):
    """Test the network command with mocked dependencies."""
    # Setup arguments
    args = MagicMock()
    args.metadata_field = "/name"

    # Mock required external dependencies
    with patch("zenoh.scout"), patch("matplotlib.pyplot.show"), patch(
        "networkx.spring_layout"
    ), patch("networkx.draw_networkx"), patch("networkx.draw_networkx_labels"), patch(
        "networkx.draw_networkx_edge_labels"
    ):
        # Setup mock session info and config
        mock_config = MagicMock()
        mock_config.get_json.return_value = "peer"
        mock_zenoh_session.info.zid.return_value = "test-zid"
        mock_zenoh_session.get.return_value = []

        # Call network function
        zenoh_cli.network(mock_zenoh_session, mock_config, None, args)


def test_main_function():
    """Test the main function with minimal mocking."""
    with patch("sys.argv", ["zenoh", "info"]), patch("zenoh.open"), patch(
        "zenoh.Config"
    ) as mock_config, patch("zenoh_cli.info") as mock_info_func:
        # Call main
        zenoh_cli.main()

        # Verify config was created
        mock_config.assert_called_once()

        # Verify info function was called
        mock_info_func.assert_called_once()
