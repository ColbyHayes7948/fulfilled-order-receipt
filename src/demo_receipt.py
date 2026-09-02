import json
import os
from decimal import Decimal

from src.receipt_sender import (
    Checkout,
    CheckoutLine,
    FulfillmentStatus,
    FulfillmentUpdate,
    InfraiEmailGateway,
    OrderReceiptService,
)


def main() -> None:
    recipient = os.environ.get("RECEIPT_TO")
    if not recipient:
        raise RuntimeError("RECEIPT_TO is required")

    checkout = Checkout(
        order_id="ORDER-1042",
        customer_email=recipient,
        currency="USD",
        lines=(
            CheckoutLine(
                name="Founder's Field Notes",
                quantity=1,
                unit_price=Decimal("24.00"),
            ),
        ),
    )
    update = FulfillmentUpdate(
        order_id=checkout.order_id,
        status=FulfillmentStatus.FULFILLED,
    )
    result = OrderReceiptService(
        InfraiEmailGateway.from_environment()
    ).apply_fulfillment(checkout, update)
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()

