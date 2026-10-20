"""Executable shadow-policy specification; no world/entity access or actuation."""
from dataclasses import dataclass

from model.memory import TargetMemory


@dataclass(frozen=True)
class Sample:
    target_id: int
    visible: bool
    at_ms: int


@dataclass(frozen=True)
class Intent:
    state: str
    kind: str
    target_id: int | None = None
    position: tuple | None = None
    reaction_remaining_ms: int = 0
    search_remaining_ms: int = 0


def bounded_ms(value, maximum: int, fallback: int) -> int:
    return value if type(value) is int and 1 <= value <= maximum else fallback


class ShadowDecision:
    def __init__(self, reaction_ms=250, search_ms=3000, stale_ms=2000):
        self.reaction_ms = bounded_ms(reaction_ms, 2000, 250)
        self.search_ms = bounded_ms(search_ms, 10000, 3000)
        self.stale_ms = bounded_ms(stale_ms, 5000, 2000)
        self.reset()

    def _clear_focus(self):
        self.state = "idle"
        self.target_id = None
        self.reaction_started_at = -1
        self.last_positive_at = -1
        self.search_deadline = -1

    def reset(self):
        self._clear_focus()
        self.last_tick = -1

    def _acquire(self, target_id: int, now_ms: int):
        self.state = "reacting"
        self.target_id = target_id
        self.reaction_started_at = self.last_positive_at = now_ms
        self.search_deadline = -1

    def _snapshot(self, memory: TargetMemory, now_ms: int) -> Intent:
        if self.state == "reacting":
            return Intent(self.state, "wait", self.target_id, reaction_remaining_ms=max(0, self.reaction_started_at + self.reaction_ms - now_ms))
        if self.state in ("tracking", "searching"):
            contact = memory.recall(self.target_id, now_ms)
            if contact is not None:
                return Intent(self.state, "observe" if self.state == "tracking" else "search", self.target_id, contact.position, search_remaining_ms=self.search_deadline - now_ms if self.state == "searching" else 0)
        return Intent(self.state, "none", self.target_id)

    def update(self, memory: TargetMemory, samples: list[Sample], now_ms: int) -> Intent:
        if type(now_ms) is not int or now_ms < 0 or now_ms < self.last_tick:
            memory.clear()
            self.reset()
            return self._snapshot(memory, 0)
        memory.advance(now_ms)
        self.last_tick = now_ms
        contact = memory.recall(self.target_id, now_ms) if self.target_id is not None else None
        if self.target_id is not None and (contact is None or now_ms - self.last_positive_at >= memory.ttl_ms):
            self._clear_focus()
        focused_sample = None
        best_visible = None
        for sample in samples:
            if type(sample.target_id) is not int or not 0 <= sample.target_id <= 2047 or type(sample.visible) is not bool or sample.at_ms != now_ms:
                continue
            if sample.visible:
                observed = memory.recall(sample.target_id, now_ms)
                if observed is None or observed.seen_at != now_ms:
                    continue
                if best_visible is None or sample.target_id < best_visible:
                    best_visible = sample.target_id
            if sample.target_id == self.target_id:
                focused_sample = sample.visible
        stale = now_ms - self.last_positive_at >= self.stale_ms
        if focused_sample is True:
            self.last_positive_at = now_ms
        if self.state == "reacting":
            if focused_sample is False or stale:
                self._clear_focus()
            elif focused_sample is True and now_ms - self.reaction_started_at >= self.reaction_ms:
                self.state = "tracking"
        elif self.state == "tracking" and (focused_sample is False or stale):
            self.state = "searching"
            self.search_deadline = min(now_ms + self.search_ms, contact.seen_at + memory.ttl_ms)
        if self.state == "searching" and now_ms >= self.search_deadline:
            self._clear_focus()
        if best_visible is not None and self.state in ("idle", "searching"):
            self._acquire(best_visible, now_ms)
        return self._snapshot(memory, now_ms)
