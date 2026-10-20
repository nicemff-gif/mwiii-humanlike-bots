"""Reference contract for bounded last-seen memory, without engine entities."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Contact:
    target_id: int
    position: tuple[float, float, float]
    seen_at: int
    age_ms: int
    confidence: float


def supports_tdm(mode: str | None, teambased: bool | None, player_count: int) -> bool:
    return mode == "war" and teambased is True and 0 < player_count <= 12


class TargetMemory:
    def __init__(self, ttl_ms: int = 4000, capacity: int = 16):
        self.ttl_ms = ttl_ms if isinstance(ttl_ms, (int, float)) and 1 <= ttl_ms <= 15000 else 4000
        self.capacity = int(capacity) if isinstance(capacity, (int, float)) and 1 <= capacity <= 32 else 16
        self.clear()

    def clear(self) -> None:
        self._entries: list[tuple[int, tuple[float, float, float], int] | None] = [None] * self.capacity
        self._last_tick = -1

    def advance(self, now_ms: int) -> bool:
        if type(now_ms) is not int or now_ms < 0:
            self.clear()
            return False
        if now_ms < self._last_tick:
            self.clear()
        self._last_tick = now_ms
        for index, entry in enumerate(self._entries):
            if entry is not None and now_ms >= entry[2] + self.ttl_ms:
                self._entries[index] = None
        return True

    def record_visible(self, target_id: int, position, now_ms: int) -> bool:
        if not self.advance(now_ms):
            return False
        if type(target_id) is not int or not 0 <= target_id <= 2047:
            return False
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            return False
        if any(not isinstance(n, (int, float)) or not math.isfinite(n) for n in position):
            return False
        selected = next((i for i, e in enumerate(self._entries) if e is not None and e[0] == target_id), None)
        if selected is None:
            selected = next((i for i, e in enumerate(self._entries) if e is None), None)
        if selected is None:
            selected = min(range(self.capacity), key=lambda i: self._entries[i][2])
        self._entries[selected] = (target_id, tuple(position), now_ms)
        return True

    def recall(self, target_id: int, now_ms: int) -> Contact | None:
        if not self.advance(now_ms):
            return None
        for entry in self._entries:
            if entry is not None and entry[0] == target_id:
                age = now_ms - entry[2]
                return Contact(target_id, entry[1], entry[2], age, 1 - age / self.ttl_ms)
        return None
