#!/usr/bin/env python3

"""Build CIDR configuration for Nginx.

Download the IP address ranges from the ipverse/rir-ip repository
and build the Nginx configuration file.
"""

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path


def clone_repo(dest_dir: Path) -> Path:
    """Clone the ipverse/rir-ip repository into the destination directory."""
    repo_url = "https://github.com/ipverse/rir-ip.git"
    repo_dest = dest_dir / "rir-ip"
    logging.info("Cloning repository %s into %s", repo_url, repo_dest)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(repo_dest)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        logging.exception("Failed to clone the repository. Output: %s", e.stdout)
        raise
    return repo_dest


def read_aggregated(aggregated_file: Path) -> dict | None:
    """Read JSON data from an aggregated.json file."""
    try:
        with aggregated_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        logging.exception("Invalid JSON in %s", aggregated_file)
    except Exception:
        logging.exception("Failed to process aggregated file %s", aggregated_file)
    return None


def compute_max_length(folders: list[Path]) -> int:
    """Compute the maximum length among all subnet lines in aggregated files."""
    max_length = 0
    for folder in folders:
        aggregated_file = folder / "aggregated.json"
        if aggregated_file.exists():
            data = read_aggregated(aggregated_file)
            if data:
                ipv4 = data.get("subnets", {}).get("ipv4", [])
                ipv6 = data.get("subnets", {}).get("ipv6", [])
                lines = [line.strip() for line in ipv4 + ipv6]
                if lines:
                    max_length = max(max_length, *(len(line) for line in lines))
    return max_length


def build_nginx_conf(repo_path: Path) -> str:
    """Build the Nginx configuration file from the IP address ranges.

    Expects aggregated.json files containing a dict with a "subnets" key,
    where the subnets have "ipv4" and "ipv6" lists.
    """
    country_path = repo_path / "country"
    if not country_path.is_dir():
        msg = f"Country directory not found: {country_path}"
        raise ValueError(msg)

    folders = sorted(country_path.glob("*"))
    max_length = compute_max_length(folders)

    default_padding = " " * (max_length - len("default") + 1)
    conf_lines = ["geo $region {", f"    default{default_padding}ZZ;"]

    for folder in folders:
        country_code = folder.name.upper()
        aggregated_file = folder / "aggregated.json"
        if data := read_aggregated(aggregated_file):
            for line in data.get("subnets", {}).get("ipv4", []) + data.get(
                "subnets",
                {},
            ).get("ipv6", []):
                line_stripped = line.strip()
                conf_lines.append(f"    {line_stripped:<{max_length}} {country_code};")

    conf_lines.append("}")
    return "\n".join(conf_lines) + "\n"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Build CIDR configuration for Nginx")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("cidr.conf"),
        help=(
            "Output path for the Nginx configuration file (default: local cidr.conf; "
            "usual path is /etc/nginx/conf.d/cidr.conf)"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Build the CIDR configuration for Nginx."""
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = parse_args()
    output_conf: Path = args.output

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        try:
            repo_path = clone_repo(temp_path)
            nginx_conf = build_nginx_conf(repo_path)
        except Exception:
            logging.exception("Error building Nginx configuration")
            sys.exit(1)

    try:
        output_conf.write_text(nginx_conf, encoding="utf-8")
        logging.info("Configuration successfully written to %s", output_conf)
    except Exception:
        logging.exception("Failed to write configuration file")
        sys.exit(1)


if __name__ == "__main__":
    main()
