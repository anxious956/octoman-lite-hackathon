# Build notes

Working notes for the OctoMan Lite hackathon build (AWS Builder Center
"Weekend Challenge: No Pipeline, No Problem", deadline 2026-11-16 13:00 PST).

## Scope

One flow, end to end: POST /orders -> Step Functions (reserve stock ->
push to Amazon US/UK/DE/TR in parallel -> convert to USD -> low-stock alert ->
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

The README carries the live demo link and the video link by the author's choice.
The region, account and API host are still kept out of the repo.

## After a deploy that changes seed data

Press **Restock the demo** on the dashboard once.

## Verification status

- Local: 170 pytest tests (moto, no AWS), `sam validate --lint`, `sam build`, and a
  local dashboard run against a fake API.
- State machine: on 2026-11-15 the definition passed the Step Functions
  ValidateStateMachineDefinition API, plus mocked TestState runs for ReserveStock
  (success and caught InsufficientStock), RecordRejection, OversellPrevented,
  IsStockLow, RaiseLowStockAlert and FinalizeOrder, and after the FX catch was
  added, ConvertToUSD (success; function error and timeout both caught with the
  `fallback_error` fx and routed to PushToMarketplaces; FinalizeOrder accepts that
  fx). Nothing was invoked or created. These runs used the previous step order
  (conversion before the push).
- Step order changed afterwards: the stores are now updated first and the
  conversion runs after them; its catch now routes to IsStockLow. Checked
  locally (unit tests, `sam validate --lint`, `sam build`) and on the redeployed
  stack (below); not run through ValidateStateMachineDefinition or TestState.
- Deployed stack, repeated on 2026-11-15 after redeploying with the new step
  order, through the public dashboard and API only (no AWS console or CLI):
  - the served dashboard files match the repo (tabs, photos, diagram order);
  - Restock the demo: 15 products back at seed stock on all four stores;
  - a sale in Germany completed, converted to dollars at the ECB rate; Germany
    was skipped (origin) and the US, UK and Türkiye listings were updated; a
    receipt key was written;
  - the last-item race (two stores, same moment): one sale, one block, stock 0;
  - an order for more than the stock was blocked and the stock did not change;
  - a sale that took a product under its warning level raised one alert.
  The API does not show the order of the steps; the Step Functions console
  does. The console graph of a sold execution on the redeployed stack shows
  PushToMarketplaces and its four branches succeeded before ConvertToUSD
  (`docs/execution-sold.png`). A blocked execution shows that only
  ReserveStock (caught error), RecordRejection and OversellPrevented ran
  (`docs/execution-blocked.png`).
- Not repeated under the new order: a conversion failure (fallback) on AWS.
- Not verified yet: `sam local invoke` (Docker was not running during the
  build), and the phone layout on the deployed site (only checked locally at
  390 px against a fake API).

## Key decisions (short)

- Standard workflow: the execution graph is the demo; execution name = order id.
- One DynamoDB transaction for "check and decrement" + "create order once".
- Stores are updated before the currency conversion: the conversion calls an
  outside feed, so a slow feed must never delay a stock update.
- `stock_version` guards each site's listing copy against stale pushes.
- Mock marketplace adapter by default; same `update_inventory` signature as the
  real adapter; live mode deliberately unavailable.
- Private S3 + CloudFront OAC for the dashboard; a custom resource publishes it.
- `Prefix` parameter locked to `octoman-lite[-suffix]`; no physical name uses the
  stack name.
- API throttling 10 rps, `POST /orders` 1 rps (cost guard for a public demo API).
