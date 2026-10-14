"""The --selftest entry point CI runs against the built EXE (review F1)."""
import subprocess
import sys


def test_selftest_passes_from_source():
    import app.main as appmain
    assert appmain.selftest() == 0


def test_selftest_exit_code_via_argv():
    r = subprocess.run([sys.executable, "app/main.py", "--selftest"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "selftest: ok" in r.stdout


def test_selftest_fails_without_data(monkeypatch):
    import app.main as appmain
    import meseventool.xdf as xdf

    class Broken:
        def __init__(self, *a, **k):
            raise FileNotFoundError("xdf_tables.json")
    monkeypatch.setattr(xdf, "XDFLoader", Broken)
    assert appmain.selftest() == 1
