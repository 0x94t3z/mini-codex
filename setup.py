# ruff: noqa: I001

import sys
from pathlib import Path

from setuptools import find_packages, setup

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mini_codex.version import VERSION  # noqa: E402


setup(
    name="mini-codex",
    version=VERSION,
    description="A small terminal coding assistant powered by OpenRouter.",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "openai>=2.0.0,<3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "mini-codex=mini_codex.cli:main",
        ]
    },
)
