import pytest
import sys
from io import StringIO
from zenoh_cli import _print_sample_to_stdout, DECODERS


class MockPayload:
    def __init__(self, data):
        self._data = data

    def to_bytes(self):
        return self._data


class MockSample:
    def __init__(self, key_expr, payload):
        self.key_expr = key_expr
        self.payload = MockPayload(payload)


def test_print_sample_to_stdout_text_decoder(monkeypatch):
    # Capture stdout
    output = StringIO()
    monkeypatch.setattr(sys, "stdout", output)

    # Create a mock sample
    sample = MockSample("test/topic", b"hello world")

    # Call the function
    _print_sample_to_stdout(sample, "{key}: {value}", "text")

    # Check output
    assert output.getvalue().strip() == "test/topic: hello world"


def test_print_sample_to_stdout_base64_decoder(monkeypatch):
    # Capture stdout
    output = StringIO()
    monkeypatch.setattr(sys, "stdout", output)

    # Create a mock sample with base64 encoded bytes
    sample = MockSample("test/base64", b"\xde\xad\xbe\xef")

    # Call the function
    _print_sample_to_stdout(sample, "{key}: {value}", "base64")

    # Check output (the payload will be base64 encoded)
    assert output.getvalue().strip() == "test/base64: 3q2+7w=="


def test_print_sample_to_stdout_json_decoder(monkeypatch):
    # Capture stdout
    output = StringIO()
    monkeypatch.setattr(sys, "stdout", output)

    # Create a mock sample with JSON payload
    json_payload = b'{"name": "test", "value": 42}'
    sample = MockSample("test/json", json_payload)

    # Call the function
    _print_sample_to_stdout(sample, "{key}: {value}", "json")

    # Check output (should be a single-line, formatted JSON)
    assert output.getvalue().strip() == 'test/json: {"name": "test", "value": 42}'


def test_print_sample_to_stdout_custom_format(monkeypatch):
    # Capture stdout
    output = StringIO()
    monkeypatch.setattr(sys, "stdout", output)

    # Create a mock sample
    sample = MockSample("test/custom", b"hello")

    # Call the function with a custom format
    _print_sample_to_stdout(sample, "Key is {key}, Value is {value}!", "text")

    # Check output
    assert output.getvalue().strip() == "Key is test/custom, Value is hello!"


def test_print_sample_to_stdout_decoder_exception(monkeypatch, caplog):
    # Capture stdout
    output = StringIO()
    monkeypatch.setattr(sys, "stdout", output)

    # Create a mock sample
    sample = MockSample("test/error", b"some bytes")

    # Mock a decoder that raises an exception
    def mock_raise_decoder(key, value):
        raise ValueError("Decoder failed")

    # Temporarily replace the text decoder
    original_decoder = DECODERS["text"]
    DECODERS["text"] = mock_raise_decoder

    try:
        # Call the function and check logging
        _print_sample_to_stdout(sample, "{key}: {value}", "text")

        # Verify no output was written
        assert output.getvalue().strip() == ""

        # Check that an exception was logged
        assert "Decoder (text) failed, skipping!" in caplog.text
    finally:
        # Restore the original decoder
        DECODERS["text"] = original_decoder
