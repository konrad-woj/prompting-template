"""In-memory stand-in for the order, refund, email and ticketing systems."""

from dataclasses import dataclass, field
from typing import Any

from prompt_kit import ErrorKind, ToolError

ORDERS = {
    "ORD-1042": {
        "order_id": "ORD-1042",
        "email": "bob@example.com",
        "status": "delivered",
        "amount": 42.00,
        "currency": "EUR",
        "delivered_on": "2026-09-14",
        "refund_eligible": True,
        "refund_reason": "within the 30-day window",
    },
    "ORD-0907": {
        "order_id": "ORD-0907",
        "email": "bob@example.com",
        "status": "delivered",
        "amount": 120.00,
        "currency": "EUR",
        "delivered_on": "2026-07-02",
        "refund_eligible": False,
        "refund_reason": "delivered more than 30 days ago",
    },
}


@dataclass
class SupportBackend:
    """Tool implementations. `fail_next` injects errors per tool to exercise retry and fixed paths."""

    fail_next: dict[str, list[ToolError]] = field(default_factory=dict)
    processed_idempotency_keys: set[str] = field(default_factory=set)

    def _maybe_fail(self, tool_name: str) -> None:
        queued_errors = self.fail_next.get(tool_name)
        if queued_errors:
            raise queued_errors.pop(0)

    async def verify_customer(self, order_id: str, email: str) -> dict[str, Any]:
        self._maybe_fail("verify_customer")
        order = ORDERS.get(order_id)
        return {
            "verified": bool(order and order["email"].lower() == email.strip().lower())
        }

    async def lookup_order(self, order_id: str) -> dict[str, Any]:
        self._maybe_fail("lookup_order")
        order = ORDERS.get(order_id)
        if order is None:
            raise ToolError(ErrorKind.NOT_FOUND, hint="Order IDs look like ORD-12345.")
        return {key: value for key, value in order.items() if key != "email"}

    async def issue_refund(
        self, order_id: str, amount: float, idempotency_key: str
    ) -> dict[str, Any]:
        self._maybe_fail("issue_refund")
        order = ORDERS.get(order_id)
        if order is None or amount != order["amount"]:
            raise ToolError(
                ErrorKind.INVALID_INPUT, hint="Use the exact amount from lookup_order."
            )
        if idempotency_key in self.processed_idempotency_keys:
            return {"refund_id": f"RF-{order_id}", "status": "already_processed"}
        self.processed_idempotency_keys.add(idempotency_key)
        return {"refund_id": f"RF-{order_id}", "status": "processing"}

    async def send_email(
        self, subject: str, body: str, idempotency_key: str
    ) -> dict[str, Any]:
        self._maybe_fail("send_email")
        return {"status": "sent"}

    async def escalate_to_human(
        self, summary: str, idempotency_key: str
    ) -> dict[str, Any]:
        self._maybe_fail("escalate_to_human")
        return {"ticket_reference": "HELP-5531", "expected_response_hours": 4}

    def implementations(self) -> dict[str, Any]:
        return {
            "verify_customer": self.verify_customer,
            "lookup_order": self.lookup_order,
            "issue_refund": self.issue_refund,
            "send_email": self.send_email,
            "escalate_to_human": self.escalate_to_human,
        }
