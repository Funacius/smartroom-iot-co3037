import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def make_server(gateway, host="127.0.0.1", port=8080):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type="application/json; charset=utf-8"):
            data = (json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else body).encode(
                "utf-8"
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self.reply(
                    200,
                    Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8"),
                    "text/html; charset=utf-8",
                )
            elif self.path == "/api/state":
                self.reply(200, gateway.snapshot())
            elif self.path == "/api/events.csv":
                stream = io.StringIO(newline="")
                writer = csv.writer(stream)
                writer.writerow(["id", "timestamp_unix", "device", "kind", "detail"])
                with gateway.lock:
                    writer.writerows(
                        tuple(row) for row in gateway.db.execute("SELECT * FROM events ORDER BY id")
                    )
                self.reply(200, stream.getvalue(), "text/csv; charset=utf-8")
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.path != "/api/command":
                return self.reply(404, {"error": "Not found"})
            # The local dashboard is bound to loopback. Also block cross-origin writes.
            origin = self.headers.get("Origin")
            expected = f"http://{self.headers.get('Host')}"
            if origin and origin != expected:
                return self.reply(403, {"error": "Cross-origin command denied"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024:
                    raise ValueError("Invalid body size")
                self.connection.settimeout(2)
                body = json.loads(self.rfile.read(size))
                command = gateway.command(gateway.config["device"], body["value"])
                self.reply(202, command)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                self.reply(400, {"error": str(exc)})

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer((host, port), Handler)
