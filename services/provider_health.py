from contextlib import contextmanager
from dataclasses import dataclass
import threading
import time
from uuid import uuid4


ProviderKey = tuple[str, str]


@dataclass
class ProviderCooldown:
    until: float
    retry_after_seconds: int


@dataclass
class ProviderBudget:
    token_limit: int | None = None
    remaining_tokens: int | None = None
    token_reset: str | None = None
    token_reset_deadline: float | None = None
    request_limit: int | None = None
    remaining_requests: int | None = None
    request_reset: str | None = None
    request_reset_deadline: float | None = None


@dataclass
class TokenReservation:
    key: ProviderKey
    tokens: int
    request_reserved: bool


class ProviderHealth:
    """Circuit breaker and provider budgets scoped by provider and model."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, clock=time.monotonic, max_concurrent_requests: int = 1):
        self._clock = clock
        self._lock = threading.RLock()
        self._cooldowns: dict[ProviderKey, ProviderCooldown] = {}
        self._states: dict[ProviderKey, str] = {}
        self._budgets: dict[ProviderKey, ProviderBudget] = {}
        self._semaphores: dict[ProviderKey, threading.BoundedSemaphore] = {}
        self._probe_active: set[ProviderKey] = set()
        self._reservations: dict[str, TokenReservation] = {}
        self._max_concurrent_requests = max(1, max_concurrent_requests)

    @staticmethod
    def _key(provider: str, model: str | None = None) -> ProviderKey:
        return provider.lower(), model or ""

    def _refresh_budget(self, key: ProviderKey) -> ProviderBudget:
        budget = self._budgets.setdefault(key, ProviderBudget())
        now = self._clock()
        if budget.token_reset_deadline is not None and budget.token_reset_deadline <= now:
            budget.remaining_tokens = None
            budget.token_reset_deadline = None
            budget.token_reset = None
        if budget.request_reset_deadline is not None and budget.request_reset_deadline <= now:
            budget.remaining_requests = None
            budget.request_reset_deadline = None
            budget.request_reset = None
        return budget

    def _state(self, key: ProviderKey) -> str:
        cooldown = self._cooldowns.get(key)
        if cooldown and cooldown.until <= self._clock():
            self._cooldowns.pop(key, None)
            if self._states.get(key) == self.OPEN:
                self._states[key] = self.HALF_OPEN
        return self._states.get(key, self.CLOSED)

    def state(self, provider: str, model: str | None = None) -> str:
        with self._lock:
            return self._state(self._key(provider, model))

    def remaining(self, provider: str, model: str | None = None) -> int:
        with self._lock:
            key = self._key(provider, model)
            cooldown = self._cooldowns.get(key)
            if cooldown is None:
                return 0
            remaining = max(0, cooldown.until - self._clock())
            if remaining == 0:
                self._state(key)
                return 0
            return max(1, round(remaining))

    def cooldown(
        self,
        provider: str,
        seconds: int,
        model: str | None = None,
        *,
        open_circuit: bool = True,
    ) -> int:
        duration = max(1, int(seconds))
        with self._lock:
            key = self._key(provider, model)
            self._cooldowns[key] = ProviderCooldown(
                until=self._clock() + duration,
                retry_after_seconds=duration,
            )
            if open_circuit:
                self._states[key] = self.OPEN
        return duration

    def update_budget(
        self,
        provider: str,
        model: str | None = None,
        **values,
    ) -> None:
        with self._lock:
            budget = self._refresh_budget(self._key(provider, model))
            token_reset_seconds = values.pop("token_reset_seconds", None)
            request_reset_seconds = values.pop("request_reset_seconds", None)
            for key, value in values.items():
                if hasattr(budget, key) and value is not None:
                    setattr(budget, key, value)
            if token_reset_seconds is not None:
                budget.token_reset_deadline = self._clock() + token_reset_seconds
            if request_reset_seconds is not None:
                budget.request_reset_deadline = self._clock() + request_reset_seconds

    def budget(self, provider: str, model: str | None = None) -> dict:
        with self._lock:
            value = self._refresh_budget(self._key(provider, model))
            return value.__dict__.copy()

    def reserve(
        self,
        provider: str,
        estimated_tokens: int = 0,
        model: str | None = None,
    ) -> str | None:
        """Atomically reserve one request and the estimated token cost."""
        with self._lock:
            key = self._key(provider, model)
            budget = self._refresh_budget(key)
            if budget.remaining_requests is not None and budget.remaining_requests <= 0:
                return None
            if estimated_tokens and budget.remaining_tokens is not None:
                if estimated_tokens > budget.remaining_tokens:
                    return None
                budget.remaining_tokens -= estimated_tokens
            request_reserved = budget.remaining_requests is not None
            if request_reserved:
                budget.remaining_requests -= 1
            reservation_id = f"r-{uuid4()}"
            self._reservations[reservation_id] = TokenReservation(
                key=key,
                tokens=estimated_tokens if budget.remaining_tokens is not None else 0,
                request_reserved=request_reserved,
            )
            return reservation_id

    def reconcile(
        self,
        reservation_id: str | None,
        *,
        actual_tokens: int | None = None,
        authoritative_tokens: bool = False,
        authoritative_requests: bool = False,
        release: bool = False,
    ) -> None:
        if not reservation_id:
            return
        with self._lock:
            reservation = self._reservations.pop(reservation_id, None)
            if reservation is None:
                return
            budget = self._refresh_budget(reservation.key)
            if reservation.tokens and not authoritative_tokens:
                budget.remaining_tokens = (budget.remaining_tokens or 0) + reservation.tokens
                if not release and actual_tokens is not None:
                    budget.remaining_tokens = max(0, budget.remaining_tokens - actual_tokens)
            if reservation.request_reserved and release and not authoritative_requests:
                budget.remaining_requests = (budget.remaining_requests or 0) + 1

    def mark_success(self, provider: str, model: str | None = None) -> None:
        with self._lock:
            key = self._key(provider, model)
            if self._state(key) == self.HALF_OPEN:
                self._states[key] = self.CLOSED

    @contextmanager
    def request(self, provider: str, model: str | None = None):
        with self._lock:
            key = self._key(provider, model)
            semaphore = self._semaphores.setdefault(
                key, threading.BoundedSemaphore(self._max_concurrent_requests)
            )
            state = self._state(key)
            if state == self.OPEN:
                raise RuntimeError("provider circuit is open")
            if state == self.HALF_OPEN:
                if key in self._probe_active:
                    raise RuntimeError("provider half-open probe already running")
                self._probe_active.add(key)
        semaphore.acquire()
        try:
            yield
        finally:
            semaphore.release()
            with self._lock:
                self._probe_active.discard(key)
