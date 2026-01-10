import pytest
import sys
import io
import json
from unittest.mock import MagicMock, patch, call
from datetime import datetime

import zenoh

# Import the main module to test
import zenoh_cli


@pytest.fixture
def mock_zenoh_session():
    """Fixture to create a mock Zenoh session with liveliness support."""
    with patch("zenoh.open") as mock_open:
        mock_session = MagicMock()
        mock_liveliness = MagicMock()
        mock_session.liveliness.return_value = mock_liveliness
        mock_open.return_value.__enter__.return_value = mock_session
        yield mock_session


def test_put_with_explicit_liveliness_key(mock_zenoh_session):
    """Test put command with explicit liveliness key."""
    args = MagicMock()
    args.key = "test/key"
    args.value = "test_value"
    args.line = None
    args.liveliness = "liveliness/key"
    args.encoder = "text"

    mock_token = MagicMock()
    mock_zenoh_session.liveliness().declare_token.return_value = mock_token

    zenoh_cli.put(mock_zenoh_session, None, None, args)

    # Verify liveliness token was declared
    mock_zenoh_session.liveliness().declare_token.assert_called_once_with("liveliness/key")

    # Verify put was called
    mock_zenoh_session.put.assert_called_once()

    # Verify token was undeclared
    mock_token.undeclare.assert_called_once()


def test_put_with_bare_liveliness_flag(mock_zenoh_session):
    """Test put command with bare --liveliness flag (uses -k value)."""
    args = MagicMock()
    args.key = "test/key"
    args.value = "test_value"
    args.line = None
    args.liveliness = True
    args.encoder = "text"

    mock_token = MagicMock()
    mock_zenoh_session.liveliness().declare_token.return_value = mock_token

    zenoh_cli.put(mock_zenoh_session, None, None, args)

    # Verify liveliness token was declared with the same key as -k
    mock_zenoh_session.liveliness().declare_token.assert_called_once_with("test/key")

    # Verify put was called
    mock_zenoh_session.put.assert_called_once()

    # Verify token was undeclared
    mock_token.undeclare.assert_called_once()


def test_put_with_bare_liveliness_no_key_error():
    """Test put command with bare --liveliness but no -k flag with --line raises error."""
    mock_parser = MagicMock()
    # Make parser.error raise SystemExit like the real implementation
    mock_parser.error.side_effect = SystemExit(2)

    args = MagicMock()
    args.key = None
    args.value = "{value}"
    args.line = "{key}: {value}"
    args.liveliness = True
    args.encoder = "text"

    with pytest.raises(SystemExit):
        zenoh_cli.put(None, None, mock_parser, args)

    # Verify parser.error was called
    mock_parser.error.assert_called_once()
    assert "Cannot infer liveliness key" in str(mock_parser.error.call_args)


def test_put_without_liveliness(mock_zenoh_session):
    """Test put command without liveliness flag."""
    args = MagicMock()
    args.key = "test/key"
    args.value = "test_value"
    args.line = None
    args.liveliness = None
    args.encoder = "text"

    zenoh_cli.put(mock_zenoh_session, None, None, args)

    # Verify liveliness token was NOT declared
    mock_zenoh_session.liveliness().declare_token.assert_not_called()

    # Verify put was still called
    mock_zenoh_session.put.assert_called_once()


def test_subscribe_with_explicit_liveliness_key(mock_zenoh_session):
    """Test subscribe command with explicit liveliness key."""
    args = MagicMock()
    args.key = ["test/key"]
    args.line = "{value}"
    args.liveliness = "liveliness/key"
    args.decoder = "text"

    mock_token = MagicMock()
    mock_zenoh_session.liveliness().declare_token.return_value = mock_token

    # Simulate KeyboardInterrupt to exit the while loop
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.subscribe(mock_zenoh_session, None, None, args)

    # Verify liveliness token was declared
    mock_zenoh_session.liveliness().declare_token.assert_called_once_with("liveliness/key")

    # Verify subscriber was created
    mock_zenoh_session.declare_subscriber.assert_called_once()

    # Verify token was undeclared
    mock_token.undeclare.assert_called_once()


def test_subscribe_with_bare_liveliness_single_key(mock_zenoh_session):
    """Test subscribe command with bare --liveliness and single key."""
    args = MagicMock()
    args.key = ["test/key"]
    args.line = "{value}"
    args.liveliness = True
    args.decoder = "text"

    mock_token = MagicMock()
    mock_zenoh_session.liveliness().declare_token.return_value = mock_token

    # Simulate KeyboardInterrupt to exit the while loop
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.subscribe(mock_zenoh_session, None, None, args)

    # Verify liveliness token was declared with the same key
    mock_zenoh_session.liveliness().declare_token.assert_called_once_with("test/key")

    # Verify token was undeclared
    mock_token.undeclare.assert_called_once()


def test_subscribe_with_bare_liveliness_multiple_keys_error():
    """Test subscribe command with bare --liveliness and multiple keys raises error."""
    mock_parser = MagicMock()
    # Make parser.error raise SystemExit like the real implementation
    mock_parser.error.side_effect = SystemExit(2)

    args = MagicMock()
    args.key = ["test/key1", "test/key2"]
    args.line = "{value}"
    args.liveliness = True
    args.decoder = "text"

    with pytest.raises(SystemExit):
        zenoh_cli.subscribe(None, None, mock_parser, args)

    # Verify parser.error was called
    mock_parser.error.assert_called_once()
    assert "Cannot infer liveliness key" in str(mock_parser.error.call_args)


def test_subscribe_without_liveliness(mock_zenoh_session):
    """Test subscribe command without liveliness flag."""
    args = MagicMock()
    args.key = ["test/key"]
    args.line = "{value}"
    args.liveliness = None
    args.decoder = "text"

    # Simulate KeyboardInterrupt to exit the while loop
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.subscribe(mock_zenoh_session, None, None, args)

    # Verify liveliness token was NOT declared
    mock_zenoh_session.liveliness().declare_token.assert_not_called()

    # Verify subscriber was still created
    mock_zenoh_session.declare_subscriber.assert_called_once()


def test_liveliness_get_default_format(mock_zenoh_session, capsys):
    """Test liveliness get command with default format."""
    args = MagicMock()
    args.key = "test/**"
    args.timeout = 10.0
    args.line = None
    args.json = False

    # Mock liveliness get response
    mock_response = MagicMock()
    mock_response.ok = MagicMock()
    mock_response.ok.key_expr = "test/key1"
    mock_response.ok.kind = zenoh.SampleKind.PUT
    mock_zenoh_session.liveliness().get.return_value = [mock_response]

    zenoh_cli.liveliness_get(mock_zenoh_session, None, None, args)

    # Capture output
    captured = capsys.readouterr()
    assert "[ALIVE] test/key1" in captured.out


def test_liveliness_get_custom_format(mock_zenoh_session, capsys):
    """Test liveliness get command with custom format."""
    args = MagicMock()
    args.key = "test/**"
    args.timeout = 10.0
    args.line = "Key: {key}, Status: {status}"
    args.json = False

    # Mock liveliness get response
    mock_response = MagicMock()
    mock_response.ok = MagicMock()
    mock_response.ok.key_expr = "test/key1"
    mock_response.ok.kind = zenoh.SampleKind.PUT
    mock_zenoh_session.liveliness().get.return_value = [mock_response]

    zenoh_cli.liveliness_get(mock_zenoh_session, None, None, args)

    # Capture output
    captured = capsys.readouterr()
    assert "Key: test/key1, Status: ALIVE" in captured.out


def test_liveliness_get_json_format(mock_zenoh_session, capsys):
    """Test liveliness get command with JSON format."""
    args = MagicMock()
    args.key = "test/**"
    args.timeout = 10.0
    args.line = None
    args.json = True

    # Mock liveliness get response
    mock_response = MagicMock()
    mock_response.ok = MagicMock()
    mock_response.ok.key_expr = "test/key1"
    mock_response.ok.kind = zenoh.SampleKind.PUT
    mock_zenoh_session.liveliness().get.return_value = [mock_response]

    with patch("zenoh_cli.datetime") as mock_datetime:
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 12, 0, 0)
        zenoh_cli.liveliness_get(mock_zenoh_session, None, None, args)

    # Capture output
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["key"] == "test/key1"
    assert output["status"] == "ALIVE"
    assert "timestamp" in output


def test_liveliness_sub_with_history(mock_zenoh_session):
    """Test liveliness subscribe command with history flag."""
    args = MagicMock()
    args.key = "test/**"
    args.line = None
    args.json = False
    args.history = True

    # Simulate KeyboardInterrupt to exit the while loop
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.liveliness_sub(mock_zenoh_session, None, None, args)

    # Verify declare_subscriber was called with history=True
    mock_zenoh_session.liveliness().declare_subscriber.assert_called_once()
    call_args = mock_zenoh_session.liveliness().declare_subscriber.call_args
    assert call_args[1]["history"] is True


def test_liveliness_sub_without_history(mock_zenoh_session):
    """Test liveliness subscribe command without history flag."""
    args = MagicMock()
    args.key = "test/**"
    args.line = None
    args.json = False
    args.history = False

    # Simulate KeyboardInterrupt to exit the while loop
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.liveliness_sub(mock_zenoh_session, None, None, args)

    # Verify declare_subscriber was called with history=False
    mock_zenoh_session.liveliness().declare_subscriber.assert_called_once()
    call_args = mock_zenoh_session.liveliness().declare_subscriber.call_args
    assert call_args[1]["history"] is False


def test_liveliness_sub_alive_status(mock_zenoh_session, capsys):
    """Test liveliness subscribe callback with ALIVE status."""
    args = MagicMock()
    args.key = "test/**"
    args.line = None
    args.json = False
    args.history = False

    # Capture the listener callback
    listener_callback = None

    def capture_listener(key, callback, **kwargs):
        nonlocal listener_callback
        listener_callback = callback
        return MagicMock()

    mock_zenoh_session.liveliness().declare_subscriber.side_effect = capture_listener

    # Start the subscribe (will capture the listener)
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.liveliness_sub(mock_zenoh_session, None, None, args)

    # Now call the listener with a mock sample
    mock_sample = MagicMock()
    mock_sample.key_expr = "test/key1"
    mock_sample.kind = zenoh.SampleKind.PUT
    listener_callback(mock_sample)

    # Capture output
    captured = capsys.readouterr()
    assert "[ALIVE] test/key1" in captured.out


def test_liveliness_sub_dropped_status(mock_zenoh_session, capsys):
    """Test liveliness subscribe callback with DROPPED status."""
    args = MagicMock()
    args.key = "test/**"
    args.line = None
    args.json = False
    args.history = False

    # Capture the listener callback
    listener_callback = None

    def capture_listener(key, callback, **kwargs):
        nonlocal listener_callback
        listener_callback = callback
        return MagicMock()

    mock_zenoh_session.liveliness().declare_subscriber.side_effect = capture_listener

    # Start the subscribe (will capture the listener)
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.liveliness_sub(mock_zenoh_session, None, None, args)

    # Now call the listener with a DELETE sample
    mock_sample = MagicMock()
    mock_sample.key_expr = "test/key1"
    mock_sample.kind = zenoh.SampleKind.DELETE
    listener_callback(mock_sample)

    # Capture output
    captured = capsys.readouterr()
    assert "[DROPPED] test/key1" in captured.out


def test_liveliness_token_command(mock_zenoh_session):
    """Test liveliness token command."""
    args = MagicMock()
    args.key = "test/token"

    mock_token = MagicMock()
    mock_zenoh_session.liveliness().declare_token.return_value = mock_token

    # Simulate KeyboardInterrupt to exit the while loop
    with pytest.raises(SystemExit):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            zenoh_cli.liveliness_token(mock_zenoh_session, None, None, args)

    # Verify token was declared
    mock_zenoh_session.liveliness().declare_token.assert_called_once_with("test/token")

    # Verify token was undeclared
    mock_token.undeclare.assert_called_once()


def test_print_liveliness_to_stdout_default_format(capsys):
    """Test _print_liveliness_to_stdout with default format."""
    zenoh_cli._print_liveliness_to_stdout("test/key", "ALIVE", None, False)

    captured = capsys.readouterr()
    assert "[ALIVE] test/key" in captured.out


def test_print_liveliness_to_stdout_custom_format(capsys):
    """Test _print_liveliness_to_stdout with custom format."""
    zenoh_cli._print_liveliness_to_stdout(
        "test/key", "ALIVE", "Status: {status}, Key: {key}", False
    )

    captured = capsys.readouterr()
    assert "Status: ALIVE, Key: test/key" in captured.out


def test_print_liveliness_to_stdout_json_format(capsys):
    """Test _print_liveliness_to_stdout with JSON format."""
    with patch("zenoh_cli.datetime") as mock_datetime:
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 12, 0, 0)
        zenoh_cli._print_liveliness_to_stdout("test/key", "ALIVE", None, True)

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["key"] == "test/key"
    assert output["status"] == "ALIVE"
    assert output["timestamp"] == "2024-01-01T12:00:00Z"


def test_put_with_liveliness_and_stdin(mock_zenoh_session):
    """Test put command with liveliness and stdin line parsing."""
    args = MagicMock()
    args.key = None
    args.value = None
    args.line = "{key}: {value}"
    args.liveliness = "producer/token"
    args.encoder = "text"

    mock_token = MagicMock()
    mock_zenoh_session.liveliness().declare_token.return_value = mock_token

    # Mock stdin
    test_input = "test/key1: value1\ntest/key2: value2\n"
    with patch("sys.stdin", io.StringIO(test_input)):
        zenoh_cli.put(mock_zenoh_session, None, None, args)

    # Verify liveliness token was declared
    mock_zenoh_session.liveliness().declare_token.assert_called_once_with("producer/token")

    # Verify put was called twice
    assert mock_zenoh_session.put.call_count == 2

    # Verify token was undeclared
    mock_token.undeclare.assert_called_once()
