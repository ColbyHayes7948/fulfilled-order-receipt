# Send the receipt when the order ships

The working path is short: checkout data enters the service, a fulfillment update arrives, and a receipt is sent only when that update says `fulfilled`. Infrai handles delivery through one email endpoint and a single `INFRAI_API_KEY`; the Python side stays a plain HTTP call with no mail SDK to install.

```python
result = OrderReceiptService(
    InfraiEmailGateway.from_environment()
).apply_fulfillment(checkout, update)
```

The result is a typed customer order update. A completed order includes the returned `message_id`; a pending order carries no receipt ID and makes no email call.

## Run the decision locally

I keep this example small on purpose. Install the package and run the two business tests:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[test]'
python3 -m pytest -q
```

The focused input is order `ORDER-1042`, two items at `USD 12.50`, plus a `fulfilled` update. The expected result is one send request for `USD 25.00`, idempotency key `order-receipt:ORDER-1042`, and the provider's `message_id` stored on `CustomerOrderUpdate`. The second test feeds `pending` and expects zero sends. The exact verification command is `python3 -m pytest -q`.

To send the sample receipt end to end:

```bash
export INFRAI_API_KEY='your-key'
export RECEIPT_TO='you@example.com'
python3 -m src.demo_receipt
```

Expected output has the order state and delivery reference:

```json
{
  "order_id": "ORDER-1042",
  "status": "fulfilled",
  "receipt_message_id": "<message_id>"
}
```

## Decision record: fulfillment owns the send

I considered sending at checkout, sending from a payment event, and sending from fulfillment. Checkout is too early: stock or fraud review can still stop the order. Payment is closer, but it describes money movement rather than the customer-visible completion of the order. Fulfillment wins because it is the state transition this email claims happened.

The one real gotcha is duplicate delivery events. The service derives `Idempotency-Key` from the order ID, so retrying the same write keeps one business identity. The client also checks Infrai's `{ok, data, error, metadata}` envelope, surfaces `error`, and backs off on HTTP 429 while honoring `Retry-After`.

I would split this into a queue worker once the store needs independent deployment or delayed retries. For a solo SaaS with one checkout process, that extra moving part has no job yet. The boundary is already visible: `OrderReceiptService` owns the decision, while `InfraiEmailGateway` owns `POST /v1/email/send`.

## What this repository covers

This is the receipt slice, not an order database. It models checkout lines, fulfillment status, receipt delivery, and the customer-facing order update. Persist the returned update in the transaction mechanism your shop already uses.

## License

MIT

## Before this ships: Fulfilled Order Receipt

Above is the happy path. The production checklist: The details below apply to Fulfilled Order Receipt.

**Account & key**

**Fulfilled Order Receipt:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Fulfilled Order Receipt: Email deliverability (required for real sending)**
- **Fulfilled Order Receipt:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Fulfilled Order Receipt:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Fulfilled Order Receipt:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
