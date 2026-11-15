<!--
NOTE FOR THE AUTHOR (delete this block before posting):
- Deadline: November 16, 2026, 1:00 PM PST.
- Submit in the challenge's "Your project" tab. Paste PART 1 as the project
  description. Put the public video link (under 3 minutes, showing the build
  running end to end) in the "demo" field, and the live dashboard / repo links
  where the form asks for them.
- From the official rules (pass/fail): the written project must be published on
  AWS Builder Center; the video goes in the "demo" field, under 3 minutes,
  public on YouTube, Vimeo, Facebook Video or Youku, with no third-party
  trademarks or copyrighted music; at least one serverless AWS service, no
  servers or pipelines; an original, previously unpublished project. One entry
  per person or team, teams of at most five; people in excluded countries and
  Amazon employees cannot enter. See the VIDEO CHECKLIST at the end.
- The rules say nothing about AI use, so the optional AI-assistant line is
  purely your choice.
- The draft is written as "I". If you submit as a team, change it to "we".
- Replace <LIVE_DEMO_URL> and <VIDEO_URL>.
- PART 2 (the longer article) is optional, e.g. for a Builder Center post; check
  any title prefix, tags and minimum length there before posting it.
-->

# PART 1: Project description (paste into "Your project")

Two customers in two countries click Buy on the last unit in the same second.
Only one of them should get it.

## Title (pick one)

1. OctoMan Lite: one shelf, four Amazon stores, and the last unit sells only once
2. OctoMan Lite: serverless stock that can't be oversold across four marketplaces
3. OctoMan Lite: two countries buy the last item at once, and only one wins

## Card summary (shown in the project list)

One stock level for four Amazon stores, checked in a single conditional DynamoDB
transaction, so the last unit sells only once. Step Functions fans each sale out
to all four stores in parallel. Lambda, API Gateway, S3, CloudFront: one SAM
template, no pipeline, scales to zero.

## Tags

#serverless #aws-step-functions #amazon-dynamodb #aws-lambda #aws-sam

## Description

Two customers in two countries click Buy on the last unit in the same second.
Only one of them should get it.

### The problem I picked and what the build does

When a seller lists the same product on several marketplaces, each one keeps
its own stock count, so two customers in two countries can buy the last unit in
the same second and one order has to be cancelled. OctoMan Lite keeps one shared
stock level (the "shelf") for four Amazon stores (US, UK, Germany, Türkiye) and
checks it in one atomic step before any sale, so the last unit can only be sold
once. A live dashboard shows the shelf, the four stores, every order and where
it was stopped if it was blocked.

### The serverless AWS services and how they connect

An HTTP API (Amazon API Gateway) sends each order to an AWS Lambda function that
starts an AWS Step Functions workflow named after the order. One conditional
Amazon DynamoDB transaction reserves the stock or blocks the order; a Lambda
converts the price to US dollars with ECB rates; a Parallel state updates the
four stores at once; a low-stock warning is written straight to DynamoDB; and a
Lambda saves a receipt to Amazon S3. The dashboard is a static site in a private
S3 bucket behind Amazon CloudFront. The architecture diagram is attached
(`docs/architecture.png`).

### No servers, no deployment pipeline

Every part is a managed serverless service: no instances, no containers, no
CI/CD. The whole system is one AWS SAM template, deployed with `sam build` and
`sam deploy`. A CloudFormation custom resource publishes the dashboard during
the deploy, so there is no separate upload step.

### Cost when idle

It scales to zero: no instances, no provisioned capacity, no fixed monthly fee.
An idle stack costs nothing beyond a few kilobytes of storage, and one order costs
about $0.0003, mostly Step Functions state transitions. The README has the
[cost table](https://github.com/anxious956/octoman-lite-hackathon#cost).

### Why it stands out

- **The idea:** overselling is prevented by a single
  conditional DynamoDB transaction ("enough left?" and "take it off the shelf"
  happen together), so two stores racing for the last unit cannot both win. A
  version number on every stock change stops a late store update from
  overwriting newer stock, even right after the demo is restocked.
- **How reliably it runs:** verified on the deployed stack: a Germany order for
  one mug at €11.99 was converted to $13.25 at the ECB rate and all four stores
  were updated; two stores ordering the last print at once gave one sale and one
  block; 5 keychains ordered with 3 in stock were blocked. 166 automated tests
  run without an AWS account, every function has its own least-privilege IAM
  policy, and "Restock the demo" puts every product back so the demo never stays
  sold out.
- **Who it helps:** every oversold order is a cancellation that costs
  the seller money and marketplace rating. The same pattern (one atomic check
  and decrement, then fan out) applies to any shared stock, seat or quota.
- **How it is told:** the page is built around one picture, one
  shelf and four stores, and four short demo stories: a customer buys one,
  stock runs low, two customers want the last item, someone orders more than
  we have.

### Reuse this pattern

The SAM template is one flat file meant to be copied, and the README has a
"Reuse the pattern" section. Four pieces lift straight into other projects:

- **Atomic check-and-decrement with idempotency:** one conditional DynamoDB
  transaction ("enough left?" plus "create this order only once") fits seat
  booking, quotas, coupon redemption or any limited stock.
- **Execution name = business id:** naming each Step Functions execution after
  the order id gives duplicate protection for free.
- **Catch to a recorded outcome:** a business error is caught, written as a
  "blocked" record, and ends in a Fail state, so the console graph shows exactly
  where and why a request stopped.
- **A static site that publishes itself:** a CloudFormation custom resource
  uploads the dashboard and writes its config during `sam deploy`, so the
  website needs no separate deploy step.

### Scope

One flow, end to end: an order comes in, stock is reserved or the order is
blocked, the price is converted, all four stores are updated, a warning is
raised if stock is low, and a receipt is saved. Marketplace calls are mock: the
real Amazon Selling Partner API request is built, and is visible in the
workflow's output for each store, but never sent, and
all products and orders are synthetic demo data. There is no connection to or
endorsement by Amazon.

### What's next

- A live Amazon adapter behind the same interface the mock uses; it needs a
  per-seller token store for the Selling Partner API credentials.
- Sign-in, and each seller's stock and orders kept separate.
- A hold-then-confirm step, so a cart that is never paid gives its units back.

### Try it yourself

You need an AWS account and the AWS SAM CLI. From the repository folder:

```
sam build
sam deploy --guided
```

Open the `DashboardUrl` output and press **Try the demo**. Remove everything
with `sam delete`. Full steps: [Deploy it yourself](https://github.com/anxious956/octoman-lite-hackathon#deploy-it-yourself).

### About this project

OctoMan Lite was built for this challenge during the challenge weekend, as a
standalone, scaled-down take on my own private OctoMan inventory system; a few
modules (currency conversion, the marketplace adapter interface, the DynamoDB
helpers) were adapted from it.

- Live demo: <LIVE_DEMO_URL>
- Source and setup guide: https://github.com/anxious956/octoman-lite-hackathon
- Video: <VIDEO_URL>
- *Optional:* I built this with the help of an AI coding assistant.

---

# PART 2: Longer article (optional)

## Weekend Challenge: OctoMan Lite, one shelf of stock on four Amazon stores without overselling

### The problem

If you sell the same product in several online stores, each store keeps its own
idea of how many you have. When only one unit is left, two customers in two
different countries can both buy it in the same second, and one of those orders
has to be cancelled. That is overselling, and it costs money and seller rating.

### What it does

OctoMan Lite is a small, standalone version of OctoMan, the inventory tool I
am building. It keeps one shared stock level (the "shelf") for four Amazon
stores: the US, the UK, Germany and Türkiye. Every order checks the shelf
first, so the last unit can only be sold once.

The dashboard shows the shelf in the middle and the four stores around it. A
"Try the demo" panel runs four short stories:

- **A customer in Germany buys one.** The shelf drops by one and all four
  stores update, one after another.
- **Sell until stock runs low.** One order takes a product below its warning
  level and a low-stock warning appears.
- **Two customers, one last item.** Two stores order the last unit at the same
  moment. One order is sold, the other is blocked.
- **Someone orders more than we have.** The order is blocked before anything
  is sold.

A six-step strip shows where each order is, or where it was stopped. "Restock
the demo" puts every product back. All products and orders are made-up data.

### How it works

![OctoMan Lite architecture](architecture.png)

1. **Order arrives:** API Gateway (HTTP API) calls a Lambda function that checks
   the order and starts a Step Functions workflow. Its name is the
   order id, so an order cannot run twice.
2. **Check the shelf:** a Lambda function runs one DynamoDB transaction that
   takes the units off the shelf and records the order.
3. **Convert to dollars:** a Lambda function converts the local price to US
   dollars with the European Central Bank's daily reference rates.
4. **Update all 4 stores:** a Step Functions Parallel state pushes the new
   quantity to the four stores at the same time. The marketplace calls are
   mock: the adapter builds the real Amazon Selling Partner API request (a
   Listings Items PATCH) but never sends it, so no seller account or
   credentials are involved.
5. **Low-stock warning:** if stock falls below the product's warning level,
   Step Functions writes a warning straight to DynamoDB, no Lambda needed.
6. **Save receipt:** a Lambda function stores a receipt JSON in S3 and marks
   the order as sold.

### Why it cannot oversell

"Is there enough?" and "take it off the shelf" happen in a single conditional
DynamoDB transaction: decrease the stock only if it is at least the ordered
quantity, and create the order only if it does not exist yet. DynamoDB applies
both or neither, so two orders can never both take the last unit. When the
condition fails, the workflow records the order as blocked and ends in a red
`OversellPrevented` state, so the execution graph shows exactly where it was
stopped.

On the deployed stack: a Germany order for one mug at €11.99 was converted to
$13.25 at the ECB rate, and all four stores were updated after each sale. When
two stores ordered the last print at the same moment, one was sold and one was
blocked. An order for five keychains with three in stock was blocked.

### No pipeline

The whole system is one AWS SAM template. Deploying is `sam build` and then
`sam deploy`. There is no CI/CD and no separate upload step for the website: a
CloudFormation custom resource publishes the dashboard files and writes its
config (the API address) during the deploy, and empties the buckets on
`sam delete`.

### Cost and scale to zero

Everything is pay-per-use: Lambda, Step Functions, DynamoDB on demand, S3,
CloudFront and API Gateway. There are no servers, so an idle stack costs
nothing beyond a few kilobytes of storage. One order costs about $0.0003, most
of it the roughly 11 Step Functions state transitions. Because the demo API is
public, the order route is throttled to one request per second, which caps the
worst case at roughly $25 a day.

### What I learned

- **JSONata in Step Functions removes a lot of plumbing.** With `Assign`
  variables, each step reads `$order` or `$stock` directly instead of passing
  data through `ResultPath` and `OutputPath`. Parsing the error of a blocked
  order became a one-line expression.
- **A reset needs a version guard.** Each stock change carries a version number,
  and a store's quantity is only written if the version is newer. After
  "Restock the demo" the versions restart from the current time in
  milliseconds, so a late update from an order that was still running cannot
  overwrite the fresh stock.
- **A private bucket is enough for a public site.** CloudFront with Origin
  Access Control serves the dashboard while the S3 bucket stays fully private;
  only that distribution can read it.

### Try it

- Live demo: <LIVE_DEMO_URL> (open "Try the demo" in the bottom-right corner)
- Source and setup guide: https://github.com/anxious956/octoman-lite-hackathon
- Video (under 3 minutes): <VIDEO_URL>

The repository has 166 automated tests that need no AWS account, and a deploy guide.

*Optional:* I built this with the help of an AI coding assistant.

---

# Form fields (short versions)

**Problem** (≤ 80 words)

Sellers list the same stock on several marketplaces, and each one keeps its own
count. When one unit is left, two customers in different countries can buy it
at the same moment, and one order has to be cancelled. OctoMan Lite keeps one
shared stock level for four Amazon stores (US, UK, Germany, Türkiye) and checks
it in a single atomic step before any sale, so the last unit can only be sold once.

**Services used** (≤ 80 words)

AWS Lambda (Python 3.12), AWS Step Functions (Standard, JSONata, Parallel
state), Amazon DynamoDB (on-demand, conditional transactions), Amazon API
Gateway (HTTP API with throttling), Amazon S3 (receipts and the dashboard),
Amazon CloudFront (Origin Access Control), AWS CloudFormation custom resource
(publishes the dashboard), Amazon CloudWatch Logs. Deployed with one AWS SAM
template using `sam build` and `sam deploy`, no pipeline.

**Architecture** (≤ 80 words)

An HTTP API sends each order to a Lambda that starts a Step Functions workflow
named after the order. One conditional DynamoDB transaction reserves the stock
or blocks the order. Then a Lambda converts the total to US dollars, a Parallel
state updates four mock Amazon stores at once, a low-stock warning is written
directly to DynamoDB, and a receipt goes to S3. A static dashboard on S3 and
CloudFront reads the same API.

# Screenshots to attach

1. The dashboard with the shared shelf and the four Amazon stores around it,
   right after a sale (all four stores showing the new number).
2. A blocked order: the step strip stopped at "Check the shelf" in red with
   "Nobody was oversold", and the red-edged entry in Live orders.
3. The Step Functions execution graph of a sale, with the four parallel
   "Push Amazon" branches, and of a blocked order ending in `OversellPrevented`.
4. The "Technical details" section with the step-to-AWS-service table.

# Video checklist (for the "demo" field)

- **Under 3 minutes**, showing the build running end to end (`docs/demo_script.md`
  has a 2:30 script).
- Open with the race, as the first action on a freshly restocked demo:
  **Two customers, one last item** (one sold, one blocked), then the red
  **OversellPrevented** stop in the Step Functions execution graph. Then a normal
  sale in Germany and its graph with the four parallel store branches, then the
  low-stock warning, and close on "scales to zero, one `sam deploy`".
- Record in a clean browser window: no bookmarks bar, no other tabs, no
  notifications. **No music.**
- **No third-party trademarks or sites:** do not show GitHub or any other
  third-party site or logo. Note for your decision: the dashboard itself shows
  the word "Amazon" and the store domains (amazon.com, .co.uk, .de, .com.tr) as
  plain text. The challenge is run by AWS, but check whether that counts as a
  "third party trademark" under the Terms; if in doubt, ask before recording.
- **Don't scroll to the page footer** while recording: it names the font,
  flag and icon sets (IBM Plex, flag-icons, Lucide). In **Technical details**,
  show the step-to-service table and the diagram, not the credits.
- Upload it as **public** on YouTube, Vimeo, Facebook Video or Youku.
- Paste the link into the project's **"demo"** field, and replace `<VIDEO_URL>`
  above.
