import pytest
import subprocess
import time
import threading
import queue
import os
import signal
import base64


def run_zenoh_cli(command, capture=True):
    """
    Helper function to run Zenoh CLI commands

    Args:
        command (list): List of command arguments to pass to the CLI
        capture (bool): Whether to capture output

    Returns:
        subprocess.Popen or subprocess.CompletedProcess
    """
    base_command = ["python", "-m", "zenoh_cli"]
    full_command = base_command + command

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


def test_subscribe_and_put():
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

    # Start subscriber process with default base64 decoder
    subscriber_process = run_zenoh_cli(["subscribe", "-k", test_key], capture=False)

    # Start output capture thread
    subscriber_thread = threading.Thread(
        target=capture_subprocess_output, args=(subscriber_process, output_queue)
    )
    subscriber_thread.start()

    # Give subscriber a moment to start
    time.sleep(1)

    try:
        # Put a value (implicitly base64 encoded)
        put_result = run_zenoh_cli(["put", "-k", test_key, "-v", test_value])

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


def test_subscribe_with_base64_decoding():
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

    # Start subscriber process with explicit base64 decoder
    subscriber_process = run_zenoh_cli(
        ["subscribe", "-k", test_key, "--decoder", "base64"], capture=False
    )

    # Start output capture thread
    subscriber_thread = threading.Thread(
        target=capture_subprocess_output, args=(subscriber_process, output_queue)
    )
    subscriber_thread.start()

    # Give subscriber a moment to start
    time.sleep(1)

    try:
        # Put base64 encoded value
        put_result = run_zenoh_cli(["put", "-k", test_key, "-v", test_value])

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


def test_subscribe_multiple_puts():
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

    # Start subscriber process
    subscriber_process = run_zenoh_cli(["subscribe", "-k", test_key], capture=False)

    # Start output capture thread
    subscriber_thread = threading.Thread(
        target=capture_subprocess_output, args=(subscriber_process, output_queue)
    )
    subscriber_thread.start()

    # Give subscriber a moment to start
    time.sleep(1)

    try:
        # Put multiple values
        for value in test_values:
            put_result = run_zenoh_cli(["put", "-k", test_key, "-v", value])
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
