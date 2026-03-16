"""
meseventool/kwp.py
==================
Optional KWPBridge live data integration for MESevenTool.

MESevenTool is fully standalone. KWPBridge is optional — when running
alongside MESevenTool it provides:
  - Live RPM, load, coolant overlaid on map cells
  - Lambda and ignition timing readouts
  - Part-number safety gate before any ROM write

The tool auto-detects KWPBridge on localhost:50266 and connects
without any user action. If KWPBridge is not installed or not running,
all overlay code is simply skipped.

Architecture
------------
_KWP_AVAILABLE : bool  — kwpbridge package importable
_QT_AVAILABLE  : bool  — PyQt5 importable

If both true  → real KWPMonitor (QObject with Qt signals, auto-polling)
Otherwise     → stub KWPMonitor with _NoOpSignal attributes

App code can always safely call:
    self._kwp_monitor.connected.connect(...)
without guarding for AttributeError.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    from kwpbridge.client import KWPClient, is_running as _kwp_is_running
    from kwpbridge.constants import DEFAULT_PORT
    _KWP_AVAILABLE = True
except ImportError:
    _KWP_AVAILABLE = False
    DEFAULT_PORT   = 50266

try:
    from PyQt5.QtCore import QObject, QTimer, pyqtSignal
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False


def kwpbridge_available() -> bool:
    return _KWP_AVAILABLE

def kwpbridge_running() -> bool:
    if not _KWP_AVAILABLE:
        return False
    try:
        return _kwp_is_running(port=DEFAULT_PORT)
    except Exception:
        return False


# ── Live values extracted from KWPBridge state ────────────────────────────────

class LiveValues:
    """
    Decoded ME7 measuring block values from a KWPBridge state dict.
    All values are None if not available.
    """

    def __init__(self, state: dict):
        self.rpm:      Optional[float] = None
        self.load:     Optional[float] = None    # % relative air charge
        self.coolant:  Optional[float] = None    # °C
        self.lambda_:  Optional[float] = None    # λ (1.0 = stoich)
        self.timing:   Optional[float] = None    # °BTDC
        self.battery:  Optional[float] = None    # V
        self.maf:      Optional[float] = None    # g/s MAF
        self.boost:    Optional[float] = None    # mbar MAP sensor
        self.ecu_pn:   str = ""

        if not state or not state.get("connected"):
            return

        self.ecu_pn = state.get("ecu_id", {}).get("part_number", "")
        groups = state.get("groups", {})

        # ME7 measuring blocks use group 0 layout:
        #   cell 1: RPM, cell 2: load %, cell 3: coolant °C
        #   cell 4: battery V, cell 5: MAF g/s
        #   cell 8: lambda, cell 10: ignition timing °BTDC
        #   cell 15: MAP mbar
        group0 = groups.get("0", groups.get(0, {}))
        cells  = {c["index"]: c for c in group0.get("cells", [])}

        def _v(idx):
            c = cells.get(idx)
            return c["value"] if c else None

        self.rpm     = _v(1)
        self.load    = _v(2)
        self.coolant = _v(3)
        self.battery = _v(4)
        self.maf     = _v(5)
        self.lambda_ = _v(8)
        self.timing  = _v(10)
        self.boost   = _v(15)

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

if _QT_AVAILABLE and _KWP_AVAILABLE:

    class KWPMonitor(QObject):
        """
        Qt wrapper around KWPClient. Emits signals for MESevenTool.

        connected(str)        — ecu part number on connection
        disconnected()        — connection lost
        live_data(LiveValues) — new state at poll rate
        mismatch(str, str)    — (ecu_pn, rom_pn) when PNs differ
        """

        connected    = pyqtSignal(str)
        disconnected = pyqtSignal()
        live_data    = pyqtSignal(object)
        mismatch     = pyqtSignal(str, str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._client:  KWPClient | None = None
            self._rom_pns: list[str] = []
            self._matched  = False

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._poll)
            self._timer.start(1000)

        def set_rom_part_numbers(self, pns: list[str]):
            self._rom_pns = [p.upper().replace("-", "").strip() for p in pns]
            self._check_match()

        def start(self):  self._timer.start(1000)
        def stop(self):
            self._timer.stop()
            self._disconnect_client()

        def is_matched(self) -> bool: return self._matched
        def current_pn(self) -> str:
            if self._client and self._client.state:
                return self._client.state.get(
                    "ecu_id", {}).get("part_number", "")
            return ""

        def _poll(self):
            if self._client and self._client.connected:
                state = self._client.state
                if state:
                    lv = LiveValues(state)
                    if lv.valid:
                        self.live_data.emit(lv)
                    self._check_match()
                return
            if kwpbridge_running():
                self._connect_client()

        def _connect_client(self):
            try:
                self._client = KWPClient(port=DEFAULT_PORT)
                self._client.on_connect(self._on_connect)
                self._client.on_disconnect(self._on_disconnect)
                self._client.on_state(self._on_state)
                self._client.connect(auto_reconnect=False)
            except Exception as e:
                log.debug(f"KWPMonitor: connect error: {e}")
                self._client = None

        def _disconnect_client(self):
            if self._client:
                try: self._client.disconnect()
                except Exception: pass
                self._client = None
            self._matched = False

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
            self._matched = ecu_pn in self._rom_pns
            if not self._matched and ecu_pn:
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

        def __init__(self, parent=None): pass
        def set_rom_part_numbers(self, pns): pass
        def start(self): pass
        def stop(self):  pass
        def is_matched(self) -> bool: return False
        def current_pn(self) -> str:  return ""


# ── Status helpers ────────────────────────────────────────────────────────────

def status_label(monitor: "KWPMonitor", rom_pn: str = "") -> tuple[str, str]:
    """Return (text, colour) for a KWP status badge."""
    if not _KWP_AVAILABLE:
        return "KWPBridge not installed", "#555555"
    if not kwpbridge_running():
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
    if lv.coolant is not None: parts.append(f"{lv.coolant:.0f}°C")
    if lv.lambda_ is not None: parts.append(f"λ {lv.lambda_:.3f}")
    if lv.timing  is not None: parts.append(f"{lv.timing:.1f}° ign")
    if lv.boost   is not None: parts.append(f"{lv.boost:.0f} mbar")
    return "  ·  ".join(parts)
