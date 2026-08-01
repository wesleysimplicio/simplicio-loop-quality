import sys
import tempfile
import time
from pathlib import Path

import pytest
from simplicio_loop.hub_daemon import (
    HubDaemon,
    HubSocketClient,
    HubSocketServer,
    default_endpoint,
    default_transport,
)
from simplicio_loop.hub_queue_agent import HubQueueAgentClient

from simplicio_loop_quality.adapters import ResourceRequest
from simplicio_loop_quality.hub_process_adapter import HubProcessAdapter, QualityToolRequest

TERMINAL = {"passed", "failed", "cancelled", "timed_out"}


@pytest.fixture
def real_hub():
    with tempfile.TemporaryDirectory() as directory:
        daemon = HubDaemon(str(Path(directory) / "hub.lock"))
        daemon.start()
        transport = default_transport()
        endpoint = default_endpoint(directory)
        server = HubSocketServer(daemon, endpoint, transport)
        server.start()
        try:
            def connect():
                client = HubQueueAgentClient(
                    HubSocketClient(endpoint, transport=transport), strict=True
                )
                return HubProcessAdapter(client)

            yield connect
        finally:
            server.shutdown()
            daemon.stop()


def tool_request(
    script: str,
    *,
    attempt: str,
    timeout: float = 5,
    max_output_bytes: int = 4096,
) -> QualityToolRequest:
    return QualityToolRequest(
        run_id="quality-real-run",
        task_id="quality-real-task",
        attempt_id=attempt,
        stage_id="testing",
        agent_id="test-executor",
        argv=(sys.executable, "-c", script),
        cwd=str(Path.cwd()),
        cwd_allowlist=(str(Path.cwd()),),
        env={},
        env_allowlist=(),
        resources=ResourceRequest(500, 256, timeout),
        max_output_bytes=max_output_bytes,
        idempotency_key=f"quality-real-process:{attempt}",
    )


def wait_terminal(adapter, submission, timeout=5):
    deadline = time.monotonic() + timeout
    status = adapter.poll(submission)
    while status.get("status") not in TERMINAL and time.monotonic() < deadline:
        time.sleep(0.01)
        status = adapter.poll(submission)
    return status


def test_real_hub_executes_and_collects_quality_process_without_local_adapter_process(real_hub):
    adapter = real_hub()
    submission = adapter.submit(tool_request("print('quality-hub-ok')", attempt="happy"))
    status = wait_terminal(adapter, submission)
    receipt = adapter.collect(submission)
    assert status["status"] == "passed"
    assert receipt.status == "PASS"
    assert receipt.process_id
    assert receipt.raw_evidence["process_result"]["stdout"].strip() == "quality-hub-ok"


@pytest.mark.parametrize(
    ("script", "attempt", "timeout", "max_output", "reason"),
    [
        ("import time; time.sleep(1)", "timeout", 0.05, 4096, "PROCESS_TIMEOUT"),
        ("raise SystemExit(7)", "crash", 5, 4096, "PROCESS_CRASHED"),
        ("print('x' * 10000)", "truncated", 5, 128, "OUTPUT_TRUNCATED"),
    ],
)
def test_real_hub_failure_results_are_fail_closed(
    real_hub, script, attempt, timeout, max_output, reason
):
    adapter = real_hub()
    submission = adapter.submit(
        tool_request(script, attempt=attempt, timeout=timeout, max_output_bytes=max_output)
    )
    assert wait_terminal(adapter, submission)["status"] in TERMINAL
    receipt = adapter.collect(submission)
    assert (receipt.status, receipt.reason_code) == ("BLOCKED", reason)
    assert receipt.raw_evidence["evidence_hash"]
    assert receipt.raw_evidence["process_result"]["lease_id"] == receipt.process_id


def test_real_hub_reconnect_observes_existing_process_without_redispatch(real_hub):
    first = real_hub()
    submission = first.submit(tool_request("print('reconnected')", attempt="reconnect"))
    reconnected = real_hub()
    assert reconnected.reconnect(submission)["status"] in {"running", "passed"}
    assert wait_terminal(reconnected, submission)["status"] == "passed"
    assert reconnected.collect(submission).status == "PASS"


def test_real_hub_cancellation_produces_terminal_receipt(real_hub):
    adapter = real_hub()
    submission = adapter.submit(
        tool_request("import time; time.sleep(10)", attempt="cancel", timeout=20)
    )
    requested = adapter.cancel(submission, "operator_cancelled")
    assert requested.status in {"BLOCKED", "CANCELLED"}
    assert wait_terminal(adapter, submission)["status"] == "cancelled"
    receipt = adapter.collect(submission)
    assert (receipt.status, receipt.reason_code) == ("CANCELLED", "HUB_CANCELLED")
    assert receipt.process_terminal is True
