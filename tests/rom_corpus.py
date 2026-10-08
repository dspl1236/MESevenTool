"""
tests/rom_corpus.py
===================
Locate real ROM images for the integration tests.

The real-ROM tests were written against files in several cloud-session
directories (``/mnt/user-data/uploads``, ``/home/claude/*_stock``,
``/tmp/me7_scan``).  ``find_rom(name)`` looks for ``name`` in every known
corpus directory, so the tests run wherever the files live:

    1. ``$MESEVENTOOL_ROM_DIR``            (set this to your corpus folder)
    2. ``D:\\ME7_corpus``                   (local collection, see SOURCES.txt)
    3. the original cloud-session paths
    4. ``Z:\\Archive\\Google Drive\\home flashing\\ME7``

Matching is forgiving: a leading upload timestamp (``1773719875933_``) is
ignored, and names compare case-insensitively with every run of
non-alphanumerics folded to ``_`` (so ``uni_630HN.bin`` matches
``uni 630HN.bin`` and ``dpffiles_com_3458_...`` matches
``dpffiles.com_3458_...``).  Tests skip when ``find_rom`` returns None.
"""
import os
import re
from functools import lru_cache
from typing import Dict, List, Optional

CORPUS_DIRS: List[str] = [d for d in [
    os.environ.get("MESEVENTOOL_ROM_DIR"),
    r"D:\ME7_corpus",
    "/mnt/user-data/uploads",
    "/home/claude/chiptuning_stock",
    "/home/claude/s4wiki_stock",
    "/tmp/me7_scan",
    r"Z:\Archive\Google Drive\home flashing\ME7",
] if d]

_TS = re.compile(r"^\d{10,}_")


def _key(name: str) -> str:
    stem, ext = os.path.splitext(_TS.sub("", os.path.basename(name)))
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_") + ext.lower()


@lru_cache(maxsize=None)
def _index(directory: str) -> Dict[str, str]:
    """Every image under ``directory`` (recursive), keyed by normalised name.
    The first file seen for a key wins, walking top-down and sorted."""
    out: Dict[str, str] = {}
    if not os.path.isdir(directory):
        return out
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for n in sorted(files):
            if n.lower().endswith((".bin", ".ori", ".rom")):
                out.setdefault(_key(n), os.path.join(root, n))
    return out


def find_rom(name: str) -> Optional[str]:
    """Path of the first corpus file matching ``name``, or None."""
    base = os.path.basename(name)
    for d in CORPUS_DIRS:
        exact = os.path.join(d, base)
        if os.path.exists(exact):
            return exact
    key = _key(base)
    for d in CORPUS_DIRS:
        hit = _index(d).get(key)
        if hit:
            return hit
    return None


def have_rom(name: str) -> bool:
    return find_rom(name) is not None
