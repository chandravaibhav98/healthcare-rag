from __future__ import annotations

from pathlib import Path

import pytest

from scripts.pipeline import main

pytestmark = pytest.mark.integration


def test_build_verify_inspect(
    tmp_path: Path, fixture_corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "idx"
    assert main(["build", "--corpus", str(fixture_corpus), "--out", str(out)]) == 0
    assert "index_version" in capsys.readouterr().out

    assert main(["verify", "--index", str(out), "--corpus", str(fixture_corpus)]) == 0
    assert main(["inspect", "--index", str(out), "--stats"]) == 0
    assert "tokens/chunk" in capsys.readouterr().out
    assert main(["inspect", "--index", str(out), "--doc", "who-tst-001"]) == 0
    assert "who-tst-001::procedure::0001" in capsys.readouterr().out
    assert main(["inspect", "--index", str(out), "--chunk", "who-tst-001::procedure::0001"]) == 0
    assert main(["inspect", "--index", str(out), "--doc", "missing-doc"]) == 1


def test_errors_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", "--corpus", str(tmp_path / "none"), "--out", str(tmp_path / "o")]) == 1
    assert "corpus directory not found" in capsys.readouterr().err
    assert main(["verify", "--index", str(tmp_path / "o"), "--no-corpus"]) == 1


def test_determinism_command(
    tmp_path: Path, fixture_corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "m" / "manifest.json"
    assert (
        main(
            [
                "determinism",
                "--corpus",
                str(fixture_corpus),
                "--runs",
                "2",
                "--save-manifest",
                str(saved),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "PASS  2 builds byte-identical" in out
    assert saved.is_file()
