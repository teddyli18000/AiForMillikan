from pathlib import Path

from scripts.check_text_encoding import scan_paths


def test_encoding_scan_rejects_invalid_utf8_and_mojibake(tmp_path: Path):
    valid = tmp_path / "valid.md"
    invalid = tmp_path / "invalid.md"
    replacement = tmp_path / "replacement.ts"
    mojibake = tmp_path / "mojibake.txt"
    valid.write_text("正在处理：σ = 10⁻¹⁹ C", encoding="utf-8")
    invalid.write_bytes(b"\xff\xfe")
    replacement.write_text("broken " + chr(0xFFFD), encoding="utf-8")
    mojibake.write_text("\u59dd\uff45\u6e6a\u95b2\u56e8\u726c", encoding="utf-8")

    issues = scan_paths([valid, invalid, replacement, mojibake])

    assert [issue.kind for issue in issues] == [
        "invalid_utf8",
        "replacement_character",
        "mojibake",
    ]


def test_encoding_scan_accepts_normal_chinese_and_scientific_symbols(tmp_path: Path):
    source = tmp_path / "normal.py"
    source.write_text('label = "正在处理：σ = 10⁻¹⁹ C"\n', encoding="utf-8")

    assert scan_paths([source]) == []
