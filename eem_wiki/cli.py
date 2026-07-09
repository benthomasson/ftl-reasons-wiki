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
@click.option("--summaries-dir", default=None, type=click.Path(),
              help="Directory for committable summary JSON files")
def build(input_path, output_dir, base_url, project_name, model, timeout,
          parallel, no_topic_cache, topics_only, skip_belief_summaries,
          summaries_dir):
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
                          topics_only=topics_only_val,
                          summaries_dir=summaries_dir)
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
@click.option("--summaries-dir", default="summaries", type=click.Path(),
              help="Base directory for summary JSON files (default: summaries/)")
def build_all(config_path, output_dir, base_url, model, timeout, parallel,
              no_topic_cache, topics_only, skip_belief_summaries,
              summaries_dir):
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

    if not os.path.isabs(summaries_dir):
        summaries_dir = os.path.join(config_dir, summaries_dir)

    base = base_url.rstrip("/")
    all_stats = []

    for entry in wikis:
        name = entry["name"]
        input_path = entry["input"]
        if not os.path.isabs(input_path):
            input_path = os.path.join(config_dir, input_path)

        wiki_output = os.path.join(output_dir, name)
        wiki_base = f"{base}/{name}" if base else ""
        wiki_summaries = os.path.join(summaries_dir, name)

        click.echo(f"\nBuilding {name}...")
        stats = generate_site(
            input_path, wiki_output,
            base_url=wiki_base,
            project_name=entry.get("project_name"),
            model=model, timeout=timeout, parallel=parallel,
            no_topic_cache=no_topic_cache,
            topics_only=topics_only_val,
            directory_root="../",
            summaries_dir=wiki_summaries)

        stats["name"] = name
        stats["project_name"] = entry.get("project_name", "")
        all_stats.append(stats)

        click.echo(f"  {stats['beliefs']} belief pages, "
                   f"{stats['topics']} topic pages")

    generate_directory_index(output_dir, all_stats)
    click.echo(f"\nBuilt {len(all_stats)} wikis → {output_dir}/")


@cli.command("review-summaries")
@click.option("--summaries-dir", required=True, type=click.Path(exists=True),
              help="Directory containing belief-summaries.json")
@click.option("--input", "-i", "input_path", required=True,
              type=click.Path(exists=True), help="Path to network.json")
@click.option("-m", "--model", default="claude",
              help="LLM model for review (default: claude)")
@click.option("--timeout", default=300, type=int,
              help="LLM timeout in seconds (default: 300)")
@click.option("--filter", "filter_type", default=None,
              type=click.Choice(["defeats"]),
              help="Only review specific belief types")
@click.option("--fix", is_flag=True, default=False,
              help="Regenerate flagged summaries with tighter prompt")
@click.option("--parallel", default=0, type=int,
              help="Concurrent LLM workers (default: 0 = sequential)")
def review_summaries(summaries_dir, input_path, model, timeout, filter_type,
                     fix, parallel):
    """Review cached belief summaries for meaning drift."""
    from .summarize import review_belief_summary, summarize_defeater, summarize_belief

    with open(input_path) as f:
        data = json.load(f)
    nodes = data.get("nodes", {})

    belief_path = os.path.join(summaries_dir, "belief-summaries.json")
    with open(belief_path) as f:
        summaries = json.load(f)

    to_review = {}
    for nid, summary in summaries.items():
        if not summary:
            continue
        node = nodes.get(nid)
        if not node:
            continue
        if filter_type == "defeats":
            metadata = node.get("metadata") or {}
            if not metadata.get("defeats_node"):
                continue
        to_review[nid] = summary

    click.echo(f"Reviewing {len(to_review)} summaries...")

    results = {"PASS": [], "DRIFT": [], "REVERSED": [], "ERROR": [], "UNKNOWN": []}

    def _do_review(nid):
        node = nodes[nid]
        return nid, review_belief_summary(nid, node, to_review[nid], model, timeout)

    items = list(to_review.keys())
    if parallel > 0:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(_do_review, nid): nid for nid in items}
            done = 0
            for future in as_completed(futures):
                done += 1
                nid, result = future.result()
                verdict = result["verdict"]
                results[verdict].append((nid, result["explanation"]))
                if verdict != "PASS":
                    click.echo(f"  [{verdict}] {nid}: {result['explanation']}")
    else:
        for i, nid in enumerate(items, 1):
            if i % 10 == 0:
                click.echo(f"  Reviewed {i}/{len(items)}...", err=True)
            _, result = _do_review(nid)
            verdict = result["verdict"]
            results[verdict].append((nid, result["explanation"]))
            if verdict != "PASS":
                click.echo(f"  [{verdict}] {nid}: {result['explanation']}")

    click.echo(f"\nResults: {len(results['PASS'])} PASS, "
               f"{len(results['DRIFT'])} DRIFT, "
               f"{len(results['REVERSED'])} REVERSED, "
               f"{len(results['ERROR'])} ERROR")

    if fix and (results["DRIFT"] or results["REVERSED"]):
        flagged = [nid for nid, _ in results["DRIFT"] + results["REVERSED"]]
        click.echo(f"\nRegenerating {len(flagged)} flagged summaries...")
        for i, nid in enumerate(flagged, 1):
            node = nodes[nid]
            metadata = node.get("metadata") or {}
            if metadata.get("defeats_node"):
                new_summary = summarize_defeater(nid, node, nodes, model, timeout)
            else:
                new_summary = summarize_belief(nid, node, nodes, model, timeout)
            if new_summary:
                summaries[nid] = new_summary
                click.echo(f"  [{i}/{len(flagged)}] {nid}: regenerated")
            else:
                click.echo(f"  [{i}/{len(flagged)}] {nid}: failed", err=True)

        with open(belief_path, "w") as f:
            json.dump(summaries, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        click.echo(f"Updated {belief_path}")


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
