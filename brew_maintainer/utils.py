"""Utility functions for brew-maintainer."""

import logging
import os
import subprocess
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional

# Keychain service name for storing sudo password
KEYCHAIN_SERVICE = "brew-maintainer-sudo"


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


def keychain_has_password() -> bool:
    """Check if sudo password is stored in keychain."""
    try:
        result = subprocess.run(
            ['security', 'find-generic-password', '-s', KEYCHAIN_SERVICE, '-w'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def keychain_store_password(password: str) -> bool:
    """
    Store sudo password in macOS keychain.

    Args:
        password: The sudo password to store

    Returns:
        True if successful, False otherwise
    """
    try:
        # Delete existing entry if present (ignore errors)
        subprocess.run(
            ['security', 'delete-generic-password', '-s', KEYCHAIN_SERVICE],
            capture_output=True
        )
        # Add new entry
        result = subprocess.run(
            ['security', 'add-generic-password',
             '-s', KEYCHAIN_SERVICE,
             '-a', os.environ.get('USER', 'user'),
             '-w', password],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def keychain_delete_password() -> bool:
    """Delete sudo password from keychain."""
    try:
        result = subprocess.run(
            ['security', 'delete-generic-password', '-s', KEYCHAIN_SERVICE],
            capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False


def create_askpass_env() -> Dict[str, str]:
    """
    Create environment with SUDO_ASKPASS pointing to a keychain helper.

    Returns:
        Environment dict with SUDO_ASKPASS set
    """
    # Create a temporary askpass script
    askpass_script = f'''#!/bin/bash
security find-generic-password -s "{KEYCHAIN_SERVICE}" -w 2>/dev/null
'''
    # Create temp file that persists until process ends
    fd, askpass_path = tempfile.mkstemp(prefix='brew_askpass_', suffix='.sh')
    try:
        os.write(fd, askpass_script.encode())
        os.close(fd)
        os.chmod(askpass_path, 0o700)
    except Exception:
        os.close(fd)
        raise

    env = os.environ.copy()
    env['SUDO_ASKPASS'] = askpass_path
    # Store path for cleanup
    env['_ASKPASS_TEMP_FILE'] = askpass_path
    return env


def prime_sudo_credentials() -> bool:
    """
    Prime sudo credential cache using password from keychain.

    This authenticates sudo once so subsequent sudo calls (including those
    made internally by brew) won't prompt for a password during the cache
    validity period.

    Returns:
        True if sudo was successfully authenticated, False otherwise
    """
    logger = logging.getLogger('brew_maintainer')

    try:
        # Get password from keychain
        result = subprocess.run(
            ['security', 'find-generic-password', '-s', KEYCHAIN_SERVICE, '-w'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.warning("Could not retrieve password from keychain")
            return False

        password = result.stdout.strip()

        # Authenticate sudo with the password (validates and caches credentials)
        auth_result = subprocess.run(
            ['sudo', '-S', '-v'],
            input=password + '\n',
            capture_output=True,
            text=True
        )

        if auth_result.returncode == 0:
            logger.debug("sudo credentials cached successfully")
            return True
        else:
            logger.warning("Failed to authenticate sudo with keychain password")
            return False

    except Exception as e:
        logger.warning(f"Error priming sudo credentials: {e}")
        return False


def cleanup_askpass_env(env: Dict[str, str]) -> None:
    """Clean up temporary askpass script."""
    askpass_path = env.get('_ASKPASS_TEMP_FILE')
    if askpass_path and os.path.exists(askpass_path):
        try:
            os.unlink(askpass_path)
        except Exception:
            pass


def run_command(
    cmd: List[str],
    check: bool = True,
    capture_output: bool = True,
    dry_run: bool = False,
    timeout: int = 3600,
    env: Optional[Dict[str, str]] = None,
    stream_output: bool = False
) -> subprocess.CompletedProcess:
    """
    Run a command with error handling and logging.

    Args:
        cmd: Command and arguments as a list
        check: Raise exception on non-zero exit code
        capture_output: Capture stdout and stderr
        dry_run: If True, log command but don't execute
        timeout: Command timeout in seconds (default: 1 hour)
        env: Optional environment variables dict
        stream_output: If True, stream output to terminal in real-time

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
        if stream_output:
            # Stream output to terminal while capturing for parsing
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env
            )
            output_lines = []
            for line in process.stdout:
                print(line, end='', flush=True)
                output_lines.append(line)
            process.wait(timeout=timeout)
            combined_output = ''.join(output_lines)

            result = subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout=combined_output,
                stderr=""
            )
            if check and result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )
            return result
        else:
            result = subprocess.run(
                cmd,
                check=check,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                env=env
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


def parse_upgraded_names(output: str) -> list:
    """
    Parse the names of upgraded packages from brew output.

    Args:
        output: Output from brew upgrade command

    Returns:
        List of package names that were upgraded
    """
    if not output or output.strip() == "":
        return []

    import re

    names = []

    # Look for lines in the package list after "==> Upgrading N outdated packages:"
    # Each line looks like: "arc 1.137.0,76310 -> 1.139.0,77482" or "awscli 2.34.13 -> 2.34.14"
    # Only match lines that have the "name version -> version" pattern
    for match in re.finditer(r'^([a-zA-Z0-9@/_-]+)\s+\S+\s+->\s+\S+', output, re.MULTILINE):
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)

    return names


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

    import re

    # Look for "==> Upgrading N outdated packages:" header
    match = re.search(r'==> Upgrading (\d+) outdated package', output)
    if match:
        return int(match.group(1))

    # Fallback: count successful upgrade lines (🍺 ... was successfully upgraded!)
    success_count = len(re.findall(r'🍺.*was successfully upgraded!', output))
    if success_count > 0:
        return success_count

    # Fallback: count lines with version arrows (name X.X -> Y.Y)
    # These appear as "  3.9.0.1 -> 3.9.0.2" or "pandoc 3.9.0.1 -> 3.9.0.2"
    upgrade_lines = re.findall(r'[\d.]+ -> [\d.]+', output)
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

    import re

    # Look for "freed approximately X.XMB/GB" pattern from brew cleanup summary
    # Example: "==> This operation has freed approximately 525.5MB of disk space."
    matches = re.findall(
        r'freed approximately ([\d.]+)\s*([KMGT]?B)',
        output,
        re.IGNORECASE
    )
    if matches:
        # Sum all "freed approximately" amounts (there may be multiple cleanup operations)
        total_bytes = 0
        for size, unit in matches:
            multiplier = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
            total_bytes += float(size) * multiplier.get(unit.upper(), 1)

        # Convert back to human readable
        for unit in ['TB', 'GB', 'MB', 'KB', 'B']:
            divisor = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}[unit]
            if total_bytes >= divisor:
                return f"{total_bytes / divisor:.1f} {unit}"

    # Fallback: look for simple "freed X.XGB" pattern
    match = re.search(r'freed\s+([\d.]+\s*[KMGT]?B)', output, re.IGNORECASE)
    if match:
        return match.group(1)

    return "0 B"
