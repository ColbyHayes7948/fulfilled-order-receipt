import json
from decimal import Decimal
from unittest.mock import patch

from src.receipt_sender import (
    Checkout,
    CheckoutLine,
    FulfillmentStatus,
    FulfillmentUpdate,
    InfraiEmailGateway,
    OrderReceiptService,
)


class RecordingEmailGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def send_receipt(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> str:
        self.calls.append(
            {
                "to": to,
                "subject": subject,
                "html": html,
                "idempotency_key": idempotency_key,
            }
        )
        return "msg_receipt_1042"


def checkout() -> Checkout:
    return Checkout(
        order_id="ORDER-1042",
        customer_email="buyer@example.com",
        currency="USD",
        lines=(
            CheckoutLine(
                name="Field Notes",
                quantity=2,
                unit_price=Decimal("12.50"),
            ),
        ),
    )


def test_fulfilled_order_sends_one_receipt_and_records_message_id() -> None:
    gateway = RecordingEmailGateway()
    result = OrderReceiptService(gateway).apply_fulfillment(
        checkout(),
        FulfillmentUpdate(
            order_id="ORDER-1042", status=FulfillmentStatus.FULFILLED
        ),
    )

    assert result.receipt_message_id == "msg_receipt_1042"
    assert gateway.calls == [
        {
            "to": "buyer@example.com",
            "subject": "Receipt for order ORDER-1042",
            "html": (
                "<h1>Order ORDER-1042 is fulfilled</h1>"
                "<ul><li>Field Notes x 2: USD 25.00</li></ul>"
                "<p>Total: USD 25.00</p>"
            ),
            "idempotency_key": "order-receipt:ORDER-1042",
        }
    ]


def test_pending_order_does_not_send_a_receipt() -> None:
    gateway = RecordingEmailGateway()
    result = OrderReceiptService(gateway).apply_fulfillment(
        checkout(),
        FulfillmentUpdate(
            order_id="ORDER-1042", status=FulfillmentStatus.PENDING
        ),
    )

    assert result.receipt_message_id is None
    assert gateway.calls == []


def test_infrai_gateway_sends_idempotency_key_in_request_body() -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b'{"ok": true, "data": {"message_id": "msg_1042"}}'

    with patch("src.receipt_sender.urlopen", return_value=Response()) as urlopen:
        InfraiEmailGateway(api_key="test-key").send_receipt(
            to="buyer@example.com",
            subject="Receipt",
            html="<p>Paid</p>",
            idempotency_key="order-receipt:ORDER-1042",
        )

    request = urlopen.call_args.args[0]
    assert json.loads(request.data) == {
        "to": "buyer@example.com",
        "subject": "Receipt",
        "html": "<p>Paid</p>",
        "idempotency_key": "order-receipt:ORDER-1042",
    }
    assert "Idempotency-key" not in request.headers
