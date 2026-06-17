from __future__ import annotations

from typing import Any


def render_session_report(session: dict[str, Any], inversion: dict[str, Any] | None) -> str:
    records = list(session.get("records", []) or [])
    selected_valid = [row for row in records if row.get("valid") and row.get("selected", True)]
    lines = [
        "# Normal Mode Session Report",
        "",
        f"- total_records: {len(records)}",
        f"- selected_valid_records: {len(selected_valid)}",
    ]
    if len(selected_valid) < 3 or not inversion:
        return "\n".join(lines) + "\n"
    normal = inversion.get("normal_algorithm", {}) if isinstance(inversion, dict) else {}
    experimental = inversion.get("experimental_algorithm", {}) if isinstance(inversion, dict) else {}
    normal_ok = bool(normal.get("valid"))
    experimental_ok = bool(
        experimental.get("fundamental_spacing_identified")
        or (experimental.get("bounded_estimate_available") and experimental.get("quantization_supported") is True)
    )
    if not normal_ok and not experimental_ok:
        return "\n".join(lines) + "\n"
    lines.extend(["", "## Blind inversion", ""])
    if normal_ok:
        lines.extend(["### Normal algorithm", "", f"- e_hat_C: {normal.get('e_hat_C')}"])
    if experimental_ok:
        lines.extend(["", "### Experimental algorithm", "", f"- status: {experimental.get('status', '-')}"])
    return "\n".join(lines) + "\n"
