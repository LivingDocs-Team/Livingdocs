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
    
    # Tách bỏ phần environment marker (; sys_platform...) trước khi kiểm tra regex
    loose = []
    for r in reqs:
        clean_req = r.split(";")[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9_.\-\[\],]+==[A-Za-z0-9_.+\-]+", clean_req):
            loose.append(r)
            
    assert not loose, f"use exact '==' versions (regenerate from requirements.in): {loose}"


def test_direct_dependencies_match_requirements_in():
    # Thêm .split(";")[0] để lấy chính xác chuỗi version không dính marker
    pins = {
        r.split(";")[0].split("==")[0].split("[")[0].lower().strip(): r.split(";")[0].split("==")[1].strip()
        for r in _requirements("requirements.txt")
    }
