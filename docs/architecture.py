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
MUTED = "#7d8998"
ACCENT = "#e7157b"

graph_attr = {
    "bgcolor": BG,
    "fontcolor": FG,
    "fontname": "Helvetica",
    "fontsize": "22",
    "pad": "0.6",
    "nodesep": "0.55",
    "ranksep": "1.1",
    "splines": "spline",
    "newrank": "true",
    "labelloc": "t",
}
node_attr = {"fontcolor": FG, "fontname": "Helvetica", "fontsize": "12"}
edge_attr = {"color": MUTED, "fontcolor": FG, "fontname": "Helvetica", "fontsize": "10"}


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


def call(label=""):
    return Edge(label=label, color=FG, style="solid")


def data(label=""):
    return Edge(label=label, color=MUTED, style="dashed")


def flow(label=""):
    return Edge(label=label, color=ACCENT, style="bold")


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
    ingest = Lambda("IngestOrder")
    query = Lambda("QueryApi")

    with cluster("Step Functions: order flow (Standard, JSONata)", color=ACCENT):
        sfn = StepFunctions("Execution\nname = order_id")
        reserve = Lambda("ReserveStock")
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
        fx = Lambda("ConvertToUSD")
        push = Lambda("PushToMarketplaces\nParallel: eBay US · GB · DE · TR")
        is_low = Node(
            "IsStockLow?",
            shape="diamond",
            style="filled",
            fillcolor="#ffffff",
            color=ACCENT,
            fontcolor=FG,
            width="1.6",
            height="1.0",
            labelloc="c",
        )
        alert = DynamodbItem("RaiseLowStockAlert\ndirect putItem")
        finalize = Lambda("FinalizeOrder")

    with cluster("Amazon DynamoDB (on-demand)"):
        products = Dynamodb("products")
        orders = Dynamodb("orders")
        alerts = Dynamodb("alerts")

    receipts = S3Bucket("S3\nreceipts bucket")

    with cluster("External"):
        ebay = InternetAlt1("eBay Sell Inventory API\nrequest built, not sent")
        ecb = InternetAlt1("ECB daily\nreference rates")

    # Client traffic
    dashboard >> data("loads from") >> cdn >> dash_bucket
    dashboard >> call("GET /products /orders /alerts\nPOST /orders") >> api
    webhook >> call("POST /orders") >> api
    api >> call() >> ingest
    api >> call() >> query
    ingest >> flow("StartExecution") >> sfn

    # State machine
    sfn >> flow() >> reserve
    reserve >> flow("ok") >> fx
    reserve >> Edge(label="InsufficientStock /\nUnknownSku", color="#d13212", style="bold") >> reject
    reject >> Edge(color="#d13212", style="bold") >> oversell
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
