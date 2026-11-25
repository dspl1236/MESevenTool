"""
meseventool/presets.py
======================
Named bundles of catalogue patches applied as one step.

A preset is a list of *members*; each member is one job ("disable the
catalyst monitor") that may be satisfied by any of several catalogue
entries, because the same job has a different entry per ECU family or
firmware build (CDNWS has three, IMMO-OFF has four).  Applying a preset
means: for every member, take the first alternative whose ``detect()``
reports STOCK and apply it.  Everything else is reported, never guessed:

    APPLY           first alternative is STOCK on this ROM — will be written
    ALREADY         an alternative is already PATCHED
    NOT_APPLICABLE  no alternative applies to this ECU/build
    MISSING         an alternative applies but its needle/site was not found
    SKIP_MODIFIED   the site holds neither stock nor patched bytes — left alone

``plan()`` is the dry run the GUI shows before writing; ``apply()`` runs
the plan and ends with a fresh plan so the caller sees the result.

The first preset is the standalone-swap bundle scoped in
``docs/swap_preset_scope.md`` (catalogue-only stage).  Its immobiliser
member is PROVISIONAL in the catalogue; the preset says so, loudly, and
the GUI shows every member's confidence before the user confirms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence

from .rom import ROMImage
from .needle import Searcher
from .patches import ALL_PATCHES, PatchDef, PatchResult, PatchState


class PlanAction(Enum):
    APPLY          = "apply"
    ALREADY        = "already patched"
    NOT_APPLICABLE = "not applicable"
    MISSING        = "not found"
    SKIP_MODIFIED  = "skipped (modified)"
    REVERT         = "revert"


@dataclass(frozen=True)
class PresetMember:
    """One job; ``patches`` are the catalogue names that can do it, in
    preference order.  ``required`` members make the preset incomplete when
    none of them can be applied or is already applied."""
    job:      str
    patches:  Sequence[str]
    required: bool = False
    note:     str  = ""


@dataclass
class MemberPlan:
    member:  PresetMember
    action:  PlanAction
    patch:   Optional[PatchDef]    = None    # the alternative chosen
    result:  Optional[PatchResult] = None
    detail:  str = ""

    @property
    def confidence(self) -> str:
        return self.patch.confidence if self.patch else ""


@dataclass
class PresetPlan:
    preset:  "Preset"
    members: List[MemberPlan] = field(default_factory=list)

    def by_action(self, action: PlanAction) -> List[MemberPlan]:
        return [m for m in self.members if m.action == action]

    @property
    def will_write(self) -> bool:
        return any(m.action in (PlanAction.APPLY, PlanAction.REVERT) for m in self.members)

    @property
    def complete(self) -> bool:
        """Every required member is applied or will be."""
        return all(m.action in (PlanAction.APPLY, PlanAction.ALREADY)
                   for m in self.members if m.member.required)

    @property
    def unproven(self) -> List[MemberPlan]:
        """Members whose chosen entry is not CONFIRMED."""
        return [m for m in self.members
                if m.patch is not None and m.confidence != "CONFIRMED"
                and m.action in (PlanAction.APPLY, PlanAction.ALREADY)]

    def summary(self) -> str:
        lines = [f"{self.preset.name}: {len(self.by_action(PlanAction.APPLY))} to apply, "
                 f"{len(self.by_action(PlanAction.ALREADY))} already, "
                 f"{len(self.by_action(PlanAction.NOT_APPLICABLE))} not applicable, "
                 f"{len(self.by_action(PlanAction.MISSING))} not found, "
                 f"{len(self.by_action(PlanAction.SKIP_MODIFIED))} skipped"]
        for m in self.members:
            name = m.patch.name if m.patch else "—"
            conf = f" [{m.confidence}]" if m.patch and m.confidence != "CONFIRMED" else ""
            lines.append(f"  {m.action.value:18s} {m.member.job}: {name}{conf}")
        return "\n".join(lines)


@dataclass
class PresetReport:
    applied:  List[str] = field(default_factory=list)
    reverted: List[str] = field(default_factory=list)
    failed:   List[str] = field(default_factory=list)
    plan_after: Optional[PresetPlan] = None

    @property
    def ok(self) -> bool:
        return not self.failed


def _lookup(name: str) -> PatchDef:
    for p in ALL_PATCHES:
        if p.name == name:
            return p
    raise KeyError(f"preset refers to unknown patch {name!r}")


@dataclass(frozen=True)
class Preset:
    name:        str
    description: str
    members:     Sequence[PresetMember]
    caveats:     Sequence[str] = ()

    def validate(self) -> None:
        for m in self.members:
            for n in m.patches:
                _lookup(n)

    # ── Dry run ──────────────────────────────────────────────────────────────

    def plan(self, rom: ROMImage, searcher: Optional[Searcher] = None,
             profile=None) -> PresetPlan:
        s = searcher or Searcher(rom)
        plan = PresetPlan(self)
        for member in self.members:
            chosen: Optional[MemberPlan] = None
            fallback: Optional[MemberPlan] = None
            for name in member.patches:
                patch = _lookup(name)
                r = patch.detect(rom, s, profile)
                if r.state == PatchState.PATCHED:
                    chosen = MemberPlan(member, PlanAction.ALREADY, patch, r, r.detail)
                    break
                if r.state == PatchState.STOCK:
                    chosen = MemberPlan(member, PlanAction.APPLY, patch, r, r.detail)
                    break
                # remember the most informative non-match: a site that was
                # found but modified beats a missing needle beats N/A
                rank = {PatchState.UNKNOWN: 3, PatchState.MISSING: 2,
                        PatchState.NOT_APPLICABLE: 1}.get(r.state, 0)
                if fallback is None or rank > fallback.result_rank:
                    action = {PatchState.UNKNOWN: PlanAction.SKIP_MODIFIED,
                              PatchState.MISSING: PlanAction.MISSING}.get(
                                  r.state, PlanAction.NOT_APPLICABLE)
                    fb = MemberPlan(member, action, patch, r, r.detail)
                    fb.result_rank = rank          # type: ignore[attr-defined]
                    fallback = fb
            plan.members.append(chosen or fallback
                                or MemberPlan(member, PlanAction.NOT_APPLICABLE, None, None,
                                              "no catalogue entry for this ROM"))
        return plan

    # ── Apply / revert ───────────────────────────────────────────────────────

    def apply(self, rom: ROMImage, searcher: Optional[Searcher] = None,
              profile=None) -> PresetReport:
        s = searcher or Searcher(rom)
        report = PresetReport()
        for mp in self.plan(rom, s, profile).members:
            if mp.action is not PlanAction.APPLY or mp.patch is None or mp.result is None:
                continue
            try:
                ok = mp.patch.apply(rom, mp.result)
            except Exception as e:                       # noqa: BLE001
                ok = False
                mp.detail = str(e)
            (report.applied if ok else report.failed).append(mp.patch.name)
        report.plan_after = self.plan(rom, Searcher(rom), profile)
        return report

    def revert(self, rom: ROMImage, searcher: Optional[Searcher] = None,
               profile=None) -> PresetReport:
        """Undo every member that is currently PATCHED (reverse order)."""
        s = searcher or Searcher(rom)
        report = PresetReport()
        for mp in reversed(self.plan(rom, s, profile).members):
            if mp.action is not PlanAction.ALREADY or mp.patch is None or mp.result is None:
                continue
            try:
                ok = mp.patch.revert(rom, mp.result)
            except Exception as e:                       # noqa: BLE001
                ok = False
                mp.detail = str(e)
            (report.reverted if ok else report.failed).append(mp.patch.name)
        report.plan_after = self.plan(rom, Searcher(rom), profile)
        return report


# ── Member groups shared by the swap presets ─────────────────────────────────

_IMMO = PresetMember(
    "Immobiliser off",
    ["IMMO-OFF — ME7.5 1.8T 06A/06B/4B0 (fw4013/4016/4017/4019)",
     "IMMO-OFF — ME7.5 1.8T 06A VDO fw4013 variant",
     "IMMO-OFF — ME7.1 2.7T S4/A6 biturbo (fw6001/6005)",
     "IMMO-OFF — ME7.1.1 (4Z7 Allroad / 4D1 RS4 / 022 VR6 R32)"],
    required=True,
    note="PROVISIONAL in the catalogue: the needle is confirmed but no bench "
         "start has been done. Verify on a bench ECU before relying on it.")

_IMMO_CEL = PresetMember(
    "Immobiliser databus CEL off",
    ["P1681 Immobiliser Databus CEL Disable (ME7.1.1)"],
    note="ME7.1.1 only; on ME7.5 the equivalent is a fault-path codeword not yet in the catalogue.")

_CAT = PresetMember(
    "Catalyst monitor off",
    ["Catalyst Monitor Disable — CDKAT (ME7, per-build address)"],
    required=True)

_REAR_O2_HEATER = PresetMember(
    "Rear O2 heater diagnosis off",
    ["Rear O2 Heater Diagnosis Disable — CDLSH (ME7, per-build address)",
     "Rear O2 Sensor Diagnosis Disable (2.7T ME7.1/ME7.1.1)"],
    required=True)
_REAR_O2_INTERCHANGE = PresetMember(
    "Rear O2 interchange diagnosis off",
    ["Rear O2 Interchange Diagnosis Disable — CDLSHV (ME7, per-build address)"],
    note="The 06a layout has no CDLSHV; not applicable there is expected.")
_REAR_O2_VOLTAGE = PresetMember(
    "Rear O2 voltage diagnosis off",
    ["Rear O2 Voltage Diagnosis Disable — CDLSV (ME7, per-build address)",
     "Rear O2 After-Cat Voltage Diagnosis Disable CDHSVE (4B0906018 A6/Passat)"],
    required=True)
_REAR_O2_ESKONF = PresetMember(
    "Rear O2 heater configuration (ESKONF)",
    ["ESKONF Rear O2 Heater Disable (newer — 0F 01 05)",
     "ESKONF Rear O2 Heater Disable (older-06 — 06 02 A8)",
     "ESKONF Rear O2 Heater Disable (older-05 — 05 02 A8)"],
    note="2.7T only.")
_REAR_O2_THRESHOLD = PresetMember(
    "Rear O2 monitor threshold",
    ["Rear O2 Monitor Threshold",
     "Rear O2 Monitor Threshold (ME7.5 06A LP fw4013)"])

_SAP = PresetMember(
    "Secondary air pump diagnosis off",
    ["SAP Diagnosis Disable (ME7.5 1.8T)",
     "SAP Diagnosis Disable CDSLS (4B0906018 A6/Passat 1.8T)",
     "SAP MSLUB Airflow Table Zero (2.7T)"],
    required=True,
    note="The 2.7T MSLUB entry cannot be re-detected or reverted once applied: "
         "its anchor is the stock table itself (review A8).")

_EVAP = PresetMember(
    "EVAP purge diagnosis off",
    ["EVAP Purge Diagnosis Disable (ME7.5 1.8T)",
     "EVAP Diagnosis Disable (4B0906018 A6/Passat 1.8T)"],
    required=True)

_VVT = PresetMember(
    "VVT cam position monitor off",
    ["VVT Cam Position Monitor Disable — CDNWS (ME7.5 1.8T AWW/AWP/AUQ/AUM)",
     "VVT Cam Position Monitor Disable — CDNWS (4B0906018CM Passat/A6 AWM)",
     "VVT Cam Position Monitor Disable — CDNWS (ME7.1/ME7.1.1)"])

_GEAR_TORQUE = PresetMember(
    "Gearbox torque-mode table neutralised",
    ["5th-Gear Torque Mode Disable (ME7.5 1.8T universal)"],
    note="For a non-stock gearbox; ME7.5 1.8T only.")

_MAF_DELETE = PresetMember(
    "MAF delete (alpha-N load)",
    ["MAF Delete / Alpha-N load redirect (ME7.5 06A)",
     "MAF Delete / Alpha-N load redirect (ME7.5 RN/LP fw4013)",
     "MAF Delete / Alpha-N load redirect (ME7.5 LP/18CM fw4013/4012)",
     "MAF Delete / Alpha-N load redirect (ME7.5 SL DSG X505R)",
     "MAF Delete / Alpha-N load redirect (ME7.5 fw4013 alt FA1E/1F)"],
    required=True,
    note="Only on the ME7.5 1.8T builds these needles were confirmed on.")
_MAF_DIAG = PresetMember(
    "MAF sensor diagnosis off",
    ["MAF Sensor Diagnosis Disable — CDEHFM (ME7.5 SL/4B variants)"],
    note="Builds that ship CDEHFM=0 report not applicable: nothing to do.")

_SWAP_CAVEATS = (
    "Immobiliser-off entries are PROVISIONAL: confirmed needles, no bench start yet. "
    "Prove on a bench ECU with a K-line cable before fitting to a car.",
    "The 'Rear O2 OBD Readiness Flags' patch is deliberately not included "
    "(review B7: its offsets are DL-specific).",
    "Missing-sensor fault paths (vehicle speed, brake/clutch switches, cluster/ABS "
    "CAN timeouts) are not in the catalogue yet — see docs/swap_preset_scope.md §2.",
    "Fix checksums before saving; the Save dialog will refuse otherwise.",
)

SWAP_KEEP_MAF = Preset(
    name="Standalone swap (keep MAF)",
    description="Engine swap / race car on stock firmware with the MAF retained: "
                "immobiliser off, catalyst / rear-O2 / SAP / EVAP / VVT monitoring "
                "off, gearbox torque-mode table neutralised.",
    members=[_IMMO, _IMMO_CEL, _CAT, _REAR_O2_HEATER, _REAR_O2_INTERCHANGE,
             _REAR_O2_VOLTAGE, _REAR_O2_ESKONF, _REAR_O2_THRESHOLD, _SAP, _EVAP,
             _VVT, _GEAR_TORQUE],
    caveats=_SWAP_CAVEATS,
)

SWAP_ALPHA_N = Preset(
    name="Standalone swap (alpha-N, no MAF)",
    description=SWAP_KEEP_MAF.description + " Adds the MAF delete and MAF "
                "diagnosis off for a car running without the air mass meter.",
    members=list(SWAP_KEEP_MAF.members) + [_MAF_DELETE, _MAF_DIAG],
    caveats=_SWAP_CAVEATS + ("Alpha-N needs a boost-referenced load map; the "
                             "delete alone does not retune fuelling.",),
)

ALL_PRESETS: List[Preset] = [SWAP_KEEP_MAF, SWAP_ALPHA_N]

for _p in ALL_PRESETS:
    _p.validate()
