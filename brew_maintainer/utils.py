"""Utility functions for brew-maintainer."""

import logging
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional


class BrewError(Exception):
    """Base exception for brew-maintainer."""
    pass


class BrewNotFoundError(BrewError):
    """Homebrew executable not found."""
    pass


class BrewCommandError(BrewError):
    """Brew command failed."""

    def __init__(self, command: List[str], returncode: int, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"Command failed with code {returncode}: {' '.join(command)}")


def run_command(
    cmd: List[str],
    check: bool = True,
    capture_output: bool = True,
    dry_run: bool = False,
    timeout: int = 3600
) -> subprocess.CompletedProcess:
    """
    Run a command with error handling and logging.

    Args:
        cmd: Command and arguments as a list
        check: Raise exception on non-zero exit code
        capture_output: Capture stdout and stderr
        dry_run: If True, log command but don't execute
        timeout: Command timeout in seconds (default: 1 hour)

    Returns:
        CompletedProcess object with stdout, stderr, and returncode

    Raises:
        BrewNotFoundError: If brew command not found
        BrewCommandError: If command fails
        BrewError: On timeout or other errors
    """
    logger = logging.getLogger('brew_maintainer')
    logger.debug(f"Running: {' '.join(cmd)}")

    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(cmd)}")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )

        if result.stdout:
            logger.debug(f"stdout: {result.stdout.strip()}")
        if result.stderr:
            logger.debug(f"stderr: {result.stderr.strip()}")

        logger.debug(f"Command exited with code: {result.returncode}")
        return result

    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr if e.stderr else str(e)}")
        raise BrewCommandError(cmd, e.returncode, e.stderr if e.stderr else str(e))

    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout} seconds")
        raise BrewError(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")

    except FileNotFoundError as e:
        if cmd[0] == 'brew':
            raise BrewNotFoundError(
                "Homebrew not found in PATH. Please install Homebrew from https://brew.sh"
            )
        raise BrewError(f"Command not found: {cmd[0]}")


def setup_logging(verbose: bool = False, quiet: bool = False) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        verbose: Enable DEBUG level logging to console
        quiet: Only ERROR+ messages to console

    Returns:
        Configured logger instance
    """
    # Determine log directory
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'brew_maintainer.log'

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )

    # File handler (rotating, max 10MB, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if quiet:
        console_handler.setLevel(logging.ERROR)
    elif verbose:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Configure root logger
    logger = logging.getLogger('brew_maintainer')
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def parse_upgrade_count(output: str) -> int:
    """
    Parse the number of upgraded packages from brew output.

    Args:
        output: Output from brew upgrade command

    Returns:
        Number of packages upgraded
    """
    if not output or output.strip() == "":
        return 0

    lines = output.strip().split('\n')

    # Count lines that look like package upgrades (contain ->)
    upgrade_lines = [line for line in lines if '->' in line and '==>' in line]

    return len(upgrade_lines)


def parse_cleanup_size(output: str) -> str:
    """
    Parse disk space freed from cleanup output.

    Args:
        output: Output from brew cleanup command

    Returns:
        Human-readable string of space freed (e.g., "1.2 GB")
    """
    if not output:
        return "0 B"

    # Look for patterns like "freed 1.2GB" or "Removing: /path/to/file (123.4MB)"
    import re

    # Try to find total in output
    match = re.search(r'freed\s+([\d.]+\s*[KMGT]?B)', output, re.IGNORECASE)
    if match:
        return match.group(1)

    # Otherwise sum up individual removals
    matches = re.findall(r'\(([\d.]+)\s*([KMGT]?B)\)', output)
    if matches:
        total_bytes = 0
        for size, unit in matches:
            multiplier = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
            total_bytes += float(size) * multiplier.get(unit.upper(), 1)

        # Convert back to human readable
        for unit in ['TB', 'GB', 'MB', 'KB', 'B']:
            divisor = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}[unit]
            if total_bytes >= divisor:
                return f"{total_bytes / divisor:.1f} {unit}"

    return "Unknown"
