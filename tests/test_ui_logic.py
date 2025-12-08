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
    args.attachment = []

    # Call the delete function
    zenoh_cli.delete(mock_zenoh_session, None, None, args)

    # Verify delete was called for each key
    assert mock_zenoh_session.delete.call_count == 2
    mock_zenoh_session.delete.assert_any_call("test/key1", attachment=None)
    mock_zenoh_session.delete.assert_any_call("test/key2", attachment=None)


def test_put_command(mock_zenoh_session):
    """Test the put command with various scenarios."""
    # Test simple put
    args = MagicMock()
    args.key = "test/key"
    args.value = "test_value"
    args.line = None
    args.encoder = "text"
    args.attachment = []
    args.attachment_from_line = []

    zenoh_cli.put(mock_zenoh_session, None, None, args)
    mock_zenoh_session.put.assert_called_once_with(
        key_expr="test/key", payload=b"test_value", attachment=None
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
            key_expr="test/line", payload=b"test_line_value", attachment=None
        )


def test_get_command(mock_zenoh_session, capsys):
    """Test the get command."""
    # Create mock get response
    mock_response = MagicMock()
    mock_response.ok.key_expr = "test/key"
    mock_response.ok.payload.to_bytes.return_value = b"test_value"
    mock_response.ok.attachment = None
    mock_zenoh_session.get.return_value = [mock_response]

    # Setup arguments
    args = MagicMock()
    args.selector = "test/*"
    args.value = None
    args.line = "{value}"
    args.encoder = "text"
    args.decoder = "text"
    args.attachment = []

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
    sample.attachment = None

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
    with (
        patch("zenoh.scout"),
        patch("matplotlib.pyplot.show"),
        patch("networkx.spring_layout"),
        patch("networkx.draw_networkx"),
        patch("networkx.draw_networkx_labels"),
        patch("networkx.draw_networkx_edge_labels"),
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
    with (
        patch("sys.argv", ["zenoh", "info"]),
        patch("zenoh.open"),
        patch("zenoh.Config") as mock_config,
        patch("zenoh_cli.info") as mock_info_func,
    ):
        # Call main
        zenoh_cli.main()

        # Verify config was created
        mock_config.assert_called_once()

        # Verify info function was called
        mock_info_func.assert_called_once()


# Attachment functionality tests


def test_parse_attachments():
    """Test parsing attachments from command line arguments."""
    # Test empty attachments
    assert zenoh_cli.parse_attachments([]) is None
    assert zenoh_cli.parse_attachments(None) is None

    # Test single attachment
    result = zenoh_cli.parse_attachments(["key=value"])
    assert result == {"key": "value"}

    # Test multiple attachments
    result = zenoh_cli.parse_attachments(["key1=value1", "key2=value2"])
    assert result == {"key1": "value1", "key2": "value2"}

    # Test value with equals sign
    result = zenoh_cli.parse_attachments(["key=value=with=equals"])
    assert result == {"key": "value=with=equals"}

    # Test invalid format (no equals sign)
    with pytest.raises(ValueError) as exc_info:
        zenoh_cli.parse_attachments(["invalid"])
    assert "Invalid attachment format" in str(exc_info.value)


def test_format_attachments_json():
    """Test formatting attachments as JSON."""
    # Test None attachment
    assert zenoh_cli.format_attachments_json(None) == "{}"

    # Test with mock attachment that returns key-value pairs
    mock_attachment = [
        (MagicMock(to_string=lambda: "key1"), MagicMock(to_string=lambda: "value1")),
        (MagicMock(to_string=lambda: "key2"), MagicMock(to_string=lambda: "value2")),
    ]
    result = zenoh_cli.format_attachments_json(mock_attachment)
    parsed = json.loads(result)
    assert parsed == {"key1": "value1", "key2": "value2"}


def test_format_attachment_value():
    """Test extracting a specific attachment value."""
    # Test None attachment
    assert zenoh_cli.format_attachment_value(None, "key") == ""

    # Test with mock attachment
    mock_key = MagicMock()
    mock_key.to_string.return_value = "mykey"
    mock_value = MagicMock()
    mock_value.to_string.return_value = "myvalue"
    mock_attachment = [(mock_key, mock_value)]

    assert zenoh_cli.format_attachment_value(mock_attachment, "mykey") == "myvalue"
    assert zenoh_cli.format_attachment_value(mock_attachment, "nonexistent") == ""


def test_put_with_attachments(mock_zenoh_session):
    """Test put command with attachments."""
    args = MagicMock()
    args.key = "test/key"
    args.value = "test_value"
    args.line = None
    args.encoder = "text"
    args.attachment = ["source=device1", "priority=high"]
    args.attachment_from_line = []

    zenoh_cli.put(mock_zenoh_session, None, None, args)

    mock_zenoh_session.put.assert_called_once_with(
        key_expr="test/key",
        payload=b"test_value",
        attachment={"source": "device1", "priority": "high"},
    )


def test_delete_with_attachments(mock_zenoh_session):
    """Test delete command with attachments."""
    args = MagicMock()
    args.key = ["test/key"]
    args.attachment = ["reason=expired"]

    zenoh_cli.delete(mock_zenoh_session, None, None, args)

    mock_zenoh_session.delete.assert_called_once_with(
        "test/key", attachment={"reason": "expired"}
    )


def test_get_with_attachments(mock_zenoh_session, capsys):
    """Test get command with attachments."""
    # Create mock response
    mock_response = MagicMock()
    mock_response.ok.key_expr = "test/key"
    mock_response.ok.payload.to_bytes.return_value = b"test_value"
    mock_response.ok.attachment = None
    mock_zenoh_session.get.return_value = [mock_response]

    args = MagicMock()
    args.selector = "test/*"
    args.value = None
    args.line = "{value}"
    args.encoder = "text"
    args.decoder = "text"
    args.attachment = ["request-id=abc123"]

    zenoh_cli.get(mock_zenoh_session, None, None, args)

    # Verify get was called with attachment
    mock_zenoh_session.get.assert_called_once()
    call_kwargs = mock_zenoh_session.get.call_args[1]
    assert call_kwargs["attachment"] == {"request-id": "abc123"}


def test_put_attachment_from_line(mock_zenoh_session):
    """Test put command with --attachment-from-line."""
    args = MagicMock()
    args.key = None
    args.value = None
    args.line = "id={id} key={key} value={value}"
    args.encoder = "text"
    args.attachment = []
    args.attachment_from_line = ["id"]

    with patch("sys.stdin", io.StringIO("id=device1 key=sensor/temp value=23.5")):
        zenoh_cli.put(mock_zenoh_session, None, None, args)

    mock_zenoh_session.put.assert_called_once_with(
        key_expr="sensor/temp",
        payload=b"23.5",
        attachment={"id": "device1"},
    )


def test_output_format_with_attachment(capsys):
    """Test _print_sample_to_stdout with attachment formatting."""
    # Create mock sample with attachment
    sample = MagicMock()
    sample.key_expr = "test/key"
    sample.payload.to_bytes.return_value = b"test_value"

    # Create mock attachment
    mock_key = MagicMock()
    mock_key.to_string.return_value = "source"
    mock_value = MagicMock()
    mock_value.to_string.return_value = "device1"
    sample.attachment = [(mock_key, mock_value)]

    # Test {attachment:KEY} format
    zenoh_cli._print_sample_to_stdout(sample, "{key}: {value} (source={attachment:source})", "text")
    captured = capsys.readouterr()
    assert "test/key: test_value (source=device1)" in captured.out


def test_output_format_with_all_attachments(capsys):
    """Test _print_sample_to_stdout with {attachment} format."""
    # Create mock sample with attachment
    sample = MagicMock()
    sample.key_expr = "test/key"
    sample.payload.to_bytes.return_value = b"test_value"

    # Create mock attachment with multiple keys
    mock_key1 = MagicMock()
    mock_key1.to_string.return_value = "key1"
    mock_value1 = MagicMock()
    mock_value1.to_string.return_value = "value1"
    mock_key2 = MagicMock()
    mock_key2.to_string.return_value = "key2"
    mock_value2 = MagicMock()
    mock_value2.to_string.return_value = "value2"
    sample.attachment = [(mock_key1, mock_value1), (mock_key2, mock_value2)]

    zenoh_cli._print_sample_to_stdout(sample, "{value} [{attachment}]", "text")
    captured = capsys.readouterr()
    # Check that output contains JSON-formatted attachments
    assert "test_value" in captured.out
    assert '"key1": "value1"' in captured.out
    assert '"key2": "value2"' in captured.out
