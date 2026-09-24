import re
from pathlib import Path
from setuptools import setup, find_packages

# Single source of truth for the version: meseventool/version.py
_VERSION = re.search(
    r'__version__\s*=\s*"([^"]+)"',
    (Path(__file__).parent / "meseventool" / "version.py").read_text(),
).group(1)

setup(
    name="meseventool",
    version=_VERSION,
    packages=find_packages(),
    python_requires=">=3.10",
)
