from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import uuid


@dataclass(frozen=True)
class NormalQRecord:
    record_id: str
    video_path: str
    target_frame: int
    window: dict[str, object]
    q_C: float | None
    sigma_q_C: float | None
    valid: bool
    selected: bool = True
    flags: list[str] = field(default_factory=list)
    run_dir: str | None = None

    @classmethod
    def create(
        cls,
        *,
        video_path: str,
        target_frame: int,
        window: dict[str, object],
        q_C: float | None,
        sigma_q_C: float | None,
        valid: bool,
        selected: bool = True,
        flags: list[str] | None = None,
        run_dir: str | None = None,
    ) -> "NormalQRecord":
        return cls(
            record_id=f"q_{uuid.uuid4().hex[:12]}",
            video_path=str(video_path),
            target_frame=int(target_frame),
            window=dict(window),
            q_C=q_C,
            sigma_q_C=sigma_q_C,
            valid=bool(valid),
            selected=bool(selected),
            flags=list(flags or []),
            run_dir=run_dir,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class NormalSession:
    records: list[NormalQRecord] = field(default_factory=list)
    inversion: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "records": [record.to_dict() for record in self.records],
            "inversion": self.inversion,
        }

    def counts(self) -> dict[str, int]:
        total = len(self.records)
        valid = sum(1 for record in self.records if record.valid)
        selected_valid = sum(1 for record in self.records if record.valid and record.selected)
        return {"total": total, "valid": valid, "selected_valid": selected_valid}


def save_session(session: NormalSession, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def load_session(path: str | Path) -> NormalSession:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = [NormalQRecord(**row) for row in payload.get("records", [])]
    return NormalSession(records=records, inversion=payload.get("inversion"))

