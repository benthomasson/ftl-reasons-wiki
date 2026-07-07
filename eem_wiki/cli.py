import http.server
import functools
import json
import os

import click

from .generator import generate_site, generate_directory_index


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
@click.option("-m", "--model", default=None,
              help="LLM model for page summaries (e.g. claude, gemini)")
@click.option("--timeout", default=300, type=int,
              help="LLM timeout in seconds (default: 300)")
@click.option("--parallel", default=0, type=int,
              help="Concurrent LLM workers (default: 0 = sequential)")
@click.option("--no-topic-cache", is_flag=True, default=False,
              help="Force fresh LLM topic classification (ignore cache)")
@click.option("--topics-only", is_flag=True, default=False,
              help="Use LLM for topics but skip all summaries")
@click.option("--skip-belief-summaries", is_flag=True, default=False,
              help="Use LLM for topics and topic summaries, skip belief summaries")
def build(input_path, output_dir, base_url, project_name, model, timeout,
          parallel, no_topic_cache, topics_only, skip_belief_summaries):
    """Generate static wiki from a network.json export."""
    if skip_belief_summaries:
        topics_only_val = "with-summaries"
    elif topics_only:
        topics_only_val = True
    else:
        topics_only_val = False
    stats = generate_site(input_path, output_dir,
                          base_url=base_url, project_name=project_name,
                          model=model, timeout=timeout, parallel=parallel,
                          no_topic_cache=no_topic_cache,
                          topics_only=topics_only_val)
    click.echo(f"Generated {stats['beliefs']} belief pages, "
               f"{stats['topics']} topic pages")
    click.echo(f"Output: {output_dir}/")


@cli.command("build-all")
@click.option("--config", "-c", "config_path", required=True,
              type=click.Path(exists=True), help="Path to wikis.json config")
@click.option("--output", "-o", "output_dir", default="dist",
              help="Output directory (default: dist)")
@click.option("--base-url", default="",
              help="Base URL for sitemap and canonical links")
@click.option("-m", "--model", default=None,
              help="LLM model for page summaries (e.g. claude, gemini)")
@click.option("--timeout", default=300, type=int,
              help="LLM timeout in seconds (default: 300)")
@click.option("--parallel", default=0, type=int,
              help="Concurrent LLM workers (default: 0 = sequential)")
@click.option("--no-topic-cache", is_flag=True, default=False,
              help="Force fresh LLM topic classification (ignore cache)")
@click.option("--topics-only", is_flag=True, default=False,
              help="Use LLM for topics but skip all summaries")
@click.option("--skip-belief-summaries", is_flag=True, default=False,
              help="Use LLM for topics and topic summaries, skip belief summaries")
def build_all(config_path, output_dir, base_url, model, timeout, parallel,
              no_topic_cache, topics_only, skip_belief_summaries):
    """Build multiple wikis from a config file."""
    config_dir = os.path.dirname(os.path.abspath(config_path))
    with open(config_path) as f:
        wikis = json.load(f)

    if skip_belief_summaries:
        topics_only_val = "with-summaries"
    elif topics_only:
        topics_only_val = True
    else:
        topics_only_val = False

    base = base_url.rstrip("/")
    all_stats = []

    for entry in wikis:
        name = entry["name"]
        input_path = entry["input"]
        if not os.path.isabs(input_path):
            input_path = os.path.join(config_dir, input_path)

        wiki_output = os.path.join(output_dir, name)
        wiki_base = f"{base}/{name}" if base else ""

        click.echo(f"\nBuilding {name}...")
        stats = generate_site(
            input_path, wiki_output,
            base_url=wiki_base,
            project_name=entry.get("project_name"),
            model=model, timeout=timeout, parallel=parallel,
            no_topic_cache=no_topic_cache,
            topics_only=topics_only_val)

        stats["name"] = name
        stats["project_name"] = entry.get("project_name", "")
        all_stats.append(stats)

        click.echo(f"  {stats['beliefs']} belief pages, "
                   f"{stats['topics']} topic pages")

    generate_directory_index(output_dir, all_stats)
    click.echo(f"\nBuilt {len(all_stats)} wikis → {output_dir}/")


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
