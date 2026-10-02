"""Small dependency-free Prometheus exposition and JSON request logging helpers."""
import json
import logging
from collections import defaultdict
from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "message": record.getMessage(), "logger": record.name, "request_id": request_id_context.get()}
        for field in ("component", "status_code", "duration_ms", "user_id", "workspace_id", "job_id", "document_id", "attempt"):
            value = getattr(record, field, None)
            if value is not None: payload[field] = value
        return json.dumps(payload, default=str)


class Metrics:
    def __init__(self):
        self.request_count = defaultdict(int)
        self.request_duration_sum = defaultdict(float)
        self.events = defaultdict(int)

    def request(self, method: str, route: str, status: int, duration_seconds: float) -> None:
        key = (method, route, str(status))
        self.request_count[key] += 1
        self.request_duration_sum[key] += duration_seconds

    def event(self, name: str, outcome: str = "success") -> None:
        self.events[(name, outcome)] += 1

    def render(self) -> str:
        lines = ["# HELP modai_http_requests_total HTTP request count", "# TYPE modai_http_requests_total counter"]
        for (method, route, status), count in self.request_count.items():
            labels = f'method="{method}",route="{route}",status="{status}"'
            lines.append(f"modai_http_requests_total{{{labels}}} {count}")
            lines.append(f"modai_http_request_duration_seconds_sum{{{labels}}} {self.request_duration_sum[(method, route, status)]:.6f}")
        lines.extend(["# HELP modai_events_total Safe platform events", "# TYPE modai_events_total counter"])
        for (name, outcome), count in self.events.items():
            lines.append(f'modai_events_total{{event="{name}",outcome="{outcome}"}} {count}')
        return "\n".join(lines) + "\n"


metrics = Metrics()
