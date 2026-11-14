"""DOCKER-03: every dependency of ai-service is pinned, so Docker and CI install the same versions."""
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parents[1]


def _requirements(name):
    lines = (HERE / name).read_text(encoding="utf-8").splitlines()
    return [ln.split("#")[0].strip() for ln in lines if ln.split("#")[0].strip()]


def test_requirements_txt_is_fully_pinned():
    reqs = _requirements("requirements.txt")
    assert reqs, "requirements.txt is empty"
    loose = [r for r in reqs if not re.fullmatch(r"[A-Za-z0-9_.\-\[\],]+==[A-Za-z0-9_.+\-]+", r)]
    assert not loose, f"use exact '==' versions (regenerate from requirements.in): {loose}"


def test_direct_dependencies_match_requirements_in():
    pins = {r.split("==")[0].split("[")[0].lower(): r.split("==")[1] for r in _requirements("requirements.txt")}
    for r in _requirements("requirements.in"):
        name, version = r.split("==")
        assert pins.get(name.split("[")[0].lower()) == version, f"{r} differs from requirements.txt"



