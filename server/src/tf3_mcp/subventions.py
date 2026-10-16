"""Rule-based auto-accept for native subventions (补贴任务).

Polling lives in this MCP process, never in the mod: the game's engine update() runs in several
unshared Lua states, so in-game automation could accept the same offer more than once. Every uid is
attempted at most once; a failed or unverified accept is never resent.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from pathlib import Path

DEFAULT_KINDS = ("deliver_cargo", "deliver_cargo_town")


def make_policy(kinds=None, min_margin=1.5, max_failure_money=15_000_000, min_remaining_days=0, max_active=5):
    kinds = list(kinds) if kinds else list(DEFAULT_KINDS)
    if min_margin <= 0:
        raise ValueError("min_margin must be positive")
    if max_failure_money < 0 or min_remaining_days < 0:
        raise ValueError("limits must not be negative")
    if not 1 <= max_active <= 5:
        raise ValueError("max_active must be 1..5 (native limit is 5)")
    return dict(kinds=kinds, min_margin=float(min_margin), max_failure_money=int(max_failure_money),
                min_remaining_days=int(min_remaining_days), max_active=int(max_active))


def evaluate(task: dict, policy: dict, active_count: int) -> tuple[bool, list[str]]:
    """Decide one proposed task. Returns (accept, reasons); any failed rule rejects."""
    reasons: list[str] = []
    ok = True

    def reject(msg):
        nonlocal ok
        ok = False
        reasons.append(msg)

    if task.get("status") != "Proposed":
        reject(f"status is {task.get('status')}, not Proposed")
    if task.get("kind") not in policy["kinds"]:
        reject(f"kind {task.get('kind')} is not enabled")
    failure = task.get("failureMoney") or 0
    if failure > policy["max_failure_money"]:
        reject(f"failure penalty {failure} exceeds {policy['max_failure_money']}")
    days = task.get("remainingDays")
    if days is not None and days < policy["min_remaining_days"]:
        reject(f"offer closes in {days} days")
    if active_count >= policy["max_active"]:
        reject(f"{active_count} active subventions already (limit {policy['max_active']})")
    a = task.get("assessment") or {}
    if not a.get("supported"):
        reject(f"cannot assess: {a.get('reason', 'no assessment')}")
    elif not a.get("served"):
        reject("no player line loads this cargo at a producing industry and unloads it at the target")
    else:
        if not any(line.get("vehicles") for line in a.get("lines", [])):
            reject("serving lines have no vehicles")
        margin = a.get("margin")
        if margin is None:
            reject("required delivery rate is unknown")
        elif margin < policy["min_margin"]:
            reject(f"estimated {a.get('estimatedPerYear', 0):.1f}/yr is {margin:.2f}x the required "
                   f"{task.get('requiredPerYear', 0):.1f}/yr (need {policy['min_margin']}x)")
        else:
            reasons.append(f"estimated {a.get('estimatedPerYear', 0):.1f}/yr = {margin:.2f}x required "
                           f"{task.get('requiredPerYear', 0):.1f}/yr")
    if ok:
        reasons.append(f"failure penalty {failure} within limit")
    return ok, reasons


def expectation(task: dict) -> dict:
    """Terms the bridge re-checks immediately before sending the native accept event."""
    out = {"kind": task.get("kind"), "toDeliver": task.get("toDeliver"),
           "upfrontMoney": task.get("upfrontMoney"), "failureMoney": task.get("failureMoney")}
    if task.get("target"):
        out["target"] = task["target"].get("entity")
    return {k: v for k, v in out.items() if v is not None}


class SubventionAutoAccept:
    def __init__(self, call, log_path=None, interval=30):
        self.call, self.log_path, self.interval = call, log_path, interval
        self.policy = make_policy()
        self.dry_run = True
        self.task = None
        self.attempted: dict[int, dict] = {}  # uid -> accept attempt; never retried
        self.last_decision: dict[int, str] = {}
        self.log: list[dict] = []
        self.error = None
        self.last_run = None
        self.run_lock = asyncio.Lock()

    def _load_attempts(self):
        path = self.log_path() if callable(self.log_path) else self.log_path
        if not path or not Path(path).exists():
            return
        saved = json.loads(Path(path).read_text(encoding='utf-8'))
        for uid, row in saved.get('attempted', {}).items():
            self.attempted[int(uid)] = row
        # Migrate older journals conservatively: dispatched/unknown entries block
        # further acceptance until independently reconciled, never disappear.
        for row in saved.get('log', []):
            if row.get('uid') is not None and row.get('result') not in (None, 'dry_run'):
                self.attempted.setdefault(int(row['uid']), dict(row))

    def _record(self, entry):
        entry["time"] = time.time()
        self.log.append(copy.deepcopy(entry))
        del self.log[:-200]
        path = self.log_path() if callable(self.log_path) else self.log_path
        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"policy": self.policy, "dryRun": self.dry_run, "log": self.log,
                                      "attempted": self.attempted},
                                      ensure_ascii=False, indent=1), encoding="utf8")
            os.replace(tmp, path)

    async def run_once(self) -> dict:
        async with self.run_lock:
            path = self.log_path() if callable(self.log_path) else self.log_path
            if path:
                from .no_gui import public_lock
                with public_lock(Path(path).parent / 'subvention_policy_lock'):
                    self._load_attempts()
                    return await self._run_once()
            return await self._run_once()

    async def _run_once(self) -> dict:
        state = await self.call("get_subventions", assess=True)
        active = state.get("activeCount", 0)
        summary = {"gameTime": state.get("gameTime"), "activeCount": active, "decisions": [],
                   "accepted": [], "submitted": [], "pending": [], "failed": []}
        native = {t["uid"]: t for t in state.get("tasks", [])}
        for uid, attempt in self.attempted.items():
            if attempt.get('transportSession') and attempt['transportSession'] != state.get('transportSession'):
                raise ValueError('Autoaccept session changed; reconcile stored intents before restarting')
            if attempt.get("confirmed"):
                continue
            status = native.get(uid, {}).get("status")
            if status in {"Active", "Complete", "Failed"}:
                attempt.update(confirmed=True, nativeStatus=status)
                summary["accepted"].append(uid)
                self._record(dict(attempt, result="native_confirmed"))
            else:
                summary["pending"].append(uid)
        # Proposed/missing records cannot prove rejection after an asynchronous send.
        # Even a dispatch error may have happened after enqueueing; never release its slot blindly.
        if summary["pending"]:
            summary["blocked"] = "previous_accept_requires_reconciliation"
            self.last_run = time.time()
            return summary
        for task in state.get("tasks", []):
            uid = task.get("uid")
            if task.get("status") != "Proposed" or uid in self.attempted:
                continue
            accept, reasons = evaluate(task, self.policy, active)
            decision = "accept" if accept else "reject"
            row = {"uid": uid, "name": task.get("name"), "kind": task.get("kind"),
                   "target": (task.get("target") or {}).get("name"), "decision": decision, "reasons": reasons}
            summary["decisions"].append(row)
            changed = self.last_decision.get(uid) != decision
            self.last_decision[uid] = decision
            if not accept:
                if changed:
                    self._record(dict(row, gameTime=state.get("gameTime")))
                continue
            if self.dry_run:
                if changed:
                    self._record(dict(row, gameTime=state.get("gameTime"), result="dry_run"))
                continue
            attempt = dict(row, gameTime=state.get("gameTime"), transportSession=state.get('transportSession'),
                           terms=expectation(task), result='intent')
            self.attempted[uid] = attempt
            self._record(attempt)  # Persist before any acceptance dispatch.
            try:
                result = await self.call("accept_subvention", uid=uid, expect=expectation(task))
                attempt["result"] = {k: result.get(k) for k in ("submitted", "callbackAccepted", "dispatchError")}
                summary["pending"].append(uid)
                if result.get("submitted") is True and not result.get("dispatchError") and result.get("callbackAccepted") is not False:
                    summary["submitted"].append(uid)
                else:
                    summary["failed"].append(uid)
            except Exception as exc:  # never resend; the uid stays in attempted
                attempt["result"] = {"error": str(exc)}
                summary["failed"].append(uid)
                summary["pending"].append(uid)
            self._record(attempt)
            break  # one accept per pass; the next pass reads fresh native state
        self.last_run = time.time()
        return summary

    async def start(self, policy: dict, interval: float, dry_run: bool) -> dict:
        await self.stop()
        if interval < 5:
            raise ValueError("interval must be at least 5 seconds")
        self.policy, self.interval, self.dry_run, self.error = policy, interval, dry_run, None
        first = await self.run_once()

        async def poll():
            while True:
                await asyncio.sleep(self.interval)
                try:
                    await self.run_once()
                    self.error = None
                except Exception as exc:
                    self.error = str(exc)
                    break  # no repeated game requests after a transport/native error
        self.task = asyncio.create_task(poll())
        return dict(self.status(), firstPass=first)

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    def status(self) -> dict:
        return dict(running=bool(self.task and not self.task.done()), dryRun=self.dry_run,
                    intervalSeconds=self.interval, policy=self.policy, error=self.error,
                    lastRunAgeSeconds=round(time.time() - self.last_run, 1) if self.last_run else None,
                    attempted=list(self.attempted.values())[-20:], recentLog=self.log[-20:],
                    pending=[uid for uid, attempt in self.attempted.items() if not attempt.get("confirmed")],
                    scope="runs only while this MCP server process is alive")
