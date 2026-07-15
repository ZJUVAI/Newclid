from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import itertools
import os
from pathlib import Path
import site
import socket
import subprocess
import sys
import threading
import time
from typing import Any

import requests


def ensure_startup_patch() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    startup_line = (
        f"import sys; p={str(repo_root)!r}; "
        "sys.path.insert(0, p) if p not in sys.path else None; "
        "import scripts.qwen_tokenizer_compat"
    )
    for site_packages_dir in site.getsitepackages():
        pth_path = Path(site_packages_dir) / "zz_genesisgeo_qwen_patch.pth"
        pth_path.write_text(startup_line, encoding="utf-8")


def parse_gpu_ids(raw_gpu_ids: str) -> list[int]:
    gpu_ids = [part.strip() for part in raw_gpu_ids.split(",") if part.strip()]
    if not gpu_ids:
        raise ValueError("gpu_ids must contain at least one GPU id.")
    return [int(gpu_id) for gpu_id in gpu_ids]


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def allocate_ports(
    *,
    host: str,
    gateway_port: int,
    backend_base_port: int,
    replica_count: int,
) -> tuple[int, list[int]]:
    gateway_candidate = int(gateway_port)
    backend_candidate = int(backend_base_port)
    while True:
        backend_ports = [backend_candidate + offset for offset in range(replica_count)]
        ports = [gateway_candidate] + backend_ports
        if all(is_port_available(host, port) for port in ports):
            return gateway_candidate, backend_ports
        gateway_candidate += 1
        backend_candidate += 1


def wait_for_backend(
    url: str, *, timeout_s: float, poll_interval_s: float = 1.0
) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            response = requests.get(f"{url}/v1/models", timeout=5.0)
            if response.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(poll_interval_s)
    raise TimeoutError(f"Timed out waiting for backend {url} to become ready.")


@dataclass
class BackendInstance:
    gpu_id: int
    url: str
    process: subprocess.Popen[Any]


class ProxyRouter:
    def __init__(
        self,
        backends: list[BackendInstance],
        request_timeout_s: float,
        *,
        debug_log_requests: bool = False,
        debug_max_chars: int = 2000,
    ):
        self.backends = backends
        self.request_timeout_s = request_timeout_s
        self.debug_log_requests = debug_log_requests
        self.debug_max_chars = max(200, int(debug_max_chars))
        self._lock = threading.Lock()
        self._next_index = 0
        self._request_counter = itertools.count(1)

    @property
    def replica_count(self) -> int:
        return len(self.backends)

    def _ordered_backends(self) -> list[BackendInstance]:
        with self._lock:
            start_index = self._next_index
            self._next_index = (self._next_index + 1) % len(self.backends)
        return self.backends[start_index:] + self.backends[:start_index]

    def healthy(self) -> bool:
        for backend in self.backends:
            try:
                response = requests.get(
                    f"{backend.url}/health",
                    timeout=min(2.0, self.request_timeout_s),
                )
                if response.ok:
                    return True
            except requests.RequestException:
                continue
        return False

    def _truncate(self, value: Any) -> str:
        text = str(value)
        if len(text) <= self.debug_max_chars:
            return text
        return text[: self.debug_max_chars] + "...<truncated>"

    def _log_chat_request(
        self, *, request_id: int, body: bytes, backend: BackendInstance
    ) -> None:
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(
                f"[gateway-debug] request_id={request_id} backend_gpu={backend.gpu_id} "
                f"backend_url={backend.url} invalid_json={exc}",
                flush=True,
            )
            return
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages]
        print(
            f"[gateway-debug] request_id={request_id} backend_gpu={backend.gpu_id} "
            f"backend_url={backend.url} message_count={len(messages)}",
            flush=True,
        )
        for index, message in enumerate(messages):
            if isinstance(message, dict):
                role = message.get("role")
                content = message.get("content")
            else:
                role = None
                content = message
            print(
                f"[gateway-debug] request_id={request_id} message[{index}] "
                f"role={role} content={self._truncate(content)}",
                flush=True,
            )

    def _log_chat_response(
        self,
        *,
        request_id: int,
        response: requests.Response,
        backend: BackendInstance,
    ) -> None:
        try:
            payload = response.json()
        except ValueError:
            print(
                f"[gateway-debug] request_id={request_id} backend_gpu={backend.gpu_id} "
                f"backend_url={backend.url} status={response.status_code} "
                f"response={self._truncate(response.text)}",
                flush=True,
            )
            return
        choices = payload.get("choices", [])
        print(
            f"[gateway-debug] request_id={request_id} backend_gpu={backend.gpu_id} "
            f"backend_url={backend.url} status={response.status_code} choice_count={len(choices)}",
            flush=True,
        )
        for index, choice in enumerate(choices):
            message = choice.get("message", {})
            content = message.get("content", "") if isinstance(message, dict) else ""
            print(
                f"[gateway-debug] request_id={request_id} output[{index}]="
                f"{self._truncate(content)}",
                flush=True,
            )

    def forward(
        self,
        *,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[int, bytes, str]:
        last_error: Exception | None = None
        debug_request_id = (
            next(self._request_counter) if self.debug_log_requests else None
        )
        for backend in self._ordered_backends():
            if (
                self.debug_log_requests
                and method == "POST"
                and path == "/v1/chat/completions"
            ):
                self._log_chat_request(
                    request_id=int(debug_request_id),
                    body=body or b"",
                    backend=backend,
                )
            try:
                response = requests.request(
                    method,
                    f"{backend.url}{path}",
                    data=body,
                    headers={"content-type": content_type} if content_type else None,
                    timeout=self.request_timeout_s,
                )
            except requests.RequestException as exc:
                last_error = exc
                continue
            if response.status_code >= 500:
                last_error = requests.HTTPError(
                    f"backend returned status {response.status_code}"
                )
                continue
            if (
                self.debug_log_requests
                and method == "POST"
                and path == "/v1/chat/completions"
            ):
                self._log_chat_response(
                    request_id=int(debug_request_id),
                    response=response,
                    backend=backend,
                )
            return (
                response.status_code,
                response.content,
                response.headers.get("content-type", "application/json"),
            )
        error_payload = {
            "error": {
                "message": f"no healthy vLLM backends available: {last_error}",
                "type": "ServiceUnavailable",
                "code": 503,
            }
        }
        return 503, json.dumps(error_payload).encode("utf-8"), "application/json"


class GatewayHandler(BaseHTTPRequestHandler):
    router: ProxyRouter

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            payload = {
                "status": "ok" if self.router.healthy() else "degraded",
                "replica_count": self.router.replica_count,
            }
            body = json.dumps(payload).encode("utf-8")
            status = 200 if payload["status"] == "ok" else 503
            self._send_response(status, body, "application/json")
            return
        if self.path == "/v1/models":
            status, body, content_type = self.router.forward(
                method="GET", path=self.path
            )
            self._send_response(status, body, content_type)
            return
        self._send_response(404, b'{"error":"not found"}', "application/json")

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_response(404, b'{"error":"not found"}', "application/json")
            return
        content_length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(content_length) if content_length else b""
        status, response_body, content_type = self.router.forward(
            method="POST",
            path=self.path,
            body=body,
            content_type=self.headers.get("content-type"),
        )
        self._send_response(status, response_body, content_type)

    def _send_response(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_gateway_server(
    *,
    host: str,
    port: int,
    router: ProxyRouter,
) -> ThreadingHTTPServer:
    handler_cls = type("BoundGatewayHandler", (GatewayHandler,), {})
    handler_cls.router = router
    return ThreadingHTTPServer((host, port), handler_cls)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch managed single-GPU vLLM replicas behind one local gateway.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model_name", type=str, required=True)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--backend_base_port", type=int, default=8100)
    parser.add_argument("--gpu_ids", type=str, default="0,1,2,3")
    parser.add_argument("--gpu_memory_utilization", type=float, default=0.2)
    parser.add_argument("--max_logprobs", type=int, default=64)
    parser.add_argument(
        "--generation_config",
        type=str,
        default=None,
        help=(
            "Forward to vLLM --generation-config. Use 'vllm' to avoid loading "
            "the model directory generation_config.json, including its "
            "max_new_tokens default."
        ),
    )
    parser.add_argument("--healthcheck_timeout_s", type=float, default=120.0)
    parser.add_argument("--startup_timeout_s", type=float, default=600.0)
    parser.add_argument("--debug_log_requests", action="store_true")
    parser.add_argument(
        "--debug_log_completions",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--debug_max_chars", type=int, default=2000)
    args = parser.parse_args()

    ensure_startup_patch()
    gpu_ids = parse_gpu_ids(args.gpu_ids)
    gateway_port, backend_ports = allocate_ports(
        host=args.host,
        gateway_port=args.port,
        backend_base_port=args.backend_base_port,
        replica_count=len(gpu_ids),
    )

    backends: list[BackendInstance] = []
    server: ThreadingHTTPServer | None = None
    stop_event = threading.Event()
    failure_holder: dict[str, str] = {}
    try:
        for gpu_id, backend_port in zip(gpu_ids, backend_ports):
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
            env.setdefault("TOKENIZERS_PARALLELISM", "false")
            internal_port_base = backend_port + 1000 + (gpu_id * 100)
            env.setdefault("VLLM_PORT", str(internal_port_base))
            env.setdefault("VLLM_DP_MASTER_PORT", str(internal_port_base + 20))

            command = [
                sys.executable,
                "-m",
                "vllm.entrypoints.cli.main",
                "serve",
                args.model_name,
                "--host",
                args.host,
                "--port",
                str(backend_port),
                "--gpu-memory-utilization",
                str(args.gpu_memory_utilization),
                "--max-logprobs",
                str(args.max_logprobs),
                "--trust-remote-code",
            ]
            # `vllm` avoids model generation_config.json defaults such as
            # max_new_tokens being applied at server startup.
            if args.generation_config:
                command.extend(["--generation-config", args.generation_config])
            process = subprocess.Popen(command, env=env)
            backends.append(
                BackendInstance(
                    gpu_id=gpu_id,
                    url=f"http://{args.host}:{backend_port}",
                    process=process,
                )
            )

        for backend in backends:
            wait_for_backend(backend.url, timeout_s=args.startup_timeout_s)

        router = ProxyRouter(
            backends,
            request_timeout_s=args.healthcheck_timeout_s,
            debug_log_requests=args.debug_log_requests or args.debug_log_completions,
            debug_max_chars=args.debug_max_chars,
        )
        server = create_gateway_server(
            host=args.host,
            port=gateway_port,
            router=router,
        )

        def monitor_backend_processes() -> None:
            while not stop_event.is_set():
                for backend in backends:
                    return_code = backend.process.poll()
                    if return_code is not None:
                        failure_holder["message"] = (
                            f"backend on gpu={backend.gpu_id} exited "
                            f"with code {return_code}"
                        )
                        stop_event.set()
                        if server is not None:
                            server.shutdown()
                        return
                time.sleep(1.0)

        monitor_thread = threading.Thread(
            target=monitor_backend_processes,
            daemon=True,
        )
        monitor_thread.start()

        print(f"Gateway URL: http://{args.host}:{gateway_port}")
        for backend in backends:
            print(f"Backend GPU {backend.gpu_id}: {backend.url}")

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
            server.shutdown()
            server.server_close()
        if failure_holder:
            raise RuntimeError(failure_holder["message"])
    finally:
        stop_event.set()
        for backend in backends:
            if backend.process.poll() is None:
                backend.process.terminate()
        deadline = time.time() + 10.0
        for backend in backends:
            if backend.process.poll() is None:
                remaining = max(0.0, deadline - time.time())
                try:
                    backend.process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    backend.process.kill()
        for backend in backends:
            if backend.process.poll() is None:
                backend.process.wait(timeout=5.0)


if __name__ == "__main__":
    main()
