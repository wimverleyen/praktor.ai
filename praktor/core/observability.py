import time
import json
from dataclasses import dataclass, field

from settings import create_log

log = create_log()


@dataclass
class Span:
    """
    Lightweight observability span for a single agent request.

    Logs structured JSON to praktor.ai.log on finish().
    Drop-in: replace with OpenTelemetry later without changing call sites.
    """

    agent_type: str
    session_id: str
    model: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    token_count: int = 0
    cached: bool = False
    passes: int = 1
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    def finish(
        self,
        token_count: int = 0,
        cached: bool = False,
        passes: int = 1,
        error: str | None = None,
    ) -> None:
        self.end_time = time.time()
        self.token_count = token_count
        self.cached = cached
        self.passes = passes
        self.error = error
        self._emit()

    def _emit(self) -> None:
        record: dict = {
            "agent_type": self.agent_type,
            "session_id": self.session_id,
            "model": self.model,
            "duration_ms": round(self.duration_ms, 2),
            "token_count": self.token_count,
            "passes": self.passes,
            "cached": self.cached,
        }
        if self.error:
            record["error"] = self.error
            log.error(f"SPAN {json.dumps(record)}")
        else:
            log.info(f"SPAN {json.dumps(record)}")
