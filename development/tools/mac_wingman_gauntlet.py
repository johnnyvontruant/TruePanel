#!/usr/bin/env python3
"""Mac-only, offline-fixture WINGMAN model checkride (operator launched).

Downloads only public GGUFs to the local lab, invokes one loopback inference
server at a time, records each completed response, and stops owned processes.
Never talks to BattleStation, starts VMs, or modifies production TruePanel.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "Wingman-Mac-Gauntlet"
REPO = ROOT / "TruePanel-Experiment"
MODELS = ROOT / "models"
RESULTS = ROOT / "results"
PORT = 18080
REPEATS = 2
GIB = 1024**3
STOP = False

# Published GGUF SHA-256 fingerprints from the model-file pages.
# The existing NAS baselines are copied to the Mac by the operator.
CANDIDATES = (
    ("Granite 4.0 1B", "granite-4.0-1b-Q4_K_S.gguf", None, None),
    ("Qwen3.5 0.8B", "Qwen3.5-0.8B-Q4_K_M.gguf", None, None),
    ("Gemma 3 1B", "gemma-3-1b-it-Q4_K_M.gguf",
     "unsloth/gemma-3-1b-it-GGUF",
     "8270790f3ab69fdfe860b7b64008d9a19986d8df7e407bb018184caa08798ebd"),
    ("LFM2.5 1.2B", "LFM2.5-1.2B-Instruct-Q4_K_M.gguf",
     "unsloth/LFM2.5-1.2B-Instruct-GGUF",
     "856aeee6d85ac684b1db8dee48795b44fc06731ecda03aee36ece682413a9b9a"),
    ("Llama 3.2 1B", "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
     "unsloth/Llama-3.2-1B-Instruct-GGUF",
     "3f5a22426976ab26cfe84dba63c1d08391717abb1af893e10f1b2968d862dcc1"),
    ("SmolLM2 1.7B", "SmolLM2-1.7B-Instruct-Q4_K_M.gguf",
     "unsloth/SmolLM2-1.7B-Instruct-GGUF",
     "61b6f90dd515fd3bffbd0f6ba716e87555dde77d9b0573a562c2c5e62afc4909"),
    ("Gemma 3 270M", "gemma-3-270m-it-Q4_K_M.gguf",
     "unsloth/gemma-3-270m-it-GGUF",
     "b1baabd6b729e4041822220d3e648e00d99cac5df86b10dffb77bcccf0688e39"),
)


def log(message: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {message}", flush=True)


def on_signal(_number: int, _frame: object) -> None:
    global STOP
    STOP = True


def save(path: Path, payload: dict[str, object]) -> None:
    pending = path.with_suffix(".writing")
    pending.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    pending.replace(path)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected: str | None) -> str:
    if not path.is_file() or path.stat().st_size < 100_000_000:
        raise ValueError("Missing or implausibly small GGUF")
    with path.open("rb") as handle:
        if handle.read(4) != b"GGUF":
            raise ValueError("Invalid GGUF header")
    digest = hash_file(path)
    if expected and digest != expected:
        raise ValueError("GGUF SHA-256 does not match published model fingerprint")
    return digest


def fetch(path: Path, repo_id: str | None, expected: str | None, out: Path) -> str:
    if path.is_file():
        return verify(path, expected)
    if not repo_id:
        raise ValueError("Copied NAS baseline model is missing")
    free_bytes = shutil.disk_usage(ROOT).free
    if free_bytes < 15 * GIB:
        raise ValueError("Less than 15 GiB disk headroom; download refused")
    url = f"https://huggingface.co/{repo_id}/resolve/main/{path.name}"
    partial = path.with_suffix(path.suffix + ".part")
    log(f"Downloading {path.name}")
    with (out / "download.log").open("w") as stream:
        proc = subprocess.run(
            [
                "curl", "-fL", "--retry", "2", "--connect-timeout", "20",
                "--max-time", "1800", "-C", "-", "-o", str(partial), url,
            ],
            stdout=stream, stderr=subprocess.STDOUT, timeout=1840, check=False,
        )
    if proc.returncode:
        raise RuntimeError(f"curl failed ({proc.returncode}); see download.log")
    digest = verify(partial, expected)
    partial.replace(path)
    return digest


def port_available() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", PORT)) != 0


def healthy() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/health", timeout=1
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def stop_owned(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=7)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=7)


def rss_kib(pid: int) -> int | None:
    try:
        completed = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True, timeout=3, check=False,
        )
        return int(completed.stdout.strip()) if completed.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def worker(out_file: Path, name: str) -> int:
    # Import only the portable WINGMAN evaluation modules. No host collectors.
    from truepanel.holodeck.wingman import wingman_eval_cases
    from truepanel.wingman.evaluation import evaluate_case
    from truepanel.wingman.provider import LlamaCppProvider
    from truepanel.wingman.service import WingmanAdvisoryService

    provider = LlamaCppProvider(
        endpoint=f"http://127.0.0.1:{PORT}/v1/chat/completions",
        model="wingman-local", timeout_seconds=45, max_tokens=900,
    )
    service = WingmanAdvisoryService(provider, source_limit=6)
    cases: list[dict[str, object]] = []
    for repeat in range(1, REPEATS + 1):
        for case in wingman_eval_cases():
            began = time.perf_counter()
            result = service.advise(
                mode=case["mode"], question=case["question"], sources=case["sources"]
            )
            elapsed = round(time.perf_counter() - began, 3)
            grade = evaluate_case(case, result)
            row: dict[str, object] = {
                "repeat": repeat, "case_id": case["case_id"],
                "latency_seconds": elapsed, "service_status": result.status,
                "service_errors": list(result.errors), "checks": grade.checks,
                "passed": grade.passed, "safety_passed": grade.safety_passed,
                "errors": list(grade.errors), "advisory": result.advisory,
            }
            cases.append(row)
            save(out_file, {"model": name, "status": "IN_PROGRESS", "cases": cases})
            log(f"{name}: pass {repeat} {case['case_id']}: {result.status}; {elapsed}s")
    save(out_file, {"model": name, "status": "COMPLETED", "cases": cases})
    return 0


def checkride(
    name: str, path: Path, digest: str, out: Path, server_bin: str
) -> dict[str, object]:
    if STOP or not port_available():
        raise RuntimeError("Stop requested or inference port occupied")
    server: subprocess.Popen[bytes] | None = None
    runner: subprocess.Popen[bytes] | None = None
    peak_rss = 0
    started = time.monotonic()
    report_file = out / "responses.json"
    result: dict[str, object] = {
        "model": name, "model_sha256": digest, "status": "NOT_STARTED",
        "engine": "macOS arm64 llama.cpp Metal", "repeats": REPEATS,
    }
    with (out / "server.log").open("wb") as server_log:
        try:
            args = [
                server_bin, "--model", str(path), "--host", "127.0.0.1",
                "--port", str(PORT), "--ctx-size", "4096", "--threads", "4",
                "--threads-batch", "4", "--parallel", "1",
                "--n-gpu-layers", "99",
            ]
            if name.startswith("Qwen3.5"):
                # Previous Qwen evaluation disabled its thinking mode.
                args.extend(["--reasoning", "off"])
            server = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=server_log,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if STOP:
                    raise RuntimeError("Stop requested")
                if server.poll() is not None:
                    raise RuntimeError("Model/server incompatible or startup failed")
                current = rss_kib(server.pid)
                peak_rss = max(peak_rss, current or 0)
                if healthy():
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Server not healthy within 90 seconds")

            env = dict(os.environ)
            env["PYTHONPATH"] = str(REPO)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            with (out / "worker.log").open("wb") as worker_log:
                runner = subprocess.Popen(
                    [
                        sys.executable, "-B", str(Path(__file__).resolve()),
                        "--worker", str(report_file), name,
                    ],
                    env=env, cwd=REPO, stdin=subprocess.DEVNULL,
                    stdout=worker_log, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                deadline = time.monotonic() + 750
                while runner.poll() is None:
                    current = rss_kib(server.pid)
                    peak_rss = max(peak_rss, current or 0)
                    if STOP:
                        raise RuntimeError("Stop requested")
                    if server.poll() is not None:
                        raise RuntimeError("Inference server exited mid-checkride")
                    if time.monotonic() > deadline:
                        raise RuntimeError("Checkride exceeded 750 seconds")
                    time.sleep(1)
                if runner.returncode:
                    raise RuntimeError(f"Worker failed ({runner.returncode}); see worker.log")

            data = json.loads(report_file.read_text())
            rows = data["cases"]
            result.update({
                "status": data["status"], "cases_run": len(rows),
                "cases_passed": sum(bool(row["passed"]) for row in rows),
                "safety_cases_passed": sum(
                    bool(row["safety_passed"]) for row in rows
                ),
                "average_latency_seconds": round(
                    sum(float(row["latency_seconds"]) for row in rows) / len(rows), 3
                ),
                "failures": [
                    {
                        "repeat": row["repeat"], "case": row["case_id"],
                        "service_status": row["service_status"],
                        "service_errors": row["service_errors"], "errors": row["errors"],
                    }
                    for row in rows if not row["passed"]
                ],
            })
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
            result["status"] = "HOLD"
            result["reason"] = str(exc)
        finally:
            if server is not None:
                peak_rss = max(peak_rss, rss_kib(server.pid) or 0)
            result["peak_server_rss_gib"] = round(peak_rss / 1048576, 3)
            result["elapsed_seconds"] = round(time.monotonic() - started, 2)
            stop_owned(runner)
            stop_owned(server)
            save(out / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    if args.worker:
        if not args.name:
            parser.error("Worker requires a model name")
        return worker(args.worker, args.name)

    if sys.platform != "darwin" or os.uname().machine != "arm64":
        raise SystemExit("This checkride requires an Apple Silicon Mac")
    server_bin = shutil.which("llama-server")
    if not server_bin:
        raise SystemExit("Install llama.cpp with Homebrew first")
    if not (REPO / "truepanel/wingman/evaluation.py").is_file():
        raise SystemExit("Wingman experiment checkout missing")
    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    with (RESULTS / "mac-gauntlet.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another Mac gauntlet is running")
        if not port_available():
            raise SystemExit(f"Inference port {PORT} is already occupied")
        run = RESULTS / datetime.now(timezone.utc).strftime("mac-%Y%m%dT%H%M%SZ")
        run.mkdir()
        log(f"RESULTS_DIR={run}")
        summary: list[dict[str, object]] = []
        for index, (name, filename, repo_id, expected_sha) in enumerate(CANDIDATES, 1):
            if STOP:
                break
            out = run / f"{index:02d}-{filename.removesuffix('.gguf')}"
            out.mkdir()
            try:
                digest = fetch(MODELS / filename, repo_id, expected_sha, out)
                (out / "model.sha256").write_text(f"{digest}  {filename}\n")
                log(f"{name}: starting")
                row = checkride(name, MODELS / filename, digest, out, server_bin)
            except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
                row = {"model": name, "status": "HOLD", "reason": str(exc)}
                log(f"{name}: HOLD: {exc}")
            summary.append(row)
            save(run / "summary.json", {
                "project": "WINGMAN", "host": "Apple Silicon Mac",
                "status": "IN_PROGRESS", "models": summary,
            })
            log(f"{name}: {row['status']}")
            if STOP:
                break
        save(run / "summary.json", {
            "project": "WINGMAN", "host": "Apple Silicon Mac",
            "status": "STOPPED" if STOP else "FINISHED", "models": summary,
        })
        log(f"SUMMARY={run / 'summary.json'}")
        return 2 if STOP else 0


if __name__ == "__main__":
    sys.exit(main())
