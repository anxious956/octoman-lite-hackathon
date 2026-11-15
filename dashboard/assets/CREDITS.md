# Asset credits

Every file under `dashboard/assets/` that was not written for this project is listed
here with its source and licence. All of them are downloaded into the repository and
served from the dashboard's own origin; nothing is loaded from a third-party server at
runtime. Full licence texts are in `licenses/`.

## Fonts

| File | Source | Author | Licence |
|---|---|---|---|
| `fonts/ibm-plex-sans-latin-400-normal.woff2` | https://www.npmjs.com/package/@fontsource/ibm-plex-sans (v5.1.0, Latin subset) | IBM Corp. | SIL Open Font License 1.1 (`licenses/OFL-IBM-Plex-Sans.txt`) |
| `fonts/ibm-plex-sans-latin-500-normal.woff2` | same | IBM Corp. | SIL OFL 1.1 |
| `fonts/ibm-plex-sans-latin-600-normal.woff2` | same | IBM Corp. | SIL OFL 1.1 |
| `fonts/ibm-plex-mono-latin-400-normal.woff2` | https://www.npmjs.com/package/@fontsource/ibm-plex-mono (v5.1.0, Latin subset) | IBM Corp. | SIL Open Font License 1.1 (`licenses/OFL-IBM-Plex-Mono.txt`) |
| `fonts/ibm-plex-mono-latin-500-normal.woff2` | same | IBM Corp. | SIL OFL 1.1 |
| `fonts/ibm-plex-mono-latin-ext-400-normal.woff2` | same package, Latin Extended subset (used only for the ₺ sign) | IBM Corp. | SIL OFL 1.1 |
| `fonts/ibm-plex-mono-latin-ext-500-normal.woff2` | same | IBM Corp. | SIL OFL 1.1 |

## Flags

| File | Source | Author | Licence |
|---|---|---|---|
| `img/flags/us.svg` | https://github.com/lipis/flag-icons (npm `flag-icons` v7.2.3, `flags/4x3/`) | Panayiotis Lipiridis and contributors | MIT (`licenses/MIT-flag-icons.txt`) |
| `img/flags/gb.svg` | same | same | MIT |
| `img/flags/de.svg` | same | same | MIT |
| `img/flags/tr.svg` | same | same | MIT |

## Icons

Inlined as an SVG sprite in `index.html` (`<symbol id="i-...">`): `shopping-bag`,
`package`, `circle-dollar-sign`, `store`, `triangle-alert`, `receipt`, `refresh-cw`,
`sun`, `moon`, `chevron-down`, `octagon-x`, `check`, `users`, `ban`, `plus`, `minus`,
`external-link`, `circle-help`.

| Source | Author | Licence |
|---|---|---|
| https://lucide.dev (npm `lucide-static` v0.460.0) | Lucide contributors | ISC (`licenses/ISC-lucide.txt`) |

## OctoMan brand

| File | What it is |
|---|---|
| `img/logo.png` | The OctoMan octopus mascot, owned by the OctoMan project author; cropped and resized from the OctoMan brand artwork |
| `img/favicon.png` | Same mascot at 48 px, used as the browser tab icon |

## AWS service icons

Used in the architecture diagram under "Technical details", from the official
[AWS Architecture Icons](https://aws.amazon.com/architecture/icons/) set. AWS states
that customers and partners may use these icons to create architecture diagrams; they
are used here unmodified (no recolouring, cropping or stretching), only scaled down to
96 px PNG. Five come from the copies in `docs/aws-icons/`; the S3 icon was supplied
separately as a PNG from the AWS Architecture Icons set. No package version is claimed
for either. The icons belong to Amazon Web Services
and are not covered by this repository's licence.

| File | Icon |
|---|---|
| `img/aws/cloudfront.png` | Amazon CloudFront, service icon |
| `img/aws/s3.png` | Amazon S3, service icon |
| `img/aws/api-gateway.png` | Amazon API Gateway, service icon |
| `img/aws/lambda.png` | AWS Lambda, service icon |
| `img/aws/step-functions.png` | AWS Step Functions, service icon |
| `img/aws/dynamodb.png` | Amazon DynamoDB, service icon |

## Product photos

Photos from [Unsplash](https://unsplash.com), used under the
[Unsplash License](https://unsplash.com/license): free to use, including commercially,
no permission needed. Credit is not required by the licence but is given here anyway.
All 15 are standard Unsplash photos, none from the paid Unsplash+ collection.
The licence covers the photographs only, not any brand, product design or artwork shown
in them, so photos were picked to show plain, unbranded items with no logos or readable
text. Each was cropped square and resized to 192 px WebP. They stand in for the 15
synthetic seed products; they are stock photos, not photos of real OctoMan products.

| File | Stands in for | Photographer | Source |
|---|---|---|---|
| `img/products/octo-mug-001.webp` | White Ceramic Mug | [@mediamodifier](https://unsplash.com/@mediamodifier) | [photo](https://unsplash.com/photos/a-white-coffee-mug-xf38DdLyBvI) |
| `img/products/octo-tee-002.webp` | Classic White T-Shirt | [@mockupbee](https://unsplash.com/@mockupbee) | [photo](https://unsplash.com/photos/a-white-shirt-on-a-white-background-4rUYuwJ2vGw) |
| `img/products/octo-plush-003.webp` | Teddy Bear Plush, Small | [@izamarques](https://unsplash.com/@izamarques) | [photo](https://unsplash.com/photos/a-stuffed-bear-with-a-green-bow-8xpfM2QHJSE) |
| `img/products/octo-lamp-004.webp` | Pink Desk Lamp | [@oscaresquivel](https://unsplash.com/@oscaresquivel) | [photo](https://unsplash.com/photos/red-and-silver-table-lamp-at5-1nW3UCY) |
| `img/products/octo-sock-005.webp` | Patterned Crew Socks | [@johnn21](https://unsplash.com/@johnn21) | [photo](https://unsplash.com/photos/white-red-and-blue-socks-zOFQ8v3YBBU) |
| `img/products/octo-print-006.webp` | Cactus Art Print A4 | [@joshhemsley](https://unsplash.com/@joshhemsley) | [photo](https://unsplash.com/photos/painting-of-cactus-plant-mL8cnlSC3oo) |
| `img/products/octo-case-007.webp` | Reef Blue Phone Case | [@jascentleung](https://unsplash.com/@jascentleung) | [photo](https://unsplash.com/photos/a-cell-phone-sitting-on-top-of-a-blue-cloth-CubSQS4iYEE) |
| `img/products/octo-bottle-008.webp` | Insulated Water Bottle | [@joanofarts](https://unsplash.com/@joanofarts) | [photo](https://unsplash.com/photos/green-bottle-on-white-table-reEySFadyJQ) |
| `img/products/octo-key-009.webp` | Heart Keychain | [@erikalowe](https://unsplash.com/@erikalowe) | [photo](https://unsplash.com/photos/a-metal-heart-shaped-keychain-hanging-from-a-chain-dKRNe47ror4) |
| `img/products/octo-puzzle-010.webp` | Blue Jigsaw Puzzle, 500 Pieces | [@ttepavac](https://unsplash.com/@ttepavac) | [photo](https://unsplash.com/photos/a-piece-of-a-puzzle-with-a-missing-piece-cWMhxNmQVq0) |
| `img/products/octo-tote-011.webp` | Canvas Tote Bag | [@brandomakesbranding](https://unsplash.com/@brandomakesbranding) | [photo](https://unsplash.com/photos/white-reusable-bag-on-gray-surface-smTDI-z1rlY) |
| `img/products/octo-cap-012.webp` | White Baseball Cap | [@mediamodifier](https://unsplash.com/@mediamodifier) | [photo](https://unsplash.com/photos/white-baseball-cap-on-white-surface-t8HiP3e5abg) |
| `img/products/octo-candle-013.webp` | Sea Salt Candle | [@oneshotespresso](https://unsplash.com/@oneshotespresso) | [photo](https://unsplash.com/photos/lighted-candle-66qsl7ia2cE) |
| `img/products/octo-note-014.webp` | Blank Notebook | [@enginakyurt](https://unsplash.com/@enginakyurt) | [photo](https://unsplash.com/photos/notebook-and-pen-on-white-IZj7vckPGiw) |
| `img/products/octo-stick-015.webp` | Space Sticker Pack | [@mkmasdos](https://unsplash.com/@mkmasdos) | [photo](https://unsplash.com/photos/a-bunch-of-stickers-on-a-yellow-background-zzHJ3VSKrZg) |

Edits: two photos had a small printed mark, painted out with the plain material next
to it: a round brand mark in the corner of the tote bag (`octo-tote-011.webp`) and a
line of tiny maker's text near the bottom edge of the phone case (`octo-case-007.webp`).
No other photo was retouched.
