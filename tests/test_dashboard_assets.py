"""Static checks on the dashboard: self-hosted, licensed, text-only rendering, size budget."""

import re
import xml.dom.minidom
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
ASSETS = DASHBOARD / "assets"
CODE_FILES = [DASHBOARD / "index.html", ASSETS / "app.css", ASSETS / "app.js", ASSETS / "derive.js"]

# The only absolute URLs allowed in page code: SVG namespaces, the AWS console link
# builder (used only when execution links are configured) and the public repository.
ALLOWED_URL_PREFIXES = (
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xlink",
    "https://github.com/anxious956/octoman-lite-hackathon",
)
# The console link is assembled at runtime as "https://" + region + ".console.aws.amazon.com/..."
# so it never appears as a complete literal URL; this pattern finds every literal one.
_URL_RE = re.compile(r"""https?://[^\s"'`)<>]+""")
MAX_SITE_BYTES = 700 * 1024


def _site_files():
    for p in DASHBOARD.rglob("*"):
        if p.is_file() and p.name != "deployer.py" and "__pycache__" not in p.parts and not p.name.startswith("."):
            yield p


@pytest.mark.parametrize("path", CODE_FILES, ids=lambda p: p.name)
def test_code_files_exist(path):
    assert path.is_file()


@pytest.mark.parametrize("path", CODE_FILES, ids=lambda p: p.name)
def test_no_external_runtime_urls(path):
    text = path.read_text(encoding="utf-8")
    for url in _URL_RE.findall(text):
        assert url.startswith(ALLOWED_URL_PREFIXES), f"external URL in {path.name}: {url}"
    # Protocol-relative URLs (//host/...) in src/href would also load from another origin.
    assert not re.search(r"""(?:src|href)\s*=\s*["']//""", text)


@pytest.mark.parametrize("path", CODE_FILES, ids=lambda p: p.name)
def test_api_data_is_never_parsed_as_html(path):
    text = path.read_text(encoding="utf-8")
    assert "innerHTML" not in text and "outerHTML" not in text and "insertAdjacentHTML" not in text
    assert "document.write" not in text and "eval(" not in text


def test_index_loads_config_then_one_module():
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    assert '<script src="config.js"></script>' in html
    assert '<script type="module" src="assets/app.js"></script>' in html


def test_every_asset_is_credited():
    credits = (ASSETS / "CREDITS.md").read_text(encoding="utf-8")
    for p in list((ASSETS / "img").rglob("*.*")) + list((ASSETS / "fonts").glob("*.woff2")):
        rel = p.relative_to(ASSETS).as_posix()
        assert f"`{rel}`" in credits, f"{rel} is not listed in CREDITS.md"


def test_every_seed_product_has_an_image():
    from shared.seed_data import PRODUCTS
    skus = [row[0] for row in PRODUCTS]
    assert len(skus) == 15
    for sku in skus:
        assert (ASSETS / "img" / "products" / f"{sku.lower()}.svg").is_file(), sku


@pytest.mark.parametrize("path", sorted((ASSETS / "img").rglob("*.svg")), ids=lambda p: p.name)
def test_svgs_are_valid_and_inert(path):
    text = path.read_text(encoding="utf-8")
    xml.dom.minidom.parseString(text)
    assert not re.search(r"<script|\son[a-z]+=|href=\"https?:", text, re.I)


def test_licence_texts_are_shipped():
    names = {p.name for p in (ASSETS / "licenses").iterdir()}
    assert {"OFL-IBM-Plex-Sans.txt", "OFL-IBM-Plex-Mono.txt", "MIT-flag-icons.txt", "ISC-lucide.txt"} <= names


def test_total_site_size_is_under_budget():
    total = sum(p.stat().st_size for p in _site_files())
    assert total <= MAX_SITE_BYTES, f"{total} bytes"
