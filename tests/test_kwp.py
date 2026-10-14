"""
Review items G1, G2, G4: the KWPBridge integration must not block the UI
thread, must keep a single client, and must read ME7 values where the
bridge actually puts them.  The integration test drives the real
kwpbridge client against the bridge's own ME7 mock server when the
package is installed.
"""
import os
import socket
import threading
import time

import pytest

import meseventool.kwp as kwp
from meseventool.kwp import LiveValues, live_summary, status_label

# README example: groups 1 and 91 polled
README_STATE = {
    "connected": True, "protocol": "kwp2000",
    "ecu_id": {"part_number": "06A906032BN", "component": "1.8l T  ME7.5"},
    "groups": {
        "1": {"group": 1, "cells": [
            {"index": 1, "label": "Engine Speed", "value": 820.0, "unit": "RPM"},
            {"index": 2, "label": "Coolant Temp", "value": 90.0, "unit": "°C"},
            {"index": 3, "label": "Lambda Controller", "value": 1.2, "unit": "%"},
            {"index": 4, "label": "Basic Setting Flags", "value": 127.0, "unit": ""}]},
        "91": {"group": 91, "cells": [
            {"index": 1, "label": "Engine Speed", "value": 3500.0, "unit": "RPM"},
            {"index": 2, "label": "Engine Load", "value": 42.3, "unit": "%"},
            {"index": 3, "label": "N75 Duty Cycle", "value": 22.0, "unit": "%"},
            {"index": 4, "label": "Boost Pressure", "value": 1120.0, "unit": "mbar"}]},
    },
}


# ── G4: label-based extraction ───────────────────────────────────────────────

class TestLiveValues:
    def test_readme_example(self):
        lv = LiveValues(README_STATE)
        assert lv.valid and lv.ecu_pn == "06A906032BN"
        assert lv.rpm == 820.0                # lowest group wins
        assert lv.coolant == 90.0
        assert lv.load == 42.3
        assert lv.boost == 1120.0
        assert lv.lambda_ctrl == 1.2          # a % correction …
        assert lv.lambda_ is None             # … not λ
        assert lv.timing is None and lv.knock_retard is None
        assert lv.groups_seen == [1, 91]

    def test_me7_groups_3_4_94(self):
        state = {"connected": True, "ecu_id": {"part_number": "06A906032DL"}, "groups": {
            3:  {"group": 3,  "cells": [{"index": 1, "label": "Engine Speed", "value": 2400, "unit": "RPM"},
                                        {"index": 2, "label": "Intake Air Mass", "value": 31.5, "unit": "g/s"},
                                        {"index": 3, "label": "Throttle Sensor 1", "value": 18.0, "unit": "%"},
                                        {"index": 4, "label": "Ignition Timing Angle", "value": 21.0, "unit": "°"}]},
            4:  {"group": 4,  "cells": [{"index": 2, "label": "Voltage Supply", "value": 13.9, "unit": "V"},
                                        {"index": 3, "label": "Coolant Temperature", "value": 88.0, "unit": "°C"},
                                        {"index": 4, "label": "Intake Air Temperature", "value": 31.0, "unit": "°C"}]},
            94: {"group": 94, "cells": [{"index": 2, "label": "Engine Load", "value": 55.1, "unit": "%"},
                                        {"index": 3, "label": "Ignition Timing Actual", "value": 18.5, "unit": "°"},
                                        {"index": 4, "label": "Knock Retard Total", "value": 2.25, "unit": "°"}]},
        }}
        lv = LiveValues(state)
        assert (lv.rpm, lv.maf, lv.battery, lv.coolant, lv.iat) == (2400, 31.5, 13.9, 88.0, 31.0)
        assert lv.timing == 18.5              # "Actual" preferred over the group-3 angle
        assert lv.knock_retard == 2.25 and lv.load == 55.1
        assert "KR 2.2°" in live_summary(lv) or "KR 2.3°" in live_summary(lv)

    def test_old_group0_layout_yields_nothing(self):
        """The previous reader assumed a 'group 0' with cells 1..15; ME7 has none."""
        state = {"connected": True, "groups": {"0": {"group": 0, "cells": [
            {"index": 1, "label": "", "value": 3000.0, "unit": ""}]}}}
        lv = LiveValues(state)
        assert not lv.valid                   # an unlabelled cell is not RPM

    def test_lambda_proper_when_reported(self):
        state = {"connected": True, "groups": {"1": {"group": 1, "cells": [
            {"index": 1, "label": "Engine Speed", "value": 900, "unit": "RPM"},
            {"index": 2, "label": "Lambda (actual)", "value": 0.98, "unit": ""}]}}}
        lv = LiveValues(state)
        assert lv.lambda_ == 0.98 and lv.lambda_colour() == "#2dff6e"

    def test_disconnected_or_garbage_state(self):
        assert not LiveValues({}).valid
        assert not LiveValues({"connected": False, "groups": README_STATE["groups"]}).valid
        lv = LiveValues({"connected": True, "groups": {"x": "junk", "1": {"cells": [{"index": "a", "value": "nope"}]}}})
        assert not lv.valid


# ── G1 / G2: monitor behaviour with a fake client ────────────────────────────

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtCore = pytest.importorskip("PyQt5.QtCore")
from PyQt5.QtWidgets import QApplication   # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeClient:
    instances = []

    def __init__(self, port=0):
        self.port = port
        self._connected = False
        self._state = None
        self.disconnect_calls = 0
        self.groups_requested = None
        self._handlers = {"state": [], "connect": [], "disconnect": []}
        FakeClient.instances.append(self)

    def on_state(self, fn): self._handlers["state"].append(fn); return self
    def on_connect(self, fn): self._handlers["connect"].append(fn); return self
    def on_disconnect(self, fn): self._handlers["disconnect"].append(fn); return self

    def connect(self, auto_reconnect=True):
        self._connected = True
        self._state = README_STATE
        for fn in self._handlers["connect"]:
            fn()

    def disconnect(self):
        self.disconnect_calls += 1
        self._connected = False

    def drop(self):
        self._connected = False
        for fn in self._handlers["disconnect"]:
            fn()

    def set_groups(self, groups): self.groups_requested = list(groups)

    @property
    def connected(self): return self._connected
    @property
    def state(self): return self._state


@pytest.fixture
def fake_bridge(monkeypatch):
    FakeClient.instances.clear()
    monkeypatch.setattr(kwp, "_KWP_AVAILABLE", True)
    monkeypatch.setattr(kwp, "KWPClient", FakeClient)
    probe = {"running": True, "threads": set(), "sleep": 0.0}

    def is_running(port=0, timeout=0.2):
        probe["threads"].add(threading.current_thread().name)
        if probe["sleep"]:
            time.sleep(probe["sleep"])
        return probe["running"]
    monkeypatch.setattr(kwp, "_kwp_is_running", is_running)
    return probe


class TestMonitor:
    def _wait(self, cond, timeout=2.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            QApplication.processEvents()
            if cond():
                return True
            time.sleep(0.02)
        return cond()

    def test_probe_runs_off_the_ui_thread_and_poll_never_blocks(self, qapp, fake_bridge):
        fake_bridge["sleep"] = 0.3                 # a slow probe …
        m = kwp.KWPMonitor(probe_interval=0.05)
        try:
            assert self._wait(lambda: m.bridge_running)
            assert fake_bridge["threads"] == {"kwpbridge-probe"}
            t0 = time.monotonic()
            m._poll()                              # … must not be felt here
            assert time.monotonic() - t0 < 0.1
        finally:
            m.stop()

    def test_bridge_down_is_reflected(self, qapp, fake_bridge):
        m = kwp.KWPMonitor(probe_interval=0.05)
        try:
            assert self._wait(lambda: m.bridge_running)
            fake_bridge["running"] = False
            assert self._wait(lambda: not m.bridge_running)
        finally:
            m.stop()

    def test_single_client_across_reconnects(self, qapp, fake_bridge):
        m = kwp.KWPMonitor(probe_interval=0.05)
        try:
            assert self._wait(lambda: m.bridge_running)
            m._poll()
            assert len(FakeClient.instances) == 1 and m._client is FakeClient.instances[0]
            assert m.current_pn() == "06A906032BN"
            # drop the link: the next poll releases the old client
            FakeClient.instances[0].drop()
            m._poll()
            assert m._client is None
            assert FakeClient.instances[0].disconnect_calls == 1
            # reconnect is rate-limited, then makes exactly one new client
            m._last_connect_attempt = 0.0
            m._poll()
            assert len(FakeClient.instances) == 2 and m._client is FakeClient.instances[1]
            assert sum(1 for c in FakeClient.instances if c.connected) == 1
        finally:
            m.stop()
        assert all(c.disconnect_calls >= 1 for c in FakeClient.instances)

    def test_reconnect_backoff(self, qapp, fake_bridge):
        m = kwp.KWPMonitor(probe_interval=0.05)
        try:
            assert self._wait(lambda: m.bridge_running)
            m._poll()
            FakeClient.instances[0].drop()
            m._poll(); m._poll(); m._poll()
            assert len(FakeClient.instances) == 1   # within the back-off window
        finally:
            m.stop()

    def test_part_number_match_and_mismatch(self, qapp, fake_bridge):
        m = kwp.KWPMonitor(probe_interval=0.05)
        got = {}
        m.mismatch.connect(lambda e, r: got.setdefault("mismatch", (e, r)))
        try:
            assert self._wait(lambda: m.bridge_running)
            m._poll()
            m.set_rom_part_numbers(["06A906032BN"])
            assert m.is_matched()
            m.set_rom_part_numbers(["8D0907551M"])
            assert not m.is_matched()
            assert self._wait(lambda: "mismatch" in got)
            assert got["mismatch"] == ("06A906032BN", "8D0907551M")
            assert status_label(m, "8D0907551M")[0].startswith("🟡")
        finally:
            m.stop()

    def test_request_groups_is_explicit(self, qapp, fake_bridge):
        m = kwp.KWPMonitor(probe_interval=0.05)
        try:
            assert self._wait(lambda: m.bridge_running)
            m._poll()
            assert FakeClient.instances[0].groups_requested is None   # never automatic
            assert m.request_groups()
            assert FakeClient.instances[0].groups_requested == kwp.PREFERRED_GROUPS
        finally:
            m.stop()

    def test_stop_joins_probe_thread(self, qapp, fake_bridge):
        m = kwp.KWPMonitor(probe_interval=0.05)
        assert self._wait(lambda: m.bridge_running)
        t = m._probe_thread
        m.stop()
        assert not t.is_alive()

    def test_inert_without_kwpbridge(self, qapp, monkeypatch):
        monkeypatch.setattr(kwp, "_KWP_AVAILABLE", False)
        m = kwp.KWPMonitor()
        assert not m.bridge_running and m._probe_thread is None
        m._poll()
        assert m._client is None
        m.stop()


# ── Integration: real client against KWPBridge's ME7 mock server ─────────────

@pytest.mark.skipif(not kwp.kwpbridge_available(), reason="kwpbridge not installed")
def test_live_values_from_me7_mock_server(qapp):
    from kwpbridge.mock.server import MockServer
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = MockServer(ecu="me7", port=port, poll_hz=10.0)
    srv.start()
    m = kwp.KWPMonitor(port=port, probe_interval=0.1)
    got = []
    m.live_data.connect(got.append)
    try:
        t0 = time.monotonic()
        while time.monotonic() - t0 < 8.0 and len(got) < 3:
            QApplication.processEvents()
            m._poll()
            time.sleep(0.05)
        assert got, "no live data from the mock server"
        lv = got[-1]
        assert lv.ecu_pn == "06A906032BN"
        assert lv.rpm is not None and 500 <= lv.rpm <= 7500
        assert lv.coolant is not None and -40 <= lv.coolant <= 130
        assert lv.lambda_ is None or 0.5 <= lv.lambda_ <= 1.5
        m.set_rom_part_numbers(["06A906032BN"])
        assert m.is_matched()
        assert "RPM" in live_summary(lv)
    finally:
        m.stop()
        srv.stop()
