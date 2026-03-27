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

## How it works

ETH's webprint runs [SavaPage](https://www.savapage.org/). This tool talks to the same internal API that the web interface uses. Files are uploaded to your webprint inbox and print jobs are submitted to the CARD-STUD printer queue, which you can release at any student printer on campus.

## Support

If you find this useful, [buy me a coffee](https://buymeacoffee.com/swanson).

<img src="assets/bmc_qr.png" alt="Buy Me a Coffee QR" width="200">
