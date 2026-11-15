"""Render the architecture diagram with official AWS service icons.

Every node sits on a fixed grid and every connector is routed by hand on its
own lane, so the layout stays tidy. Writes:

    docs/architecture.svg   self-contained (icons embedded)
    docs/architecture.png   2x raster, rendered with Playwright + Chromium

Usage:
    python docs/architecture.py            # SVG + PNG
    python docs/architecture.py --svg-only # no browser needed

Icons in docs/aws-icons/ are from the AWS Architecture Icons set.
"""

import base64
import subprocess
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICONS = HERE / "aws-icons"
SVG_OUT = HERE / "architecture.svg"
PNG_OUT = HERE / "architecture.png"

W, H = 2090, 1010
ICON = 64
FONT = "Helvetica, Arial, sans-serif"

INK = "#232f3e"
GREY = "#545b64"
PINK = "#e7157b"
RED = "#d13212"
PANEL = "#f8f9fa"
BORDER = "#aab7b8"

STYLES = {
    # name: (colour, width, dash)
    "call": (INK, 2.0, None),
    "flow": (PINK, 2.6, None),
    "fail": (RED, 2.6, None),
    "data": (GREY, 1.8, "7 5"),
}

# ---------------------------------------------------------------- nodes
# key: (x, y, icon, label lines, label side)
NODES = {
    "dashboard": (115, 130, "client", ["Dashboard", "static HTML + JS"], "below"),
    "webhook": (115, 450, "traditional-server", ["Marketplace webhook", "or curl"], "below"),
    "cloudfront": (330, 130, "cloudfront", ["CloudFront", "HTTPS, OAC"], "below"),
    "dash_bucket": (520, 130, "simple-storage-service-s3-bucket", ["S3", "dashboard bucket"], "below"),
    "api": (330, 330, "api-gateway", ["API Gateway", "HTTP API, throttled"], "below"),
    "query": (690, 330, "lambda", ["QueryApi"], "below"),
    "ingest": (520, 470, "lambda", ["IngestOrder"], "below"),
    "start": (720, 470, "step-functions", ["Execution", "name = order_id"], "below"),
    "reserve": (895, 470, "lambda", ["ReserveStock"], "below"),
    "fx": (1070, 470, "lambda", ["ConvertToUSD"], "below"),
    "push": (1260, 470, "lambda", ["PushToMarketplaces", "Parallel: eBay US · GB · DE · TR"], "below"),
    "alert": (1610, 470, "dynamodb-item", ["RaiseLowStockAlert", "direct putItem"], "below"),
    "finalize": (1790, 470, "lambda", ["FinalizeOrder"], "below"),
    "reject": (895, 620, "dynamodb-item", ["RecordRejection", "direct putItem"], "below"),
    "receipts": (1990, 470, "simple-storage-service-s3-bucket", ["S3", "receipts bucket"], "below"),
    "orders": (1000, 230, "dynamodb", ["orders"], "right"),
    "products": (1260, 230, "dynamodb", ["products"], "right"),
    "alerts": (1610, 230, "dynamodb", ["alerts"], "right"),
    "ecb": (1070, 905, "internet-alt1", ["ECB daily", "reference rates"], "below"),
    "ebay": (1260, 905, "internet-alt1", ["eBay Sell Inventory API", "request built, not sent"], "below"),
}
DIAMOND = (1440, 470, 110, 64, "IsStockLow?")
FAIL_PILL = (895, 735, 156, 28, "OversellPrevented")

# ---------------------------------------------------------------- groups
# (x0, y0, x1, y1, title, title x, title y, anchor, border colour)
GROUPS = [
    (40, 60, 190, 515, "Client", 52, 80, "start", BORDER),
    (630, 400, 1870, 795, "AWS Step Functions: order flow (Standard, JSONata)", 645, 782, "start", PINK),
    (940, 150, 1720, 290, "Amazon DynamoDB (on-demand)", 1435, 175, "middle", BORDER),
    (990, 830, 1350, 985, "External (not AWS)", 1165, 852, "middle", BORDER),
]

# ---------------------------------------------------------------- edges
# (style, [points], label lines, label x, label y, anchor)
EDGES = [
    # client traffic
    ("data", [(147, 130), (298, 130)], ["loads from"], 222, 121, "middle"),
    ("call", [(362, 130), (488, 130)], [], 0, 0, ""),
    ("call", [(115, 200), (115, 315), (298, 315)], ["GET /products /orders /alerts", "POST /orders"], 206, 284, "middle"),
    ("call", [(147, 450), (240, 450), (240, 345), (298, 345)], ["POST /orders"], 192, 441, "middle"),
    ("call", [(362, 330), (658, 330)], ["GET"], 510, 321, "middle"),
    ("call", [(330, 400), (330, 470), (488, 470)], ["POST /orders"], 410, 461, "middle"),
    ("flow", [(552, 470), (688, 470)], ["StartExecution"], 620, 461, "middle"),
    # order flow
    ("flow", [(752, 470), (863, 470)], [], 0, 0, ""),
    ("flow", [(927, 470), (1038, 470)], ["ok"], 982, 461, "middle"),
    ("flow", [(1102, 470), (1228, 470)], [], 0, 0, ""),
    ("flow", [(1292, 470), (1385, 470)], [], 0, 0, ""),
    ("flow", [(1495, 470), (1578, 470)], ["yes"], 1536, 461, "middle"),
    ("flow", [(1642, 470), (1758, 470)], [], 0, 0, ""),
    ("flow", [(1440, 502), (1440, 585), (1790, 585), (1790, 530)], ["no"], 1615, 576, "middle"),
    ("fail", [(895, 526), (895, 588)], ["InsufficientStock /", "UnknownSku"], 905, 552, "start"),
    ("fail", [(895, 690), (895, 721)], [], 0, 0, ""),
    # data access
    ("data", [(880, 438), (880, 310), (990, 310), (990, 262)], ["create once"], 935, 301, "middle"),
    ("data", [(910, 438), (910, 340), (1245, 340), (1245, 262)], ["conditional transaction"], 1078, 331, "middle"),
    ("data", [(863, 620), (800, 620), (800, 230), (968, 230)], ["putItem"], 884, 221, "middle"),
    ("data", [(1275, 438), (1275, 262)], ["listing copy"], 1284, 305, "start"),
    ("data", [(1610, 438), (1610, 262)], ["putItem"], 1619, 305, "start"),
    ("data", [(1790, 438), (1790, 55), (1012, 55), (1012, 198)], ["COMPLETED"], 1400, 46, "middle"),
    ("data", [(1822, 470), (1958, 470)], ["receipt"], 1890, 461, "middle"),
    ("data", [(1070, 532), (1070, 873)], ["HTTPS"], 1079, 812, "start"),
    ("data", [(1260, 545), (1260, 873)], ["mock adapter"], 1269, 812, "start"),
    # QueryApi read bus
    ("data", [(690, 298), (690, 95), (990, 95), (990, 198)], ["read"], 840, 86, "middle"),
    ("data", [(690, 298), (690, 95), (1260, 95), (1260, 198)], [], 0, 0, ""),
    ("data", [(690, 298), (690, 95), (1610, 95), (1610, 198)], [], 0, 0, ""),
]

LEGEND = [
    ("flow", "order flow (Step Functions)"),
    ("call", "HTTP call"),
    ("data", "data access"),
    ("fail", "oversell rejected"),
]


def icon_href(name):
    data = base64.b64encode((ICONS / f"{name}.png").read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def text(x, y, lines, size=12, anchor="middle", weight="normal", fill=INK, halo=False, step=14):
    extra = ' stroke="#ffffff" stroke-width="4" stroke-linejoin="round" paint-order="stroke"' if halo else ""
    out = []
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{x}" y="{y + i * step}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}"{extra}>{escape(line)}</text>'
        )
    return "\n".join(out)


def render_svg():
    s = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}">',
        "<defs>",
    ]
    for name, (colour, _, _) in STYLES.items():
        s.append(
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" '
            f'markerWidth="11" markerHeight="11" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{colour}"/></marker>'
        )
    s.append("</defs>")
    s.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    s.append(text(40, 34, ["Octoman Lite: order flow on AWS"], size=22, anchor="start", weight="bold"))

    for x0, y0, x1, y1, title, tx, ty, anchor, colour in GROUPS:
        s.append(
            f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="10" '
            f'fill="{PANEL}" stroke="{colour}" stroke-width="1.5"/>'
        )
        s.append(text(tx, ty, [title], size=13, anchor=anchor, weight="bold"))

    for style, pts, *_ in EDGES:
        colour, width, dash = STYLES[style]
        d = " ".join(f"{x},{y}" for x, y in pts)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        s.append(
            f'<polyline points="{d}" fill="none" stroke="{colour}" stroke-width="{width}"{dash_attr} '
            f'stroke-linejoin="round" marker-end="url(#arrow-{style})"/>'
        )

    for x, y, icon, label, side in NODES.values():
        s.append(
            f'<image href="{icon_href(icon)}" x="{x - ICON / 2}" y="{y - ICON / 2}" '
            f'width="{ICON}" height="{ICON}"/>'
        )
        if side == "below":
            s.append(text(x, y + ICON / 2 + 16, label))
        else:
            s.append(text(x + ICON / 2 + 8, y + 4, label, size=13, anchor="start", weight="bold"))

    x, y, w, h, label = DIAMOND
    s.append(
        f'<polygon points="{x},{y - h / 2} {x + w / 2},{y} {x},{y + h / 2} {x - w / 2},{y}" '
        f'fill="#ffffff" stroke="{PINK}" stroke-width="2"/>'
    )
    s.append(text(x, y + 4, [label], size=11, weight="bold"))

    x, y, w, h, label = FAIL_PILL
    s.append(f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" rx="{h / 2}" fill="{RED}"/>')
    s.append(text(x, y + 4, [label], size=12, weight="bold", fill="#ffffff"))

    for _, _, label, lx, ly, anchor in EDGES:
        if label:
            s.append(text(lx, ly - (len(label) - 1) * 13, label, size=11, anchor=anchor, weight="bold", halo=True, step=13))

    lx, ly = 40, 860
    s.append(text(lx, ly, ["Legend"], size=13, anchor="start", weight="bold"))
    for i, (style, label) in enumerate(LEGEND):
        colour, width, dash = STYLES[style]
        y = ly + 24 + i * 24
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        s.append(
            f'<line x1="{lx}" y1="{y - 4}" x2="{lx + 50}" y2="{y - 4}" stroke="{colour}" '
            f'stroke-width="{width}"{dash_attr} marker-end="url(#arrow-{style})"/>'
        )
        s.append(text(lx + 62, y, [label], size=12, anchor="start"))

    s.append("</svg>")
    return "\n".join(s)


def render_png():
    script = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage({{ viewport: {{ width: {W}, height: {H} }}, deviceScaleFactor: 2 }});
  await page.goto('file://{SVG_OUT}');
  await page.screenshot({{ path: '{PNG_OUT}', clip: {{ x: 0, y: 0, width: {W}, height: {H} }} }});
  await browser.close();
}})();
"""
    subprocess.run(["node", "-e", script], check=True)


if __name__ == "__main__":
    SVG_OUT.write_text(render_svg(), encoding="utf-8")
    print(f"wrote {SVG_OUT}")
    if "--svg-only" not in sys.argv:
        render_png()
        print(f"wrote {PNG_OUT}")
