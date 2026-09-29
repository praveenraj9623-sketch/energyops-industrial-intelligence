import hashlib

from energyops.config import source_path
from energyops.provenance import file_identity, sha256_file


def test_checksum_and_identity(tmp_path):
    path = tmp_path / "small.csv"
    path.write_bytes(b"a,b\n1,2\n")
    expected = hashlib.sha256(b"a,b\n1,2\n").hexdigest()
    assert sha256_file(path) == expected
    assert file_identity(path) == {"filename": "small.csv", "size_bytes": 8, "sha256": expected}


def test_source_selection_and_missing_error(tmp_path, monkeypatch):
    path = tmp_path / "sample.csv"
    path.write_text("sample", encoding="utf-8")
    monkeypatch.setenv("ENERGYOPS_SOURCE_CSV", str(path))
    assert source_path() == path.resolve()
    assert source_path(path) == path.resolve()
    monkeypatch.setenv("ENERGYOPS_SOURCE_CSV", str(tmp_path / "missing.csv"))
    try:
        source_path()
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as exc:
        assert "Pass --source" in str(exc)
