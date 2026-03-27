"""CLI interface for ETH webprint."""

import getpass
import os
import sys
from pathlib import Path

import click

from .client import AuthError, Client, WebPrintError, resize_pdf

MEDIA_SIZES = {
    "a4": "iso_a4_210x297mm",
    "a3": "iso_a3_297x420mm",
    "letter": "na_letter_8.5x11in",
}


def get_client():
    return Client()


def _cleanup(temp_files):
    for f in temp_files:
        try:
            os.unlink(f)
        except OSError:
            pass


def handle_auth(client):
    """Check session, prompt for login if needed."""
    if client.user and client.check_session():
        return
    click.echo("Session expired or not logged in.")
    username = click.prompt("ETH username")
    password = getpass.getpass("ETH password: ")
    try:
        client.login(username, password)
        click.echo(f"Logged in as {username}")
    except AuthError as e:
        click.echo(f"Login failed: {e}", err=True)
        sys.exit(1)


@click.group()
@click.version_option(package_name="eth-print-cli")
def main():
    """CLI for ETH Zurich's webprint service.

    Upload and print documents from the command line.
    Requires VPN connection to the ETH network.
    """


@main.command()
@click.option("--username", "-u", help="ETH username (prompted if omitted)")
def login(username):
    """Authenticate with ETH credentials."""
    client = get_client()
    if not username:
        username = click.prompt("ETH username")
    password = getpass.getpass("ETH password: ")
    try:
        client.login(username, password)
        click.echo(f"Logged in as {username}")
    except AuthError as e:
        click.echo(f"Login failed: {e}", err=True)
        sys.exit(1)


@main.command()
def logout():
    """End the current session."""
    client = get_client()
    client.logout()
    click.echo("Logged out")


@main.command()
def status():
    """Check session status and account balance."""
    client = get_client()
    if not client.user:
        click.echo("Not logged in")
        sys.exit(1)
    if client.check_session():
        click.echo(f"Logged in as {client.user}")
        try:
            balance = client.get_balance()
            click.echo(f"Balance: {balance}")
        except WebPrintError:
            pass
    else:
        click.echo("Session expired. Run: ethprint login")
        sys.exit(1)


@main.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
def upload(files):
    """Upload files to the webprint inbox."""
    client = get_client()
    handle_auth(client)
    for path in files:
        try:
            client.upload(path)
            click.echo(f"Uploaded: {path}")
        except WebPrintError as e:
            click.echo(f"Failed to upload {path}: {e}", err=True)


@main.command("print")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--copies", "-n", default=1, help="Number of copies")
@click.option("--color", "-c", is_flag=True, help="Print in color (default: B&W)")
@click.option("--simplex", "-s", is_flag=True, help="Single-sided (default: duplex)")
@click.option(
    "--media", "-m",
    type=click.Choice(list(MEDIA_SIZES.keys()), case_sensitive=False),
    default="a4",
    help="Paper size",
)
@click.option("--pages", "-p", default="", help="Page range (e.g. 1-3,5)")
@click.option("--printer", default="CARD-STUD", help="Printer name")
def print_cmd(files, copies, color, simplex, media, pages, printer):
    """Upload and print files.

    If FILES are given, uploads them first then prints.
    If no files are given, prints whatever is already in the inbox.
    """
    client = get_client()
    handle_auth(client)

    media_value = MEDIA_SIZES[media.lower()]
    temp_files = []

    for path in files:
        try:
            upload_path = path
            if path.lower().endswith(".pdf"):
                resized, tmp, source_size = resize_pdf(path, media_value)
                if tmp:
                    temp_files.append(tmp)
                    src_name = Path(path).name
                    click.echo(
                        f"Warning: {src_name} is {source_size}, "
                        f"resizing to {media.upper()}"
                    )
                    upload_path = resized
            client.upload(upload_path)
            click.echo(f"Uploaded: {Path(path).name}")
        except WebPrintError as e:
            click.echo(f"Failed to upload {path}: {e}", err=True)
            _cleanup(temp_files)
            sys.exit(1)
    try:
        msg = client.print_job(
            printer=printer,
            copies=copies,
            color=color,
            duplex=not simplex,
            media=media_value,
            pages=pages,
        )
        click.echo(f"Print job submitted: {msg}")
    except WebPrintError as e:
        click.echo(f"Print failed: {e}", err=True)
        _cleanup(temp_files)
        sys.exit(1)

    _cleanup(temp_files)


@main.command()
def clear():
    """Delete all documents from the inbox."""
    client = get_client()
    handle_auth(client)
    if client.clear_inbox():
        click.echo("Inbox cleared")
    else:
        click.echo("No documents to clear")


if __name__ == "__main__":
    main()
