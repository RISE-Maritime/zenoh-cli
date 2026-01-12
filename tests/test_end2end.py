import pytest
import subprocess
import time
import threading
import queue
import os
import signal
import base64
import socket


@pytest.fixture
def zenoh_port():
    """Allocate an available port for the test"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def zenoh_cli_base():
    """Return base command with multicast scouting disabled"""
    return ["python", "-m", "zenoh_cli", "--cfg", "scouting/multicast/enabled:false"]


def run_zenoh_cli(command, port=None, listen=False, capture=True):
    """
    Helper function to run Zenoh CLI commands

    Args:
        command (list): List of command arguments to pass to the CLI
        port (int): Optional port for TCP connectivity
        listen (bool): If True, add --listen flag; if False, add --connect flag
        capture (bool): Whether to capture output

    Returns:
        subprocess.Popen or subprocess.CompletedProcess
    """
    full_command = zenoh_cli_base()

    if port is not None:
        if listen:
            full_command += ["--listen", f"tcp/127.0.0.1:{port}"]
        else:
            full_command += ["--connect", f"tcp/127.0.0.1:{port}"]

    full_command += command

    if capture:
        return subprocess.run(full_command, capture_output=True, text=True, timeout=10)
    else:
        # For long-running processes like subscribe
        return subprocess.Popen(
            full_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )


def capture_subprocess_output(process, output_queue):
    """
    Helper function to capture output from a subprocess

    Args:
        process (subprocess.Popen): Process to capture output from
        output_queue (queue.Queue): Queue to store output lines
    """
    try:
        for line in process.stdout:
            output_queue.put(line.strip())
    except Exception:
        pass
    finally:
        process.stdout.close()


def test_info_command():
    """
    Test the 'info' subcommand of the Zenoh CLI

    Verifies that:
    - The command runs successfully
    - Output contains expected information fields
    """
    result = run_zenoh_cli(["info"])

    assert result.returncode == 0, f"Command failed with error: {result.stderr}"
    assert "zid:" in result.stdout, "ZID information should be present"
    assert "routers:" in result.stdout, "Router information should be present"
    assert "peers:" in result.stdout, "Peer information should be present"


def test_scout_command():
    """
    Test the 'scout' subcommand of the Zenoh CLI

    Verifies that:
    - The command runs successfully
    - Scout produces some output
    """
    result = run_zenoh_cli(["scout"])

    assert result.returncode == 0, f"Command failed with error: {result.stderr}"
    # The scout command might not always produce output depending on network
    # So we'll just check it runs without error


def test_subscribe_and_put(zenoh_port):
    """
    End-to-end test for subscribe and put commands

    Verifies:
    - Can start a subscriber
    - Can put a value to a key
    - Subscriber receives the put value
    """
    # Setup output queue for subscriber
    output_queue = queue.Queue()

    # Key to use for this test
    test_key = "test/subscribe_put"
    test_value = "Hello, Zenoh Subscriber!"

    # Encode value to base64 (default decoder)
    base64_value = base64.b64encode(test_value.encode()).decode()

    # Start subscriber process with default base64 decoder (listening on port)
    subscriber_process = run_zenoh_cli(
        ["subscribe", "-k", test_key], port=zenoh_port, listen=True, capture=False
    )

    # Start output capture thread
    subscriber_thread = threading.Thread(
        target=capture_subprocess_output, args=(subscriber_process, output_queue)
    )
    subscriber_thread.start()

    # Give subscriber a moment to start
    time.sleep(1)

    try:
        # Put a value (connecting to subscriber's port)
        put_result = run_zenoh_cli(
            ["put", "-k", test_key, "-v", test_value], port=zenoh_port, listen=False
        )

        # Wait for potential network propagation
        time.sleep(1)

        # Check put was successful
        assert put_result.returncode == 0, f"Put command failed: {put_result.stderr}"

        # Try to get the value from queue with timeout
        try:
            received_value = output_queue.get(timeout=3)
            # Check if received value matches base64 encoded value
            assert (
                received_value == base64_value
            ), f"Received value {received_value} does not match expected base64 encoded value {base64_value}"
        except queue.Empty:
            pytest.fail("Did not receive expected value from subscriber")

    finally:
        # Cleanup: terminate subscriber process
        subscriber_process.send_signal(signal.SIGINT)
        subscriber_thread.join(timeout=2)
        subscriber_process.wait(timeout=2)


def test_subscribe_with_base64_decoding(zenoh_port):
    """
    Test subscribing with explicit base64 decoding

    Verifies:
    - Can subscribe and receive base64 encoded values
    """
    # Setup output queue for subscriber
    output_queue = queue.Queue()

    # Key to use for this test
    test_key = "test/base64_subscribe"
    test_value = "Zenoh Base64 Test Message"

    # Encode value to base64
    base64_value = base64.b64encode(test_value.encode()).decode()

    # Start subscriber process with explicit base64 decoder (listening on port)
    subscriber_process = run_zenoh_cli(
        ["subscribe", "-k", test_key, "--decoder", "base64"],
        port=zenoh_port,
        listen=True,
        capture=False,
    )

    # Start output capture thread
    subscriber_thread = threading.Thread(
        target=capture_subprocess_output, args=(subscriber_process, output_queue)
    )
    subscriber_thread.start()

    # Give subscriber a moment to start
    time.sleep(1)

    try:
        # Put base64 encoded value (connecting to subscriber's port)
        put_result = run_zenoh_cli(
            ["put", "-k", test_key, "-v", test_value], port=zenoh_port, listen=False
        )

        # Wait for potential network propagation
        time.sleep(1)

        # Check put was successful
        assert put_result.returncode == 0, f"Put command failed: {put_result.stderr}"

        # Try to get the value from queue with timeout
        try:
            received_value = output_queue.get(timeout=3)
            # Check if received value matches original test value
            assert (
                received_value == base64_value
            ), f"Received value {received_value} does not match original value {test_value}"
        except queue.Empty:
            pytest.fail("Did not receive expected value from subscriber")

    finally:
        # Cleanup: terminate subscriber process
        subscriber_process.send_signal(signal.SIGINT)
        subscriber_thread.join(timeout=2)
        subscriber_process.wait(timeout=2)


def test_subscribe_multiple_puts(zenoh_port):
    """
    Test subscribing to multiple puts with base64 encoding

    Verifies:
    - Can subscribe to a key
    - Can put multiple values
    - Subscriber receives all values in order
    """
    # Setup output queue for subscriber
    output_queue = queue.Queue()

    # Key to use for this test
    test_key = "test/multiple_puts"
    test_values = ["First message", "Second message", "Third message"]

    # Encode values to base64
    base64_values = [base64.b64encode(v.encode()).decode() for v in test_values]

    # Start subscriber process (listening on port)
    subscriber_process = run_zenoh_cli(
        ["subscribe", "-k", test_key], port=zenoh_port, listen=True, capture=False
    )

    # Start output capture thread
    subscriber_thread = threading.Thread(
        target=capture_subprocess_output, args=(subscriber_process, output_queue)
    )
    subscriber_thread.start()

    # Give subscriber a moment to start
    time.sleep(1)

    try:
        # Put multiple values (connecting to subscriber's port)
        for value in test_values:
            put_result = run_zenoh_cli(
                ["put", "-k", test_key, "-v", value], port=zenoh_port, listen=False
            )
            assert put_result.returncode == 0, f"Put command failed for {value}"
            time.sleep(0.5)  # Small delay between puts

        # Collect received values
        received_values = []
        for expected_base64 in base64_values:
            try:
                received_values.append(output_queue.get(timeout=3))
            except queue.Empty:
                pytest.fail(
                    f"Did not receive all expected values. Only got: {received_values}"
                )

        # Verify all values were received in order (as base64)
        assert (
            received_values == base64_values
        ), f"Received values {received_values} do not match expected base64 values {base64_values}"

    finally:
        # Cleanup: terminate subscriber process
        subscriber_process.send_signal(signal.SIGINT)
        subscriber_thread.join(timeout=2)
        subscriber_process.wait(timeout=2)


def test_liveliness_token_and_get(zenoh_port):
    """
    End-to-end test for liveliness token and get commands

    Verifies:
    - Can declare a liveliness token
    - Can query alive tokens with liveliness get
    - Token appears in get results as ALIVE
    """
    import json

    # Key to use for this test
    test_key = "test/liveliness/token1"

    # Start liveliness token process (listening on port)
    token_process = run_zenoh_cli(
        ["liveliness", "token", "-k", test_key],
        port=zenoh_port,
        listen=True,
        capture=False,
    )

    # Give token a moment to be declared and session to establish
    time.sleep(2)

    try:
        # Query alive tokens (connecting to token's port)
        get_result = run_zenoh_cli(
            ["liveliness", "get", "-k", "test/liveliness/**"],
            port=zenoh_port,
            listen=False,
        )

        # Check get was successful
        assert get_result.returncode == 0, f"Get command failed: {get_result.stderr}"

        # Parse JSON output
        lines = get_result.stdout.strip().split("\n")
        found_token = False
        for line in lines:
            if line:
                data = json.loads(line)
                if data["key"] == test_key and data["status"] == "ALIVE":
                    found_token = True
                    break

        assert found_token, f"Token {test_key} not found in liveliness get results"

    finally:
        # Cleanup: terminate token process
        token_process.send_signal(signal.SIGINT)
        token_process.wait(timeout=2)


def test_liveliness_sub_alive_and_dropped(zenoh_port):
    """
    End-to-end test for liveliness subscribe command

    Verifies:
    - Can subscribe to liveliness changes
    - Receives ALIVE when token is declared
    - Receives DROPPED when token is undeclared
    """
    import json

    # Setup output queue for liveliness subscriber
    output_queue = queue.Queue()

    # Key to use for this test
    test_key = "test/liveliness/token2"

    # Start liveliness subscriber process (listening on port)
    sub_process = run_zenoh_cli(
        ["liveliness", "sub", "-k", "test/liveliness/**"],
        port=zenoh_port,
        listen=True,
        capture=False,
    )

    # Start output capture thread
    sub_thread = threading.Thread(
        target=capture_subprocess_output, args=(sub_process, output_queue)
    )
    sub_thread.start()

    # Give subscriber a moment to start and establish session
    time.sleep(2)

    try:
        # Start a liveliness token (connecting to subscriber's port)
        token_process = run_zenoh_cli(
            ["liveliness", "token", "-k", test_key],
            port=zenoh_port,
            listen=False,
            capture=False,
        )

        # Wait for token to be declared and propagated
        time.sleep(2)

        # Check for ALIVE message
        try:
            alive_msg = output_queue.get(timeout=3)
            alive_data = json.loads(alive_msg)
            assert (
                alive_data["key"] == test_key
            ), f"Expected key {test_key}, got {alive_data['key']}"
            assert (
                alive_data["status"] == "ALIVE"
            ), f"Expected ALIVE status, got {alive_data['status']}"
        except queue.Empty:
            pytest.fail("Did not receive ALIVE message from liveliness subscriber")

        # Stop the token to trigger DROPPED
        token_process.send_signal(signal.SIGINT)
        token_process.wait(timeout=2)

        # Wait a bit for the DROPPED message
        time.sleep(1)

        # Check for DROPPED message
        try:
            dropped_msg = output_queue.get(timeout=3)
            dropped_data = json.loads(dropped_msg)
            assert (
                dropped_data["key"] == test_key
            ), f"Expected key {test_key}, got {dropped_data['key']}"
            assert (
                dropped_data["status"] == "DROPPED"
            ), f"Expected DROPPED status, got {dropped_data['status']}"
        except queue.Empty:
            pytest.fail("Did not receive DROPPED message from liveliness subscriber")

    finally:
        # Cleanup: terminate subscriber process
        sub_process.send_signal(signal.SIGINT)
        sub_thread.join(timeout=2)
        sub_process.wait(timeout=2)


def test_put_with_liveliness(zenoh_port):
    """
    End-to-end test for put command with liveliness token

    Verifies:
    - Can put a value with liveliness token
    - Token is visible via liveliness get while put is active
    """
    import json

    # Key to use for this test
    data_key = "test/data/sensor1"
    liveliness_key = "test/producer/sensor1"

    # Start a put process with stdin that keeps the token alive (listening on port)
    put_process = run_zenoh_cli(
        [
            "put",
            "-k",
            data_key,
            "--line",
            "{value}",
            "--liveliness",
            liveliness_key,
        ],
        port=zenoh_port,
        listen=True,
        capture=False,
    )

    # Give put a moment to start and declare token
    # Increased sleep time to ensure session is fully established
    time.sleep(2)

    try:
        # Query alive tokens to verify our liveliness token is present (connecting to put's port)
        get_result = run_zenoh_cli(
            ["liveliness", "get", "-k", "test/producer/**"],
            port=zenoh_port,
            listen=False,
        )

        # Check get was successful
        assert get_result.returncode == 0, f"Get command failed: {get_result.stderr}"

        # Parse JSON output to find our token
        lines = get_result.stdout.strip().split("\n")
        found_token = False
        for line in lines:
            if line:
                data = json.loads(line)
                if data["key"] == liveliness_key and data["status"] == "ALIVE":
                    found_token = True
                    break

        assert (
            found_token
        ), f"Liveliness token {liveliness_key} not found in get results"

    finally:
        # Cleanup: terminate put process
        put_process.send_signal(signal.SIGINT)
        put_process.wait(timeout=2)


def test_liveliness_sub_with_history(zenoh_port):
    """
    End-to-end test for liveliness subscribe with --history flag

    Verifies:
    - Can subscribe with --history flag
    - Receives currently alive tokens immediately
    """
    import json

    # Setup output queue for liveliness subscriber
    output_queue = queue.Queue()

    # Key to use for this test
    test_key = "test/liveliness/token3"

    # First, start a liveliness token before subscribing (listening on port)
    token_process = run_zenoh_cli(
        ["liveliness", "token", "-k", test_key],
        port=zenoh_port,
        listen=True,
        capture=False,
    )

    # Give token a moment to be declared and session to establish
    time.sleep(2)

    try:
        # Now subscribe with --history to get the already-alive token (connecting to token's port)
        sub_process = run_zenoh_cli(
            ["liveliness", "sub", "-k", "test/liveliness/**", "--history"],
            port=zenoh_port,
            listen=False,
            capture=False,
        )

        # Start output capture thread
        sub_thread = threading.Thread(
            target=capture_subprocess_output, args=(sub_process, output_queue)
        )
        sub_thread.start()

        # Give subscriber a moment to start
        time.sleep(1)

        # Check for ALIVE message (from history)
        try:
            alive_msg = output_queue.get(timeout=3)
            alive_data = json.loads(alive_msg)
            assert (
                alive_data["key"] == test_key
            ), f"Expected key {test_key}, got {alive_data['key']}"
            assert (
                alive_data["status"] == "ALIVE"
            ), f"Expected ALIVE status, got {alive_data['status']}"
        except queue.Empty:
            pytest.fail(
                "Did not receive ALIVE message from liveliness subscriber with --history"
            )

        # Cleanup subscriber
        sub_process.send_signal(signal.SIGINT)
        sub_thread.join(timeout=2)
        sub_process.wait(timeout=2)

    finally:
        # Cleanup: terminate token process
        token_process.send_signal(signal.SIGINT)
        token_process.wait(timeout=2)
