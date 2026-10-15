"""Single shared store of the entities the panel uses: diffing, generation, online/stale tracking."""
import time


class StateStore:
    def __init__(self):
        self.states = {}
        self.generation = 0
        self.online = None          # None = unknown (no attempt finished), True/False afterwards
        self.last_success = None    # time.monotonic() of the last good fetch

    def update(self, entities, now=None):
        """Replace the stored set; returns the set of entity ids whose state/attributes changed."""
        new = {s['entity_id']: s for s in entities if isinstance(s, dict) and 'entity_id' in s}
        changed = {e for e, s in new.items() if self._sig(s) != self._sig(self.states.get(e))}
        changed |= set(self.states) - set(new)
        self.states = new
        self.online = True
        self.last_success = time.monotonic() if now is None else now
        if changed:
            self.generation += 1
        return changed

    def failed(self):
        self.online = False

    def age(self, now=None):
        if self.last_success is None:
            return None
        return (time.monotonic() if now is None else now) - self.last_success

    @staticmethod
    def _sig(s):
        if s is None:
            return None
        return (s.get('state'), repr(sorted((s.get('attributes') or {}).items(), key=lambda kv: kv[0])))


def age_text(seconds):
    if seconds is None:
        return 'never'
    s = int(seconds)
    if s < 90:
        return f'{s}s ago'
    if s < 5400:
        return f'{s // 60} min ago'
    return f'{s // 3600} h ago'
