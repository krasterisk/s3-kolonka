#!/usr/bin/env python3
"""Tiny HTTPS CONNECT proxy for api.groq.com (geo / Cloudflare blocks)."""

import select
import socket
import threading

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8877
ALLOW = {"api.groq.com"}


def _handle(conn):
    remote = None
    try:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                return
            data += chunk
        line = data.split(b"\r\n", 1)[0].decode("ascii", "replace")
        parts = line.split()
        if len(parts) < 2 or parts[0].upper() != "CONNECT":
            conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        host, _, port = parts[1].partition(":")
        port = int(port or "443")
        if host not in ALLOW:
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return
        remote = socket.create_connection((host, port), timeout=20)
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        sockets = [conn, remote]
        while True:
            readable, _, _ = select.select(sockets, [], [], 90)
            if not readable:
                return
            for sock in readable:
                other = remote if sock is conn else conn
                buf = sock.recv(65536)
                if not buf:
                    return
                other.sendall(buf)
    except OSError:
        pass
    finally:
        if remote:
            remote.close()
        conn.close()


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(32)
    print("groq-proxy listen %s:%s allow=%s" % (LISTEN_HOST, LISTEN_PORT, ",".join(sorted(ALLOW))), flush=True)
    while True:
        conn, _addr = srv.accept()
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
