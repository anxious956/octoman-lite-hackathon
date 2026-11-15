"""Render docs/architecture.png with official AWS service icons.

Requires Graphviz (`dot`) and the `diagrams` package:

    pip install diagrams
    python docs/architecture.py
"""

from pathlib import Path

from diagrams import Cluster, Diagram, Edge, Node
from diagrams.aws.compute import Lambda
from diagrams.aws.database import Dynamodb, DynamodbItem
from diagrams.aws.general import Client, InternetAlt1, TraditionalServer
from diagrams.aws.integration import StepFunctions
from diagrams.aws.network import APIGateway, CloudFront
from diagrams.aws.storage import SimpleStorageServiceS3Bucket as S3Bucket

OUT = Path(__file__).with_name("architecture")

BG = "#ffffff"
FG = "#232f3e"
MUTED = "#545b64"
ACCENT = "#e7157b"

graph_attr = {
    "bgcolor": BG,
    "fontcolor": FG,
    "fontname": "Helvetica",
    "fontsize": "22",
    "pad": "0.6",
    "nodesep": "1.0",
    "ranksep": "1.9",
    "splines": "ortho",
    "forcelabels": "true",
    "newrank": "true",
    "labelloc": "t",
}
node_attr = {"fontcolor": FG, "fontname": "Helvetica", "fontsize": "12"}
edge_attr = {
    "color": MUTED,
    "fontcolor": FG,
    "fontname": "Helvetica-Bold",
    "fontsize": "11",
    "penwidth": "1.8",
    "arrowsize": "0.9",
}


def cluster(label, color="#aab7b8", fill="#f8f9fa"):
    return Cluster(
        label,
        graph_attr={
            "bgcolor": fill,
            "pencolor": color,
            "fontcolor": FG,
            "fontname": "Helvetica-Bold",
            "fontsize": "14",
            "style": "rounded",
            "margin": "18",
        },
    )


# Orthogonal routing ignores ordinary edge labels, so labels go in xlabel.
def call(label="", **attrs):
    return Edge(xlabel=label, color=FG, style="solid", penwidth="2", **attrs)


def data(label="", **attrs):
    return Edge(xlabel=label, color=MUTED, style="dashed", penwidth="1.8", **attrs)


def flow(label=""):
    return Edge(xlabel=label, color=ACCENT, style="solid", penwidth="2.6")


def fail(label=""):
    return Edge(xlabel=label, color="#d13212", style="solid", penwidth="2.6")


with Diagram(
    "Octoman Lite: order flow on AWS",
    filename=str(OUT),
    outformat="png",
    direction="LR",
    show=False,
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    with cluster("Client"):
        dashboard = Client("Dashboard\nstatic HTML + JS")
        webhook = TraditionalServer("Marketplace webhook\nor curl")

    cdn = CloudFront("CloudFront\nHTTPS, OAC")
    dash_bucket = S3Bucket("S3\ndashboard bucket")

    api = APIGateway("API Gateway\nHTTP API, throttled")
    ingest = Lambda("IngestOrder", group="main")
    query = Lambda("QueryApi")

    with cluster("Step Functions: order flow (Standard, JSONata)", color=ACCENT):
        sfn = StepFunctions("StartExecution\nname = order_id", group="main")
        reserve = Lambda("ReserveStock", group="main")
        reject = DynamodbItem("RecordRejection\ndirect putItem")
        oversell = Node(
            "OversellPrevented",
            shape="box",
            style="rounded,filled",
            fillcolor="#d13212",
            color="#d13212",
            fontcolor="white",
            width="1.8",
            height="0.5",
            labelloc="c",
        )
        fx = Lambda("ConvertToUSD", group="main")
        push = Lambda("PushToMarketplaces\nParallel: eBay US · GB · DE · TR", group="main")
        is_low = Node(
            "IsStockLow?",
            shape="diamond",
            style="filled",
            fillcolor="#ffffff",
            color=ACCENT,
            fontcolor=FG,
            width="1.6",
            height="1.0",
            group="main",
            labelloc="c",
        )
        alert = DynamodbItem("RaiseLowStockAlert\ndirect putItem", group="main")
        finalize = Lambda("FinalizeOrder", group="main")

    with cluster("Amazon DynamoDB (on-demand)"):
        products = Dynamodb("products")
        orders = Dynamodb("orders")
        alerts = Dynamodb("alerts")

    receipts = S3Bucket("S3\nreceipts bucket")

    with cluster("External"):
        ebay = InternetAlt1("eBay Sell Inventory API\nrequest built, not sent")
        ecb = InternetAlt1("ECB daily\nreference rates")

    # Client traffic
    dashboard >> data("loads from", minlen="2") >> cdn >> dash_bucket
    dashboard >> call("GET /products /orders /alerts\nPOST /orders", minlen="2") >> api
    webhook >> call("POST /orders", minlen="2") >> api
    api >> call() >> ingest
    api >> call() >> query
    ingest >> flow() >> sfn

    # State machine
    sfn >> flow() >> reserve
    reserve >> flow("ok") >> fx
    reserve >> fail("InsufficientStock /\nUnknownSku") >> reject
    reject >> fail() >> oversell
    fx >> flow() >> push >> flow() >> is_low
    is_low >> flow("yes") >> alert >> flow() >> finalize
    is_low >> flow("no") >> finalize

    # Data access
    reserve >> data("conditional transaction") >> products
    reserve >> data("create once") >> orders
    reject >> data("putItem") >> orders
    fx >> data("HTTPS") >> ecb
    push >> data("listing copy") >> products
    push >> data("mock adapter") >> ebay
    alert >> data("putItem") >> alerts
    finalize >> data("receipt") >> receipts
    finalize >> data("COMPLETED") >> orders
    query >> data() >> [products, orders, alerts]
