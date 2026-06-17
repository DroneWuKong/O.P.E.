import time
from dataclasses import dataclass, field


@dataclass
class ProviderHealth:
    cooldowns: dict[str, float] = field(default_factory=dict)
    last_failure: dict[str, str] = field(default_factory=dict)

    def is_available(self, model: str) -> bool:
        return time.time() >= self.cooldowns.get(model, 0)

    def mark_failure(self, model: str, reason: str, cooldown_seconds: int = 60) -> None:
        self.last_failure[model] = reason
        if reason in {'rate_limit', 'quota', 'timeout', 'overloaded'}:
            self.cooldowns[model] = time.time() + cooldown_seconds

    def status(self) -> dict:
        now = time.time()
        return {
            model: {
                'available': now >= until,
                'cooldown_remaining_seconds': max(0, int(until - now)),
                'last_failure': self.last_failure.get(model),
            }
            for model, until in self.cooldowns.items()
        }


provider_health = ProviderHealth()
