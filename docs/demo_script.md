# OctoMan Lite: 2.5 minute demo script

Target length 2:30 (hard limit 3:00). Two windows side by side: the **dashboard**
(`DashboardUrl` output) on the left, the **Step Functions console** on the right
(state machine `octoman-lite-order-flow`, **Executions** tab).

## Before you hit record

1. Deploy (`sam build && sam deploy --guided`). With `ConsoleLinks=true`, order
   numbers in the order details link straight to their execution graph; with
   `false`, find the execution in the console by its name (the order number).
2. Warm the Lambdas so no cold start shows on camera: open **Try the demo**
   (bottom right), run "A customer in Germany buys one", wait until it says Sold,
   then open **Try the demo** again and choose **Restock the demo**.
3. Check the shelf in the middle shows a product and the four Amazon stores
   around it show the same number.
4. Sign in to the AWS console in the right-hand window and open the state machine.
5. Zoom the browser to about 110% so the page is readable in the video.

## Script

| Time | On screen | Say (roughly) |
|---|---|---|
| **0:00 – 0:15** | The dashboard: the shared shelf in the middle, Amazon US and UK on the left, Germany and Türkiye on the right. | "I sell the same products on Amazon in the US, the UK, Germany and Türkiye. If each store kept its own stock count, two customers could buy the last unit at the same time. That's overselling. OctoMan Lite stops it, fully serverless, deployed with one `sam deploy`." |
| **0:15 – 0:30** | Point at the big **units left** number, then at the four store windows. | "There is one shelf, one number in DynamoDB. Each store window shows what that Amazon store currently offers, in its own currency." |
| **0:30 – 0:55** | Open **Try the demo** → **A customer in Germany buys one**. The panel closes; the shelf number drops by one, the four stores update one after another, the flow strip fills in, and the order shows **Sold** in Live orders. | "A customer in Germany buys one. API Gateway and a Lambda start a Step Functions workflow: check the shelf, convert the euro price to dollars with today's ECB rate, update all four stores in parallel, save a receipt. Germany is skipped because Amazon already took its own sale off the shelf." |
| **0:55 – 1:25** | In the console open that execution (its name is the order number). Show the graph: ReserveStock → ConvertToUSD → the four parallel **Push Amazon** branches → IsStockLow → FinalizeOrder. Click **Push Amazon US** and show its output `request`. | "Here's that execution. Four branches, one per Amazon store, run at the same time. The adapter runs in mock mode: it builds the real Amazon Selling Partner API call, the Listings Items PATCH with the right marketplace ID, without sending it, so anyone can run this without a seller account." |
| **1:25 – 1:45** | **Try the demo** → **Sell until stock runs low**. The shelf drops below its warning level, the step **Low-stock warning** turns amber, and a warning appears under **Low-stock warnings**. | "This product was right at its warning level. One more sale and the workflow takes the low-stock branch and writes a warning straight from Step Functions to DynamoDB, no Lambda needed." |
| **1:45 – 2:15** | **Try the demo** → **Two customers, one last item**. Two orders appear: one **Sold**, one **Blocked** with "wanted 1, only 0 left". The shelf shows 0 and the flow strip stops at **Check the shelf** in red. | "Now the real problem: one item left, and two stores order it in the same instant. Only one can win. Checking the shelf and taking the item off it is one conditional DynamoDB transaction, so the second order is blocked, not oversold." |
| **2:15 – 2:30** | In the console open the blocked execution: the graph ends in the red **OversellPrevented** state; show the Cause text. Optionally open **Technical details** on the dashboard. | "And here's the blocked execution, stopped at the oversell guard, recorded with what was wanted and what was left. Everything scales to zero: Lambda, Step Functions, DynamoDB on demand, S3 and CloudFront. No servers, no pipeline." |

## If you have spare seconds

- **Try the demo** → **Someone orders more than we have**: blocked before
  anything is sold, with "wanted N, only M left".
- Open a receipt in the S3 console (`receipts/YYYY/MM/DD/<order_id>.json`).
- Click any order in **Live orders** to see its details (price in dollars, shelf
  after the sale, how many stores were updated).

## If something goes wrong on camera

- **The demo is sold out:** the corner button turns red; choose **Restock the
  demo** and confirm.
- **An order stays "Processing" for more than ~5 s:** click **Refresh**; the
  dashboard polls for 20 s after each action and then stops.
- **"The store data can't be reached":** check the `ApiUrl` output and that the
  stack finished deploying; the page reads it from `config.js`.
- **"Too many orders at once":** you clicked faster than the 1 order/second
  throttle. Wait a second and try again.
