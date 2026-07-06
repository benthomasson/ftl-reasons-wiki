import http.server
import functools
import os

import click

from .generator import generate_site


@click.group()
def cli():
    """Static wiki generator for EEM belief networks."""
    pass


@cli.command()
@click.option("--input", "-i", "input_path", required=True,
              type=click.Path(exists=True), help="Path to network.json")
@click.option("--output", "-o", "output_dir", default="dist",
              help="Output directory (default: dist)")
@click.option("--base-url", default="",
              help="Base URL for sitemap and canonical links")
@click.option("--project-name", default=None,
              help="Override project name from network.json meta")
def build(input_path, output_dir, base_url, project_name):
    """Generate static wiki from a network.json export."""
    stats = generate_site(input_path, output_dir,
                          base_url=base_url, project_name=project_name)
    click.echo(f"Generated {stats['beliefs']} belief pages, "
               f"{stats['topics']} topic pages")
    click.echo(f"Output: {output_dir}/")


@cli.command()
@click.argument("directory", default="dist")
@click.option("--port", "-p", default=8000, help="Port (default: 8000)")
def serve(directory, port):
    """Serve the generated site locally for preview."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=directory)
    with http.server.HTTPServer(("", port), handler) as httpd:
        click.echo(f"Serving {directory}/ at http://localhost:{port}")
        click.echo("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")
