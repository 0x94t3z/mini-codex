from setuptools import setup, find_packages


setup(
    name="mini-codex",
    version="0.1.0",
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
