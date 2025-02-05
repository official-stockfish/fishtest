#!/usr/bin/env python3
"""Back up neural network files to AWS S3 and check net hashes for integrity.

This script offers two modes:
  - Backup: Synchronize new neural net files to AWS S3.
  - Check: Verify local neural net file hashes.
"""

import argparse
import gzip
import hashlib
import logging
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class AwsConfig:
    """Configuration for AWS S3 bucket."""

    bucket: str = "s3://fishtest/backup/archive/nn/"
    bin: Path = field(
        default_factory=lambda: Path(get_required_env_var("VENV", expand=True))
        / "bin"
        / "aws",
    )
    access_key_id: str = field(
        default_factory=lambda: get_required_env_var("AWS_ACCESS_KEY_ID"),
    )
    secret_access_key: str = field(
        default_factory=lambda: get_required_env_var("AWS_SECRET_ACCESS_KEY"),
    )

    def get_aws_env(self) -> dict[str, str]:
        """Return the AWS environment variables."""
        return {
            "AWS_ACCESS_KEY_ID": self.access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.secret_access_key,
        }


def get_required_env_var(key: str, *, expand: bool = False) -> str:
    """Read a required variable from $HOME/.profile directly.

    Search for a line like:
    export VARIABLE_NAME=value
    export VARIABLE_NAME="value"
    export VARIABLE_NAME='value'
    Optionally expand environment variables if 'expand' is True.
    """
    profile_path = Path.home() / ".profile"
    if profile_path.exists():
        with profile_path.open() as profile:
            pattern = re.compile(
                r"^export\s+" + re.escape(key) + r"=(?:([\"'])(.*?)\1|(\S+))$",
            )
            for line in profile:
                match = pattern.match(line.strip())
                if match:
                    if match.group(1):
                        quote = match.group(1)
                        # Guard against quoted spaces/tabs in value
                        val = (match.group(2) or "").strip()
                        if not val:
                            break
                        if expand and quote == '"':
                            return os.path.expandvars(val)
                        return val
                    # Guard against empty value from a wrong regex
                    val = (match.group(3) or "").strip()
                    if not val:
                        break
                    return os.path.expandvars(val) if expand else val
    detail = f"Required variable '{key}' not found/set in $HOME/.profile"
    raise OSError(detail)


def is_valid_net_hash(net: Path) -> bool:
    """Check if the net file has a valid hash by reading and decompressing inline."""
    try:
        net_data = gzip.decompress(net.read_bytes())
    except Exception:
        logger.exception("Exception reading/decompressing the net %s", net)
        return False
    net_hash = hashlib.sha256(net_data).hexdigest()[:12]
    return net_hash == net.name[3:15]


def get_invalid_net(net: Path) -> Path | None:
    """Return the net file if it has an invalid hash, otherwise return None."""
    return None if is_valid_net_hash(net) else net


def verify_net_hashes(net_path_list: Iterable[Path]) -> list[Path]:
    """Check the hashes of a list of net files and return those with invalid hashes."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        return [
            net
            for net in executor.map(get_invalid_net, net_path_list)
            if net is not None
        ]


def execute_aws_command(aws_cmd: list[str | Path], env: dict[str, str]) -> list[str]:
    """Run an AWS CLI command with provided aws_env and return the output."""
    aws_log = subprocess.run(
        aws_cmd,
        stdout=subprocess.PIPE,
        env=env,
        text=True,
        check=False,
    )
    return aws_log.stdout.splitlines()


def list_aws_bucket(config: AwsConfig) -> list[str]:
    """List the contents of the AWS S3 bucket."""
    aws_cmd: list[str | Path] = [config.bin, "s3", "ls", config.bucket]
    return execute_aws_command(aws_cmd, config.get_aws_env())


def sync_aws_directory(
    local_path: Path,
    config: AwsConfig,
    *,
    dryrun: bool = True,
) -> list[str]:
    """Sync the local net files with the AWS S3 bucket."""
    aws_cmd: list[str | Path] = [
        config.bin,
        "s3",
        "sync",
        local_path,
        config.bucket,
        "--exclude='*'",
        "--include='*.nnue.gz'",
    ]
    if dryrun:
        aws_cmd.append("--dryrun")
    return execute_aws_command(aws_cmd, config.get_aws_env())


def is_net_in_log(net: Path, log: list[str]) -> bool:
    """Check if the net file is mentioned in the log."""
    return any(net.name in line for line in log)


def find_unregistered_nets(nets_folder: Path, config: AwsConfig) -> list[Path]:
    """Find new net files that are not yet in the AWS S3 bucket."""
    logger.info("Get info from AWS S3 bucket...")
    aws_dry_sync = sync_aws_directory(nets_folder, config, dryrun=True)
    aws_ls = list_aws_bucket(config)
    logger.info("Find new nets...")
    new_nets = []
    for net in nets_folder.glob("nn-*.nnue.gz"):
        if not is_net_in_log(net, aws_ls):
            new_nets.append(net)
            logger.info("Found new net %s", net)
        elif is_net_in_log(net, aws_dry_sync):
            logger.warning(
                "The net %s is already on aws and it is changed locally.",
                net.name,
            )
    if new_nets:
        logger.info("Check hash for new nets...")
        wrong_hashes = verify_net_hashes(new_nets)
        for net in wrong_hashes:
            new_nets.remove(net)
            logger.warning("Wrong hash, removed net %s from backup", net.name)
    return new_nets


def sync_new_nets_to_aws(new_nets: Iterable[Path], config: AwsConfig) -> None:
    """Sync new net files to the AWS S3 bucket using config."""
    logger.info("Sync new nets in AWS S3 bucket...")
    with TemporaryDirectory() as temp_folder:
        links_folder = Path(temp_folder)
        for net in new_nets:
            (links_folder / net.name).symlink_to(net)
        aws_sync = sync_aws_directory(links_folder, config, dryrun=False)
    logger.info("AWS S3 sync log:")
    for line in aws_sync:
        logger.info(line)


def backup_nets_to_aws(nets_folder: Path) -> None:
    """Back up neural network files to AWS S3."""
    try:
        config = AwsConfig()
    except OSError:
        logger.exception("Missing AWS environment variable")
        sys.exit(1)
    try:
        logger.info("Start nets backup...")
        new_nets = find_unregistered_nets(nets_folder, config)
        if new_nets:
            sync_new_nets_to_aws(new_nets, config)
        logger.info("End nets backup")
    except Exception:
        logger.exception("Exception during nets backup")
        sys.exit(1)


def check_nets_hashes(nets_folder: Path) -> None:
    """Run neural network hashes check similar to nets_hashes_check.py."""
    logger.info("Start nets hashes check...")
    wrong_hashes = verify_net_hashes(nets_folder.glob("nn-*.nnue.gz"))
    for net in wrong_hashes:
        logger.warning("Wrong hash for %s", net.name)
    logger.info("End nets hashes check")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments: either backup or check mode must be provided."""
    parser = argparse.ArgumentParser(description="AWS nets backup and hash check")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--backup",
        action="store_true",
        help="Perform backup operation",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Perform nets hash check",
    )
    parser.add_argument(
        "--path",
        default="/var/www/fishtest/nn",
        help="Path to the nets folder (default: /var/www/fishtest/nn)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    nets_folder = Path(args.path)

    if not nets_folder.exists():
        logger.error("Nets folder does not exist: %s", nets_folder)
        sys.exit(1)
    try:
        if args.backup:
            backup_nets_to_aws(nets_folder)
        elif args.check:
            check_nets_hashes(nets_folder)
    except KeyboardInterrupt:
        logger.warning("Aborted manually")
        sys.exit(1)
    except Exception:
        logger.exception("Exception during script execution")
        sys.exit(1)
