import pytest
import sys
import os
import json
import io
import contextlib
import tempfile
from unittest.mock import MagicMock, patch, call

import zenoh
import networkx as nx

# Import the main module to test
import zenoh_cli


def test_gather_plugins():
    """Test the plugin gathering functionality."""
    encoder_plugins, decoder_plugins = zenoh_cli.gather_plugins()

    # Check that basic encoders and decoders are present
    assert "text" in zenoh_cli.ENCODERS
    assert "base64" in zenoh_cli.ENCODERS
    assert "json" in zenoh_cli.ENCODERS

    assert "text" in zenoh_cli.DECODERS
    assert "base64" in zenoh_cli.DECODERS
    assert "json" in zenoh_cli.DECODERS


def test_codec_functions():
    """Test the built-in codec functions."""
    # Text codec
    key = "test/key"
    text_value = "Hello, World!"
    encoded_text = zenoh_cli.encode_from_text(key, text_value)
    assert zenoh_cli.decode_to_text(key, encoded_text) == text_value

    # Base64 codec
    base64_value = "SGVsbG8sIFdvcmxkIQ=="  # Base64 encoded "Hello, World!"
    encoded_base64 = zenoh_cli.encode_from_base64(key, base64_value)
    assert zenoh_cli.decode_to_base64(key, encoded_base64) == base64_value

    # JSON codec
    json_value = '{"name": "test", "value": 42}'
    encoded_json = zenoh_cli.encode_from_json(key, json_value)
    decoded_json = zenoh_cli.decode_to_json(key, encoded_json)
    assert json.loads(decoded_json) == json.loads(json_value)
