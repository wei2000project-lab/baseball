import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_configure(config):
    if not config.option.basetemp:
        config.option.basetemp = str(Path(__file__).resolve().parents[1] / "build/pytest-temp")
