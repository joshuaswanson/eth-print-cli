# eth-print-cli

CLI tool for [ETH Zurich's webprint service](https://webprint.ethz.ch). Upload and print documents from your terminal instead of the web interface.

## Requirements

- Python 3.9+
- Connection to ETH network (VPN or on-campus)
- ETH student account

## Installation

```bash
git clone https://github.com/joshuaswanson/eth-print-cli.git
cd eth-print-cli
pip install .
playwright install chromium
```

## Usage

### Login

```bash
ethprint login
ethprint login -u jdoe
```

Your session is saved locally so you don't need to log in every time. Sessions expire after ~24 hours of inactivity.

### Print a file

```bash
ethprint print document.pdf
ethprint print slides.pdf --color
ethprint print essay.pdf --simplex --copies 2
ethprint print poster.pdf --media a3
```

### Upload without printing

```bash
ethprint upload file1.pdf file2.pdf
```

Then print from the web UI or the CLI.

### Other commands

```bash
ethprint status          # check login status and balance
ethprint clear           # delete all files from inbox
ethprint logout          # end session
```

### Print options

| Flag            | Description                                    |
| --------------- | ---------------------------------------------- |
| `--copies, -n`  | Number of copies (default: 1)                  |
| `--color, -c`   | Print in color (default: black & white)        |
| `--simplex, -s` | Single-sided printing (default: duplex)        |
| `--media, -m`   | Paper size: `a4`, `a3`, `letter` (default: a4) |
| `--pages, -p`   | Page range, e.g. `1-3,5`                       |
| `--printer`     | Printer name (default: CARD-STUD)              |

## Supported file types

PDF, HTML, TXT, PS, BMP, GIF, JPEG, PNG, SVG, TIFF

## Why this exists

ETH's webprint runs [SavaPage](https://www.savapage.org/), which has a REST API and IPP support for exactly this kind of thing. But ETH has disabled both for student accounts. The Internet Printer settings page just says "No URL available" and the REST API returns 401 regardless of credentials.

So this tool does it the hard way: it uses a headless browser to log in (because SavaPage needs a Wicket-initialized server session that can't be created with plain HTTP requests), then talks to the same internal API endpoints that the web UI uses.

PDFs are also automatically resized to match your target paper size before uploading. If you try to print an A3 PDF on A4, it gets scaled down transparently instead of printing on the wrong paper size or getting cropped.

## Support

If you find this useful, [buy me a coffee](https://buymeacoffee.com/swanson).

<img src="assets/bmc_qr.png" alt="Buy Me a Coffee QR" width="200">
