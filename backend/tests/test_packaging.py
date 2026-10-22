"""Docker installs requirements.txt; serverless hosts may install from pyproject.toml. Keep them equal."""

import os
import tomllib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pyproject_and_requirements_pin_the_same_packages():
    with open(os.path.join(HERE, "requirements.txt")) as f:
        reqs = {line.strip() for line in f if line.strip() and not line.startswith("#")}
    with open(os.path.join(HERE, "pyproject.toml"), "rb") as f:
        deps = set(tomllib.load(f)["project"]["dependencies"])
    assert reqs == deps


def test_serverless_entry_point_exposes_the_app():
    with open(os.path.join(HERE, "main.py")) as f:
        assert "from app.main import app" in f.read()
