# OctoMan Lite: 2.5 minute demo script

Target length 2:30 (hard limit 3:00). Two windows side by side: the **dashboard**
(`DashboardUrl` output) on the left, the **Step Functions console** on the right
(state machine `octoman-lite-order-flow`).

## Before you hit record

1. Deploy (`sam build && sam deploy --guided`) with `ConsoleLinks=true`, so order
   ids on the dashboard link straight to their execution graph.
2. Warm the Lambdas so no cold start shows on camera: click one order on any
   product, wait for it to complete, then reset the data:
   `python scripts/seed.py --profile <your-profile> --region <region> --reset`
3. Reload the dashboard. Check that `OCTO-LAMP-004` shows stock 5 / threshold 5,
   `OCTO-KEY-009` shows 3 / 3 and `OCTO-PRINT-006` shows 1.
4. Sign in to the AWS console in the right-hand window and open the state machine.
5. Zoom the browser to about 110% so the table is readable in the video.

## Script

| Time | On screen | Say (roughly) |
|---|---|---|
| **0:00 – 0:15** | Dashboard, products table. | "I sell the same products on eBay US, UK, Germany and Turkey. Each site thinks it has the full stock, so two buyers on two sites can buy the last unit at the same time. That's overselling. OctoMan Lite stops it, fully serverless, deployed with one `sam deploy`." |
| **0:15 – 0:30** | Point at the **Stock** column, then the four eBay columns. | "Central stock in DynamoDB is the single source of truth. Each eBay column is the quantity we last pushed to that site, in its own currency." |
| **0:30 – 0:55** | On `OCTO-MUG-001` click **DE**. The order appears as `COMPLETED`; the stock goes 24 → 23 and all four eBay columns flash to 23. | "An order comes in from eBay Germany. API Gateway and a Lambda start a Step Functions workflow. Stock is decremented, the euro total is converted to dollars with live ECB rates, and the new quantity is pushed to every other site at once. Germany is skipped because it already sold the item." |
| **0:55 – 1:25** | Click the order id. In the console show the **graph**: ReserveStock → ConvertToUSD → the four parallel **Push eBay** branches → IsStockLow → FinalizeOrder. Click **Push eBay US** and show its output `request`. | "Here's that execution. Four branches run in parallel, one per marketplace. The adapter runs in mock mode: it builds the real eBay Inventory API call, the right marketplace header and language, without sending it, so anyone can run this without an eBay account. The receipt lands in S3." |
| **1:25 – 1:45** | Back on the dashboard, on `OCTO-LAMP-004` (stock 5, threshold 5) click **US**. Stock goes to 4 and the row turns orange; an alert `LOW` appears in **Low-stock alerts**. | "This lamp is at its threshold. One more sale and the workflow takes the low-stock branch and writes an alert directly from Step Functions to DynamoDB, no Lambda needed." |
| **1:45 – 2:15** | On `OCTO-PRINT-006` (stock 1) click **Race: last unit**. Two orders appear: one `COMPLETED`, one `REJECTED` with "requested 1, available 0". The alert shows `OUT_OF_STOCK`. | "Now the real problem: one print left, and the US and Germany order it in the same instant. Only one can win. The check and the decrement are a single conditional DynamoDB transaction, so the second order is rejected, not oversold." |
| **2:15 – 2:30** | Click the rejected order id. The graph ends in the red **OversellPrevented** state; show the Cause text. | "And here's that rejected execution, stopped at the oversell guard, recorded with what was requested and what was available. Everything here scales to zero: Lambda, Step Functions, DynamoDB on demand, S3 and CloudFront. No servers, no pipeline." |

## If you have spare seconds

- Show a single oversell without the race: `OCTO-KEY-009`, set **Qty** to 5,
  click **GB** → `REJECTED`, requested 5, available 3.
- Open a receipt in the S3 console (`receipts/YYYY/MM/DD/<order_id>.json`).

## If something goes wrong on camera

- **An order stays `RESERVED` for more than ~5 s:** click **Refresh**; the
  dashboard polls for 20 s after each click and then stops.
- **"Could not reach the API":** check the `ApiUrl` output and that the stack
  finished deploying; the page reads it from `config.js`.
- **HTTP 429 in the activity log:** you clicked faster than the 1 order/second
  throttle. Wait a second and click again.
