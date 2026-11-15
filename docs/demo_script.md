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
4. The video opens with the race, so it must be the first action after the
   restock. On a freshly restocked demo, **Two customers, one last item** picks
   the Cactus Art Print A4 (1 left) and sends two orders for it from two random
   stores at once: one is Sold, the other Blocked. If you ran anything else
   since the restock, restock again.
5. Sign in to the AWS console in the right-hand window and open the state machine.
6. Zoom the browser to about 110% so the page is readable in the video.

## Script

| Time | On screen | Say (roughly) |
|---|---|---|
| **0:00 – 0:12** | The dashboard: the shared shelf in the middle, Amazon US and UK on the left, Germany and Türkiye on the right. | "One shelf of stock, four Amazon stores: the US, the UK, Germany and Türkiye. Every store sells from the same number." |
| **0:12 – 0:45** | **Try the demo** → **Two customers, one last item**. Two orders for the last Cactus Art Print appear in Live orders: one **Sold**, one **Blocked** with "wanted 1, only 0 left". The shelf shows 0 and the flow strip stops at **Check the shelf** in red. | "One print left, and two stores order it in the same instant. Only one can win. Checking the shelf and taking the item off it is one conditional DynamoDB transaction, so the second order is blocked, not oversold." |
| **0:45 – 1:05** | In the console open the blocked execution (its name is the order number): the graph ends in the red **OversellPrevented** state; show the Cause text. | "Here's the blocked order in Step Functions. It stopped at the oversell guard, and it's recorded with what was wanted and what was left." |
| **1:05 – 1:30** | **Try the demo** → **A customer in Germany buys one**. The shelf number drops by one, the four stores update one after another, the flow strip fills in, and the order shows **Sold**. | "Now a normal sale. A customer in Germany buys one. API Gateway and a Lambda start the workflow: check the shelf, convert the euro price to dollars with today's ECB rate, update all four stores in parallel, save a receipt." |
| **1:30 – 1:55** | In the console open that execution. Show the graph: ReserveStock → ConvertToUSD → the four parallel **Push Amazon** branches → IsStockLow → FinalizeOrder. Click **Push Amazon US** and show its output `request`. | "Four branches, one per Amazon store, run at the same time. Germany is skipped because Amazon already took its own sale off the shelf. The adapter runs in mock mode: it builds the real Selling Partner API call without sending it." |
| **1:55 – 2:15** | **Try the demo** → **Sell until stock runs low** (it picks the Heart Keychain). The step **Low-stock warning** turns amber and the keychain appears under **Low-stock warnings**, next to the sold-out print from the race. | "This keychain was right at its warning level. One more sale and the workflow writes a low-stock warning straight from Step Functions to DynamoDB, no Lambda needed." |
| **2:15 – 2:30** | Back to the whole dashboard; optionally open **Technical details**. | "Everything scales to zero: Lambda, Step Functions, DynamoDB on demand, S3 and CloudFront. No servers, no pipeline, one `sam deploy`." |

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
