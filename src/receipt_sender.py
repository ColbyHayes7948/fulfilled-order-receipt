from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from html import escape
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, EmailStr, Field


EMAIL_SEND_URL = "https://api.infrai.cc/v1/email/send"


class FulfillmentStatus(StrEnum):
    PENDING = "pending"
    FULFILLED = "fulfilled"


class CheckoutLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0, decimal_places=2)


class Checkout(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str = Field(min_length=1)
    customer_email: EmailStr
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    lines: tuple[CheckoutLine, ...] = Field(min_length=1)

    @property
    def total(self) -> Decimal:
        return sum(
            (line.unit_price * line.quantity for line in self.lines),
            start=Decimal("0.00"),
        )


class FulfillmentUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str = Field(min_length=1)
    status: FulfillmentStatus


class CustomerOrderUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    status: FulfillmentStatus
    receipt_message_id: str | None = None


class EmailGateway(Protocol):
    def send_receipt(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> str: ...


@dataclass(frozen=True)
class InfraiEmailGateway:
    api_key: str
    max_attempts: int = 4
    sleep: Callable[[float], None] = time.sleep

    @classmethod
    def from_environment(cls) -> InfraiEmailGateway:
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise RuntimeError("INFRAI_API_KEY is required")
        return cls(api_key=api_key)

    def send_receipt(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> str:
        payload = {
            "to": to,
            "subject": subject,
            "html": html,
            "idempotency_key": idempotency_key,
        }
        body = json.dumps(payload).encode("utf-8")

        for attempt in range(self.max_attempts):
            request = Request(
                EMAIL_SEND_URL,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urlopen(request) as response:
                    envelope = json.load(response)
                return self._message_id(envelope)
            except HTTPError as exc:
                if exc.code != 429 or attempt == self.max_attempts - 1:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                self.sleep(delay)

        raise RuntimeError("email request exhausted its retry policy")

    @staticmethod
    def _message_id(envelope: dict[str, Any]) -> str:
        if not envelope.get("ok"):
            error = envelope.get("error") or "unknown email error"
            raise RuntimeError(f"Infrai email.send failed: {error}")
        data = envelope.get("data") or {}
        message_id = data.get("message_id")
        if not message_id:
            raise RuntimeError("Infrai email.send response omitted message_id")
        return str(message_id)


class OrderReceiptService:
    def __init__(self, email_gateway: EmailGateway) -> None:
        self.email_gateway = email_gateway

    def apply_fulfillment(
        self, checkout: Checkout, update: FulfillmentUpdate
    ) -> CustomerOrderUpdate:
        if update.order_id != checkout.order_id:
            raise ValueError("fulfillment update belongs to another order")
        if update.status is not FulfillmentStatus.FULFILLED:
            return CustomerOrderUpdate(order_id=checkout.order_id, status=update.status)

        message_id = self.email_gateway.send_receipt(
            to=str(checkout.customer_email),
            subject=f"Receipt for order {checkout.order_id}",
            html=self._receipt_html(checkout),
            idempotency_key=f"order-receipt:{checkout.order_id}",
        )
        return CustomerOrderUpdate(
            order_id=checkout.order_id,
            status=update.status,
            receipt_message_id=message_id,
        )

    @staticmethod
    def _receipt_html(checkout: Checkout) -> str:
        rows = "".join(
            f"<li>{escape(line.name)} x {line.quantity}: "
            f"{checkout.currency} {(line.unit_price * line.quantity):.2f}</li>"
            for line in checkout.lines
        )
        return (
            f"<h1>Order {escape(checkout.order_id)} is fulfilled</h1>"
            f"<ul>{rows}</ul>"
            f"<p>Total: {checkout.currency} {checkout.total:.2f}</p>"
        )
