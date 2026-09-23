#!/usr/bin/env python3
"""Run isolated, unattended, resource-gated WINGMAN model checkrides.

This is an operator-launched lab utility, not a TruePanel service. It never
starts/stops VMs, changes ZFS settings, or modifies the production installation.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path("/mnt/SSDs/Applications/Wingman-Lab")
REPO = LAB / "TruePanel-Experiment"
SERVER = LAB / "runtime/llama-b10985/llama-server"
BENCHMARK = REPO / "development/tools/benchmark_wingman.py"
MODELS = LAB / "models"
RESULTS = LAB / "results"
PORT = 18080
GIB = 1024**3
MIN_START_AVAILABLE = 5 * GIB
MIN_RUNNING_AVAILABLE = 2 * GIB
MIN_FREE_DISK = 8 * GIB
REPEATS = 2
STOP_REQUESTED = False

# The SHA-256 values for downloads are published by the model-file distributor.
CANDIDATES = (
    ("granite-4.0-1b-Q4_K_S", "granite-4.0-1b-Q4_K_S.gguf", None, None),
    ("Qwen3.5-0.8B-Q4_K_M", "Qwen3.5-0.8B-Q4_K_M.gguf", None, None),
    (
        "gemma-3-1b-it-Q4_K_M", "gemma-3-1b-it-Q4_K_M.gguf",
        "unsloth/gemma-3-1b-it-GGUF",
        "8270790f3ab69fdfe860b7b64008d9a19986d8df7e407bb018184caa08798ebd",
    ),
    (
        "LFM2.5-1.2B-Instruct-Q4_K_M", "LFM2.5-1.2B-Instruct-Q4_K_M.gguf",
        "unsloth/LFM2.5-1.2B-Instruct-GGUF",
        "856aeee6d85ac684b1db8dee48795b44fc06731ecda03aee36ece682413a9b9a",
    ),
    (
        "Llama-3.2-1B-Instruct-Q4_K_M", "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "unsloth/Llama-3.2-1B-Instruct-GGUF",
        "3f5a22426976ab26cfe84dba63c1d08391717abb1af893e10f1b2968d862dcc1",
    ),
    (
        "SmolLM2-1.7B-Instruct-Q4_K_M", "SmolLM2-1.7B-Instruct-Q4_K_M.gguf",
        "unsloth/SmolLM2-1.7B-Instruct-GGUF",
        "61b6f90dd515fd3bffbd0f6ba716e87555dde77d9b0573a562c2c5e62afc4909",
    ),
    (
        "gemma-3-270m-it-Q4_K_M", "gemma-3-270m-it-Q4_K_M.gguf",
        "unsloth/gemma-3-270m-it-GGUF",
        "b1baabd6b729e4041822220d3e648e00d99cac5df86b10dffb77bcccf0688e39",
    ),
)


class Hold(Exception):
    """A model cannot be tested safely under the current conditions."""


def log(message: str) -> None:
    print(
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {message}",
        flush=True,
    )


def available_memory() -> int:
    with Path("/proc/meminfo").open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise Hold("MemAvailable unavailable")


def vm_stopped() -> bool:
    proc = subprocess.run(
        ["midclt", "call", "vm.status", "1"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return json.loads(proc.stdout)["state"] == "STOPPED"


def ensure_vm_stopped() -> None:
    try:
        if not vm_stopped():
            raise Hold("Home Assistant VM is not stopped")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        raise Hold(f"Unable to verify Home Assistant state: {type(exc).__name__}") from exc


def port_free() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", PORT)) != 0


def disk_free() -> int:
    stat = os.statvfs(MODELS)
    return stat.f_bavail * stat.f_frsize


def preflight() -> None:
    if STOP_REQUESTED:
        raise Hold("Operator requested stop")
    ensure_vm_stopped()
    if available_memory() < MIN_START_AVAILABLE:
        raise Hold("Available RAM below 5 GiB model-start threshold")
    if not port_free():
        raise Hold(f"Port {PORT} is already in use")
    if disk_free() < MIN_FREE_DISK:
        raise Hold("Less than 8 GiB free in model storage")
    for unit in ("truepanel.service", "truepanel-mission-control.service"):
        subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            check=True,
            timeout=10,
        )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_model(path: Path, expected: str | None) -> str:
    with path.open("rb") as stream:
        if stream.read(4) != b"GGUF":
            raise Hold(f"Not a GGUF model: {path.name}")
    if path.stat().st_size < 100_000_000:
        raise Hold(f"Model file is implausibly small: {path.name}")
    actual = sha256(path)
    if expected and actual != expected:
        raise Hold(f"SHA-256 mismatch for {path.name}; do not use this download")
    return actual


def fetch_model(
    path: Path, repo_id: str | None, expected_sha: str | None, out: Path
) -> str:
    if path.exists():
        return verify_model(path, expected_sha)
    if not repo_id:
        raise Hold(f"Existing baseline model missing: {path.name}")
    if STOP_REQUESTED:
        raise Hold("Operator requested stop")
    if disk_free() < MIN_FREE_DISK:
        raise Hold("Low disk headroom before download")
    url = f"https://huggingface.co/{repo_id}/resolve/main/{path.name}"
    partial = path.with_name(path.name + ".part")
    log(f"Downloading {path.name} (max 30 minutes)")
    with (out / "download.log").open("w", encoding="utf-8") as stream:
        download = subprocess.run(
            [
                "curl", "-fL", "--retry", "2", "--connect-timeout", "20",
                "--max-time", "1800", "-C", "-", "-o", str(partial), url,
            ],
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=1840,
            check=False,
        )
    if download.returncode:
        raise Hold(f"Download failed with exit {download.returncode}")
    fingerprint = verify_model(partial, expected_sha)
    partial.replace(path)
    return fingerprint


def stop_owned(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=6)


def peak_rss_kib(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def health_ready() -> bool:
    try:
        response = subprocess.run(
            [
                "curl", "-fsS", "--max-time", "1",
                f"http://127.0.0.1:{PORT}/health",
            ],
            capture_output=True,
            timeout=3,
            check=False,
        )
        return response.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def run_case(
    name: str, model: Path, fingerprint: str, run_dir: Path, attempt: int
) -> dict[str, object]:
    preflight()
    log(f"{name}: checkride {attempt}/{REPEATS}")
    model_dir = run_dir / f"run-{attempt}"
    model_dir.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    server: subprocess.Popen[bytes] | None = None
    bench: subprocess.Popen[bytes] | None = None
    low_ram_streak = 0
    minimum_available = available_memory()
    abort_reason = None
    started = time.monotonic()
    result: dict[str, object] = {
        "model": name,
        "attempt": attempt,
        "model_sha256": fingerprint,
        "status": "NOT_STARTED",
    }
    with (model_dir / "server.log").open("wb") as server_log:
        try:
            server = subprocess.Popen(
                [
                    str(SERVER), "--model", str(model),
                    "--host", "127.0.0.1", "--port", str(PORT),
                    "--ctx-size", "4096", "--threads", "4",
                    "--threads-batch", "4", "--parallel", "1",
                ],
                stdin=subprocess.DEVNULL,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise Hold("Inference server exited during startup")
                if STOP_REQUESTED:
                    raise Hold("Operator requested stop")
                if health_ready():
                    break
                time.sleep(1)
            else:
                raise Hold("Inference server did not become ready in 90 seconds")

            with (model_dir / "benchmark.json").open("wb") as report, (
                model_dir / "benchmark.stderr"
            ).open("wb") as errors:
                bench = subprocess.Popen(
                    [
                        sys.executable, "-B", str(BENCHMARK),
                        "--endpoint",
                        f"http://127.0.0.1:{PORT}/v1/chat/completions",
                        "--model", "wingman-local", "--timeout", "45",
                    ],
                    cwd=REPO,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=report,
                    stderr=errors,
                    start_new_session=True,
                )
                bench_deadline = time.monotonic() + 420
                last_vm_check = 0.0
                while bench.poll() is None:
                    if STOP_REQUESTED:
                        abort_reason = "Operator requested stop"
                        break
                    if server.poll() is not None:
                        abort_reason = "Inference server exited during benchmark"
                        break
                    if time.monotonic() > bench_deadline:
                        abort_reason = "Benchmark exceeded 420 seconds"
                        break
                    remaining = available_memory()
                    minimum_available = min(minimum_available, remaining)
                    low_ram_streak = (
                        low_ram_streak + 1
                        if remaining < MIN_RUNNING_AVAILABLE else 0
                    )
                    if low_ram_streak >= 2:
                        abort_reason = "Host available memory fell below 2 GiB"
                        break
                    if time.monotonic() - last_vm_check > 10:
                        last_vm_check = time.monotonic()
                        try:
                            ensure_vm_stopped()
                        except Hold as exc:
                            abort_reason = str(exc)
                            break
                    time.sleep(1)
                if abort_reason:
                    stop_owned(bench)
                elif bench.poll() is None:
                    bench.wait(timeout=5)
                result["benchmark_exit"] = bench.returncode

            if abort_reason:
                result["status"] = "SAFETY_ABORT"
                result["reason"] = abort_reason
            else:
                try:
                    report_data = json.loads(
                        (model_dir / "benchmark.json").read_text(encoding="utf-8")
                    )
                    result["status"] = "COMPLETED"
                    result["cases_passed"] = report_data["passed_cases"]
                    result["safety_cases_passed"] = report_data["safety_passed_cases"]
                    result["total_cases"] = report_data["case_count"]
                    result["average_seconds"] = report_data["average_latency_seconds"]
                    result["case_results"] = [
                        {
                            "id": case["case_id"],
                            "passed": case["passed"],
                            "status": case["service_status"],
                            "errors": case["errors"],
                            "service_errors": case["service_errors"],
                        }
                        for case in report_data["cases"]
                    ]
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    result["status"] = "BENCHMARK_ERROR"
                    result["reason"] = type(exc).__name__
        except (OSError, subprocess.SubprocessError, Hold) as exc:
            result["status"] = "STARTUP_HOLD"
            result["reason"] = str(exc)
        finally:
            if server is not None:
                result["peak_server_rss_gib"] = (
                    round(peak_rss_kib(server.pid) / 1048576, 3)
                    if peak_rss_kib(server.pid) is not None else None
                )
            result["minimum_host_available_gib"] = round(
                minimum_available / GIB, 3
            )
            result["elapsed_seconds"] = round(time.monotonic() - started, 2)
            stop_owned(bench)
            stop_owned(server)
    (model_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log(f"{name} run {attempt}: {result['status']}; peak RSS {result.get('peak_server_rss_gib')} GiB")
    return result


def on_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def main() -> int:
    signal.signal(signal.SIGTERM, on_stop)
    signal.signal(signal.SIGINT, on_stop)
    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    lock = RESULTS / "overnight-gauntlet.lock"
    with lock.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("HOLD: Another overnight gauntlet is already running")
            return 2
        run_dir = RESULTS / (
            "overnight-gauntlet-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        run_dir.mkdir()
        log(f"RESULTS_DIR={run_dir}")
        summary: list[dict[str, object]] = []
        terminal_reason = ""
        for name, filename, repo_id, expected in CANDIDATES:
            if STOP_REQUESTED:
                terminal_reason = "Operator requested stop"
                break
            item_dir = run_dir / name
            item_dir.mkdir()
            try:
                preflight()
                fingerprint = fetch_model(MODELS / filename, repo_id, expected, item_dir)
                (item_dir / "model.sha256").write_text(
                    f"{fingerprint}  {filename}\n", encoding="utf-8"
                )
                for attempt in range(1, REPEATS + 1):
                    if STOP_REQUESTED:
                        terminal_reason = "Operator requested stop"
                        break
                    result = run_case(
                        name, MODELS / filename, fingerprint, item_dir, attempt
                    )
                    summary.append(result)
                    if result["status"] == "SAFETY_ABORT":
                        terminal_reason = str(result.get("reason", "safety abort"))
                        break
                    # Do not repeatedly retry an incompatible model/server.
                    if result["status"] == "STARTUP_HOLD":
                        break
                if terminal_reason:
                    break
            except Hold as exc:
                reason = str(exc)
                log(f"{name}: HOLD: {reason}")
                summary.append({"model": name, "status": "HOLD", "reason": reason})
                # Resource, VM, or shared-port concerns stop the whole gauntlet.
                if (
                    "VM" in reason
                    or "memory" in reason.lower()
                    or "RAM" in reason
                    or "port" in reason.lower()
                    or "disk" in reason.lower()
                    or "Operator" in reason
                ):
                    terminal_reason = reason
                    break
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                log(f"{name}: error: {type(exc).__name__}: {exc}")
                summary.append(
                    {"model": name, "status": "ERROR", "reason": str(exc)}
                )
            finally:
                (run_dir / "summary.json").write_text(
                    json.dumps(
                        {
                            "project": "WINGMAN",
                            "status": "STOPPED" if terminal_reason else "IN_PROGRESS",
                            "stop_reason": terminal_reason,
                            "repeats_per_model": REPEATS,
                            "results": summary,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
        final_status = "STOPPED" if terminal_reason else "FINISHED"
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "project": "WINGMAN",
                    "status": final_status,
                    "stop_reason": terminal_reason,
                    "repeats_per_model": REPEATS,
                    "results": summary,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        log(f"{final_status}: {terminal_reason or 'All candidate slots attempted'}")
        log(f"SUMMARY={run_dir / 'summary.json'}")
        return 0 if not terminal_reason else 2


if __name__ == "__main__":
    sys.exit(main())
