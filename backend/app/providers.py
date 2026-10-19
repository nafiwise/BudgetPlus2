"""Provider boundary. Routing is independent of future issuing/network adapters."""
from typing import Protocol


class AuthorizationProvider(Protocol):
    def authorize(self, decision: dict, request_id: str) -> dict: ...


class SimulatedProvider:
    def authorize(self, decision: dict, request_id: str) -> dict:
        return {**decision, 'provider': 'simulated', 'simulated': True,
                'authorizationId': request_id, 'settled': False,
                'paymentNotice': 'Decision engine only. No network authorization, charge or settlement.'}
