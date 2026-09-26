"""Nonblocking pipe exchange with bounded reads, timeouts and owned-child cleanup."""

import os
import selectors
import subprocess
import sys
from time import monotonic_ns

from iaa.types import identity

from .wire import MAX_BYTES, dumps, loads, request


class Client:
    def __init__(self, role, fault="none"):
        self.role, self.sequence, self.closed = role, 0, False
        start = monotonic_ns()
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "sa04.service", role, "--fault", fault],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            hello = loads(self.exchange(b"", 4_000_000_000))
            if hello.get("schema") != "iaa-worker-ready/4" or hello.get("role") != role:
                raise ValueError("Worker handshake")
            self.session = hello["session"]
        except Exception:
            self.close()
            raise
        self.startup_ns = monotonic_ns() - start

    def exchange(self, outgoing, timeout_ns):
        if self.closed or type(timeout_ns) is not int or timeout_ns <= 0:
            raise ValueError("Closed worker or invalid timeout")
        if len(outgoing) > MAX_BYTES + 1:
            raise ValueError("Output frame too large")
        deadline = monotonic_ns() + timeout_ns
        received, sent = bytearray(), 0
        with selectors.DefaultSelector() as sel:
            sel.register(self.process.stdout, selectors.EVENT_READ)
            if outgoing:
                sel.register(self.process.stdin, selectors.EVENT_WRITE)
            while True:
                remaining = deadline - monotonic_ns()
                if remaining <= 0:
                    raise TimeoutError("Host response deadline expired")
                for key, event in sel.select(remaining / 1e9):
                    if event & selectors.EVENT_WRITE:
                        n = os.write(key.fd, outgoing[sent:])
                        sent += n
                        if sent == len(outgoing):
                            sel.unregister(self.process.stdin)
                    if event & selectors.EVENT_READ:
                        part = os.read(key.fd, 8192)
                        if not part:
                            raise EOFError("Worker exited or truncated a frame")
                        received.extend(part)
                        if len(received) > MAX_BYTES + 1:
                            raise ValueError("Input frame too large")
                        if b"\n" in received:
                            if not received.endswith(b"\n") or received.count(b"\n") != 1:
                                raise ValueError("Multiple or trailing response frames")
                            return bytes(received[:-1])

    def call(self, payload, timeout_ns=5_000_000_000):
        start = monotonic_ns()
        req = request(self.role, self.sequence, payload, self.session)
        self.sequence += 1
        serial_start = monotonic_ns()
        raw = dumps(req) + b"\n"
        serial_ns = monotonic_ns() - serial_start
        try:
            exchange_start = monotonic_ns()
            returned = self.exchange(raw, max(1, timeout_ns - (exchange_start - start)))
            exchange_ns = monotonic_ns() - exchange_start
            validate_start = monotonic_ns()
            response = loads(returned)
            if (
                response.get("schema") != "iaa-execution-response/4"
                or response.get("request_sha256") != identity(req)
                or response.get("session") != self.session
                or response.get("sequence") != req["sequence"]
                or response.get("role") != self.role
                or response.get("result_sha256") != identity(response.get("result"))
                or response.get("physical_io") is not False
            ):
                raise ValueError("Response binding, role or integrity mismatch")
            validation_ns = monotonic_ns() - validate_start
            elapsed = monotonic_ns() - start
            if elapsed > timeout_ns:
                raise TimeoutError("Validation finished after the response deadline")
            return response, dict(
                status="completed",
                serialization_ns=serial_ns,
                transport_and_service_ns=exchange_ns,
                validation_ns=validation_ns,
                roundtrip_ns=elapsed,
                request_bytes=len(raw),
                response_bytes=len(returned),
            )
        except (ValueError, OSError, EOFError, TimeoutError, KeyError, TypeError) as exc:
            elapsed = monotonic_ns() - start
            cancel = monotonic_ns()
            self.close()
            return None, dict(
                status=type(exc).__name__,
                roundtrip_ns=elapsed,
                serialization_ns=serial_ns,
                cleanup_ns=monotonic_ns() - cancel,
                request_bytes=len(raw),
                response_bytes=0,
            )

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout):
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
