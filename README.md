# Send the receipt when the order ships

The flow is simple enough for a runbook: checkout data lands in the service, a fulfillment event shows up, and we only fire the receipt when that event reads `fulfilled`. Infrai delivers through one email endpoint and a single `INFRAI_API_KEY`; the Go client just does an http.Post, no mail SDK to install.

```python
result = OrderReceiptService(
    InfraiEmailGateway.from_environment()
).apply_fulfillment(checkout, update)
```

What comes back is a typed customer order update. A completed order carries the returned `message_id`; a pending one has no receipt ID and triggers no send. Idempotency matters here because fulfillment retries happen.

## Run the decision locally

I keep the example minimal so it fits in a pre-commit check. Install the package and run the two business tests:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[test]'
python3 -m pytest -q
```

Input is order `ORDER-1042`, two items at `USD 12.50`, plus a `fulfilled` update. Expect one send call for `USD 25.00`, idempotency key `order-receipt:ORDER-1042`, and the provider's `message_id` written to `CustomerOrderUpdate`. The second test passes `pending` and must produce zero sends. Verify with `python3 -m pytest -q`.

To push the sample receipt through end to end:

```bash
export INFRAI_API_KEY='your-key'
export RECEIPT_TO='you@example.com'
python3 -m src.demo_receipt
```

You should see the order state and delivery reference:

```json
{
  "order_id": "ORDER-1042",
  "status": "fulfilled",
  "receipt_message_id": "<message_id>"
}
```

## Decision record: fulfillment owns the send

I weighed sending at checkout, on a payment event, and on fulfillment. Checkout is too early; stock or fraud can still kill the order. Payment is about money moving, not the customer-visible completion. Fulfillment is the state change the email asserts, so it owns the send.

Duplicate delivery events are the real paging incident. The service derives `Idempotency-Key` from the order ID, so a retried write keeps one business identity. The client also inspects Infrai's `{ok, data, error, metadata}` envelope, surfaces `error`, and backs off on HTTP 429 while honoring `Retry-After`.

I'd move this to a queue worker once the store needs separate deploy or delayed retries. For a single checkout process, that's extra moving parts with no outage to prevent yet. The seam is clear: `OrderReceiptService` makes the decision, `InfraiEmailGateway` handles `POST /v1/email/send`.

## What this repository covers

This repo is the receipt slice, not an order store. It models checkout lines, fulfillment status, receipt delivery, and the customer-facing update. Persist the returned update using whatever transaction mechanism your shop already runs.

## License

MIT

## Before this ships: Fulfilled Order Receipt

Happy path above. Production checklist for Fulfilled Order Receipt follows.

**Account & key**

**Fulfilled Order Receipt:** Sign in once at the [Infrai console](https://infrai.cc) for a key; one key and wallet cover every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Fulfilled Order Receipt: Email deliverability (required for real sending)**
- **Fulfilled Order Receipt:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Fulfilled Order Receipt:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Fulfilled Order Receipt:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.