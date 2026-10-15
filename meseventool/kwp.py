"""
meseventool/kwp.py
==================
Optional KWPBridge live data integration for MESevenTool.

MESevenTool is fully standalone. KWPBridge is optional — when running
alongside MESevenTool it provides:
  - Live RPM, load, coolant, ignition, boost readouts
  - Part-number safety gate before any ROM write

The tool auto-detects KWPBridge on localhost:50266 and connects
without any user action. If KWPBridge is not installed or not running,
all overlay code is simply skipped.

Design (review G1, G2, G4)
--------------------------
- The "is KWPBridge running?" TCP probe runs on a background thread and
  the result is cached in ``KWPMonitor.bridge_running``.  The GUI never
  opens a socket on the UI thread.
- Exactly one ``KWPClient`` exists at a time: a dropped client is
  disconnected and released before a new one is created, and reconnects
  are rate-limited.
- Live values are picked out of the server's state by cell *label* across
  every measuring group KWPBridge is polling.  ME7 has no "group 0": RPM,
  load, coolant, ignition timing, boost and knock retard live in the
  standard 4-cell groups (1, 2, 3, 4, 10, 91, 94…), and group 1's "Lambda
  Controller" is a percent correction, not λ.

Architecture
------------
_KWP_AVAILABLE : bool  — kwpbridge package importable
_QT_AVAILABLE  : bool  — PyQt5 importable

If Qt is available → real KWPMonitor (QObject with Qt signals, polling);
it is inert when kwpbridge is not installed.  Without Qt → stub with
_NoOpSignal attributes, so app code can always call
``self._kwp_monitor.connected.connect(...)`` without guarding.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Iterator, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    from kwpbridge.client import KWPClient, is_running as _kwp_is_running
    from kwpbridge.constants import DEFAULT_PORT
    _KWP_AVAILABLE = True
except ImportError:
    KWPClient       = None   # type: ignore[assignment]
    _kwp_is_running = None   # type: ignore[assignment]
    _KWP_AVAILABLE  = False
    DEFAULT_PORT    = 50266

try:
    from PyQt5.QtCore import QObject, QTimer, pyqtSignal
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False


PROBE_INTERVAL_S     = 2.0    # background "is the bridge up?" check
PROBE_TIMEOUT_S      = 0.2
POLL_INTERVAL_MS     = 1000   # UI-thread timer: read cached state only
RECONNECT_BACKOFF_S  = 3.0

# Measuring groups that carry everything LiveValues looks for on ME7.
# KWPMonitor.request_groups() can ask the bridge to poll these; it is not
# done automatically so the bridge's own display is not disturbed.
PREFERRED_GROUPS = [1, 3, 4, 91, 94]


def kwpbridge_available() -> bool:
    return _KWP_AVAILABLE


def kwpbridge_running(timeout: float = PROBE_TIMEOUT_S) -> bool:
    """Blocking TCP probe (up to ``timeout`` seconds).  GUI code should
    read ``KWPMonitor.bridge_running`` instead, which a background thread
    keeps current (review G1)."""
    if not _KWP_AVAILABLE:
        return False
    try:
        return bool(_kwp_is_running(port=DEFAULT_PORT, timeout=timeout))
    except Exception:
        return False


# ── Live values extracted from KWPBridge state ────────────────────────────────

def _iter_cells(state: dict) -> Iterator[Tuple[int, int, str, Optional[float], str]]:
    """Yield (group, index, label, value, unit) for every cell, groups in
    ascending order.  Accepts the dict-of-groups form the server sends
    (keys may be str or int) and tolerates missing fields."""
    groups = state.get("groups") or {}
    items = groups.items() if isinstance(groups, dict) else enumerate(groups)
    parsed = []
    for key, g in items:
        if not isinstance(g, dict):
            continue
        try:
            gid = int(g.get("group", key))
        except (TypeError, ValueError):
            continue
        parsed.append((gid, g))
    for gid, g in sorted(parsed, key=lambda t: t[0]):
        for c in g.get("cells") or []:
            if not isinstance(c, dict):
                continue
            try:
                idx = int(c.get("index", 0))
            except (TypeError, ValueError):
                idx = 0
            v = c.get("value")
            try:
                val = float(v) if v is not None else None
            except (TypeError, ValueError):
                val = None
            yield gid, idx, str(c.get("label") or ""), val, str(c.get("unit") or "")


class LiveValues:
    """
    Decoded ME7 measuring block values from a KWPBridge state dict.
    All values are None if not available.

    Values are matched by cell label (as KWPBridge's ECU definitions name
    them), so they are found in whichever groups the bridge is polling.
    """

    # (attribute, label fragments in priority order, acceptable units or None)
    _FIELDS = [
        ("rpm",         ("Engine Speed",),                                   ("RPM", "")),
        ("load",        ("Engine Load", "Load"),                             ("%", "")),
        ("coolant",     ("Coolant Temp",),                                   ("°C", "C", "")),
        ("battery",     ("Voltage Supply", "Battery"),                       ("V", "")),
        ("maf",         ("Intake Air Mass", "MAF"),                          ("g/s", "")),
        ("timing",      ("Ignition Timing Actual", "Ignition Timing"),       ("°", "deg", "°BTDC", "")),
        ("boost",       ("Boost Pressure",),                                 ("mbar", "kPa", "bar", "")),
        ("knock_retard", ("Knock Retard Total",),                            None),
        ("iat",         ("Intake Air Temp",),                                ("°C", "C", "")),
        ("lambda_ctrl", ("Lambda Controller",),                              ("%", "")),
        ("o2_voltage",  ("O2 Sensor 1 Upstream Voltage", "Upstream O2 Voltage"), None),
    ]

    def __init__(self, state: dict):
        self.rpm:          Optional[float] = None
        self.load:         Optional[float] = None    # % relative air charge
        self.coolant:      Optional[float] = None    # °C
        self.lambda_:      Optional[float] = None    # λ (1.0 = stoich), if the bridge reports one
        self.lambda_ctrl:  Optional[float] = None    # % lambda controller correction (group 1)
        self.timing:       Optional[float] = None    # °BTDC
        self.battery:      Optional[float] = None    # V
        self.maf:          Optional[float] = None    # g/s MAF
        self.boost:        Optional[float] = None    # mbar
        self.knock_retard: Optional[float] = None    # ° total knock retard
        self.iat:          Optional[float] = None    # °C
        self.o2_voltage:   Optional[float] = None    # V, upstream sensor
        self.ecu_pn:       str = ""
        self.groups_seen:  List[int] = []

        if not state or not state.get("connected"):
            return

        self.ecu_pn = (state.get("ecu_id") or {}).get("part_number", "") or ""
        cells = list(_iter_cells(state))
        self.groups_seen = sorted({g for g, *_ in cells})

        for attr, fragments, units in self._FIELDS:
            for frag in fragments:          # priority: first fragment, first group
                for gid, idx, label, val, unit in cells:
                    if val is None or not label.startswith(frag):
                        continue
                    if units is not None and unit not in units:
                        continue
                    setattr(self, attr, val)
                    break
                if getattr(self, attr) is not None:
                    break

        # λ proper: a "Lambda" cell that is not a percent and is in range
        for gid, idx, label, val, unit in cells:
            if val is None or "Lambda" not in label or unit == "%":
                continue
            if 0.5 <= val <= 1.5:
                self.lambda_ = val
                break

    @property
    def valid(self) -> bool:
        return self.rpm is not None

    def lambda_colour(self) -> str:
        if self.lambda_ is None:
            return "#444444"
        if 0.95 <= self.lambda_ <= 1.05:
            return "#2dff6e"
        if 0.85 <= self.lambda_ < 0.95 or 1.05 < self.lambda_ <= 1.15:
            return "#ffaa00"
        return "#ff4444"


# ── Qt monitor (real implementation) ─────────────────────────────────────────

if _QT_AVAILABLE:

    class KWPMonitor(QObject):
        """
        Qt wrapper around KWPClient. Emits signals for MESevenTool.

        connected(str)        — ecu part number on connection
        disconnected()        — connection lost
        live_data(LiveValues) — new state at poll rate
        mismatch(str, str)    — (ecu_pn, rom_pn) when PNs differ

        Nothing here blocks the UI thread: the bridge probe runs on its
        own thread (review G1) and KWPClient reads on its own thread.
        """

        connected    = pyqtSignal(str)
        disconnected = pyqtSignal()
        live_data    = pyqtSignal(object)
        mismatch     = pyqtSignal(str, str)

        def __init__(self, parent=None, port: int = DEFAULT_PORT,
                     probe_interval: float = PROBE_INTERVAL_S):
            super().__init__(parent)
            self.port = port
            self._client = None
            self._rom_pns: list[str] = []
            self._matched  = False
            self._bridge_running = False
            self._last_connect_attempt = 0.0
            self._probe_interval = probe_interval
            self._probe_stop = threading.Event()
            self._probe_thread: Optional[threading.Thread] = None

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._poll)
            if _KWP_AVAILABLE:
                self._start_probe()
                self._timer.start(POLL_INTERVAL_MS)

        # ── Public ────────────────────────────────────────────────────────────

        @property
        def bridge_running(self) -> bool:
            """Cached result of the background probe (never blocks)."""
            return self._bridge_running

        def set_rom_part_numbers(self, pns: list[str]):
            self._rom_pns = [p.upper().replace("-", "").strip() for p in pns]
            self._check_match()

        def start(self):
            if _KWP_AVAILABLE:
                self._start_probe()
                self._timer.start(POLL_INTERVAL_MS)

        def stop(self):
            self._timer.stop()
            self._probe_stop.set()
            t = self._probe_thread
            if t and t.is_alive() and t is not threading.current_thread():
                t.join(timeout=PROBE_TIMEOUT_S + 1.0)
            self._probe_thread = None
            self._disconnect_client()

        def is_matched(self) -> bool:
            return self._matched

        def current_pn(self) -> str:
            c = self._client
            state = c.state if c else None
            if state:
                return (state.get("ecu_id") or {}).get("part_number", "") or ""
            return ""

        def request_groups(self, groups: Optional[list[int]] = None) -> bool:
            """Ask the bridge to poll ``groups`` (default PREFERRED_GROUPS).
            Explicit, never automatic, so the bridge's own display is left
            alone unless the user asks."""
            c = self._client
            if not c or not c.connected:
                return False
            try:
                c.set_groups(list(groups or PREFERRED_GROUPS))
                return True
            except Exception as e:
                log.debug(f"KWPMonitor: set_groups failed: {e}")
                return False

        # ── Background probe (review G1) ──────────────────────────────────────

        def _start_probe(self):
            if self._probe_thread and self._probe_thread.is_alive():
                return
            self._probe_stop.clear()
            self._probe_thread = threading.Thread(
                target=self._probe_loop, name="kwpbridge-probe", daemon=True)
            self._probe_thread.start()

        def _probe_loop(self):
            while not self._probe_stop.is_set():
                try:
                    running = bool(_kwp_is_running(port=self.port, timeout=PROBE_TIMEOUT_S))
                except Exception:
                    running = False
                self._bridge_running = running
                self._probe_stop.wait(self._probe_interval)

        # ── UI-thread poll: reads cached state only ───────────────────────────

        def _poll(self):
            c = self._client
            if c is not None:
                if c.connected:
                    state = c.state
                    if state:
                        lv = LiveValues(state)
                        if lv.valid:
                            self.live_data.emit(lv)
                        self._check_match()
                    return
                # dropped: release it (review G2) and fall through to reconnect
                self._disconnect_client()
            if self._bridge_running and \
                    time.monotonic() - self._last_connect_attempt >= RECONNECT_BACKOFF_S:
                self._connect_client()

        def _connect_client(self):
            self._last_connect_attempt = time.monotonic()
            self._disconnect_client()          # never two clients (review G2)
            if KWPClient is None:
                return
            try:
                client = KWPClient(port=self.port)
                client.on_connect(self._on_connect)
                client.on_disconnect(self._on_disconnect)
                client.on_state(self._on_state)
                self._client = client
                client.connect(auto_reconnect=False)   # starts its own thread
            except Exception as e:
                log.debug(f"KWPMonitor: connect error: {e}")
                self._client = None

        def _disconnect_client(self):
            c, self._client = self._client, None
            if c is not None:
                try:
                    c.disconnect()
                except Exception:
                    pass
            self._matched = False

        # ── Client-thread callbacks (signals are queued to the UI thread) ────

        def _on_connect(self):
            pn = self.current_pn()
            self.connected.emit(pn)
            self._check_match()

        def _on_disconnect(self):
            self._matched = False
            self.disconnected.emit()

        def _on_state(self, state: dict):
            lv = LiveValues(state)
            if lv.valid:
                self.live_data.emit(lv)
            self._check_match()

        def _check_match(self):
            ecu_pn = self.current_pn().upper().replace("-", "").strip()
            if not ecu_pn or not self._rom_pns:
                self._matched = False
                return
            was = self._matched
            self._matched = ecu_pn in self._rom_pns
            if not self._matched and (was or not getattr(self, "_mismatch_reported", "") == ecu_pn):
                self._mismatch_reported = ecu_pn
                self.mismatch.emit(ecu_pn, self._rom_pns[0] if self._rom_pns else "")

else:
    # Stub — safe no-ops, signal attributes present for unconditional .connect()

    class _NoOpSignal:
        def connect(self, *a, **kw):    pass
        def disconnect(self, *a, **kw): pass
        def emit(self, *a, **kw):       pass

    class KWPMonitor:  # type: ignore
        connected    = _NoOpSignal()
        disconnected = _NoOpSignal()
        live_data    = _NoOpSignal()
        mismatch     = _NoOpSignal()
        bridge_running = False

        def __init__(self, parent=None, port: int = DEFAULT_PORT, probe_interval: float = 0): pass
        def set_rom_part_numbers(self, pns): pass
        def start(self): pass
        def stop(self):  pass
        def is_matched(self) -> bool: return False
        def current_pn(self) -> str:  return ""
        def request_groups(self, groups=None) -> bool: return False


# ── Status helpers ────────────────────────────────────────────────────────────

def status_label(monitor: "KWPMonitor", rom_pn: str = "") -> tuple[str, str]:
    """Return (text, colour) for a KWP status badge.  Uses the monitor's
    cached probe; only falls back to a blocking probe without a monitor."""
    if not _KWP_AVAILABLE:
        return "KWPBridge not installed", "#555555"
    running = monitor.bridge_running if monitor is not None else kwpbridge_running()
    if not running:
        return "KWPBridge not running", "#555555"
    ecu_pn = monitor.current_pn() if monitor else ""
    if not ecu_pn:
        return "KWPBridge running — no ECU", "#ffaa00"
    if monitor and monitor.is_matched():
        return f"🟢  {ecu_pn}  ·  ECU matches ROM", "#2dff6e"
    return f"🟡  {ecu_pn}  ≠  {rom_pn}  ·  mismatch", "#ffaa00"


def live_summary(lv: "LiveValues") -> str:
    """One-line summary for a status bar."""
    if lv is None or not lv.valid:
        return ""
    parts = []
    if lv.rpm     is not None: parts.append(f"{lv.rpm:.0f} RPM")
    if lv.load    is not None: parts.append(f"{lv.load:.0f}% load")
    if lv.coolant is not None: parts.append(f"{lv.coolant:.0f}°C")
    if lv.lambda_ is not None: parts.append(f"λ {lv.lambda_:.3f}")
    if lv.timing  is not None: parts.append(f"{lv.timing:.1f}° ign")
    if lv.boost   is not None: parts.append(f"{lv.boost:.0f} mbar")
    if lv.knock_retard: parts.append(f"KR {lv.knock_retard:.1f}°")
    return "  ·  ".join(parts)
