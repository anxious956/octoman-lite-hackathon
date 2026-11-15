# Build notes

Working notes for the OctoMan Lite hackathon build (AWS Builder Center
"Weekend Challenge: No Pipeline, No Problem", deadline 2026-11-16 13:00 PST).

## Scope

One flow, end to end: POST /orders -> Step Functions (reserve stock ->
convert to USD -> push to Amazon US/UK/DE/TR in parallel -> low-stock alert ->
receipt in S3), plus GET /products, /orders, /alerts and a static dashboard.
Out of scope: auth and multi-tenancy, error tracking, CI/CD, nested stacks,
rate limiting beyond API Gateway throttling, circuit breakers, payments, other
marketplaces' APIs, live Amazon calls.

## Build steps (each one a local commit)

- [x] 1. `template.yaml`, `samconfig.toml`, `.gitignore`. Verify: `sam validate --lint`
- [x] 2. Shared modules, six handlers, sample events, unit tests. Verify: `python -m pytest -q`, `sam build`
- [x] 3. State machine (`statemachine/order_flow.asl.json`, JSONata). Verify: `python -m pytest -q tests/test_asl.py`
- [x] 4. `scripts/seed.py` (15 synthetic products). Verify: `python scripts/seed.py --dry-run`
- [x] 5. Dashboard + deploy custom resource. Verify: `python -m http.server 8080 -d dashboard` and `?api=<ApiUrl>`
- [x] 6. README, demo script, these notes
- [x] 7. Credential and real-data scan of the whole folder: clean (only moto's fake
      "testing" credentials and AWS's documented example account id in tests).
- [x] 8. First real deploy (`sam deploy --guided --profile <your-profile>`), seed, run the demo script once:
      done; see "Verification status".

## Deploying

Advice for anyone deploying this: use a dedicated, non-production account
(`--profile <your-profile>`), sign in first and confirm the account with
`aws sts get-caller-identity`. The plan is to leave the stack running until the
winners are announced, with a $5 monthly AWS Budgets alert (README, "If you
leave it running"), and to run `sam delete` afterwards.

## After a deploy that changes seed data

Press **Restock the demo** on the dashboard once.

## Verification status

- Local: 166 pytest tests (moto, no AWS), `sam validate --lint`, `sam build`, and a
  local dashboard run against a fake API.
- State machine: on 2026-11-15 the definition passed the Step Functions
  ValidateStateMachineDefinition API, plus mocked TestState runs for ReserveStock
  (success and caught InsufficientStock), RecordRejection, OversellPrevented,
  IsStockLow, RaiseLowStockAlert and FinalizeOrder, and after the FX catch was
  added, ConvertToUSD (success; function error and timeout both caught with the
  `fallback_error` fx and routed to PushToMarketplaces; FinalizeOrder accepts that
  fx). Nothing was invoked or created.
- Deployed stack: a sale in Germany was converted to dollars at the ECB rate
  and all four stores were handled; the last-item race gave one sale and one
  block; an order for more than the stock was blocked; a low-stock warning was
  raised; the dashboard was served through CloudFront with its config written by
  the custom resource.
- Not verified yet: `sam local invoke` (Docker was not running during the
  build), and the phone layout on the deployed site (only checked locally at
  390 px against a fake API).

## Key decisions (short)

- Standard workflow: the execution graph is the demo; execution name = order id.
- One DynamoDB transaction for "check and decrement" + "create order once".
- `stock_version` guards each site's listing copy against stale pushes.
- Mock marketplace adapter by default; same `update_inventory` signature as the
  real adapter; live mode deliberately unavailable.
- Private S3 + CloudFront OAC for the dashboard; a custom resource publishes it.
- `Prefix` parameter locked to `octoman-lite[-suffix]`; no physical name uses the
  stack name.
- API throttling 10 rps, `POST /orders` 1 rps (cost guard for a public demo API).
