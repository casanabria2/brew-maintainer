# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Homebrew Maintainer is an automated Python tool for managing Homebrew packages on macOS. It updates formulae/casks, cleans up old versions, and maintains git-tracked Brewfile backups.

## Commands

```bash
# Install locally for development
pip install -e .

# Run directly (no install needed)
python -m brew_maintainer

# Run with installed CLI
brew-maintainer

# Individual operations
python -m brew_maintainer update    # Update packages only
python -m brew_maintainer cleanup   # Cleanup only
python -m brew_maintainer backup    # Create backup only
python -m brew_maintainer restore   # Restore from backup

# Useful flags
python -m brew_maintainer --dry-run       # Preview without executing
python -m brew_maintainer --verbose       # DEBUG-level logging
python -m brew_maintainer --use-keychain  # Use stored password for unattended operation

# Unattended operation (no password prompts)
python -m brew_maintainer setup-keychain  # Store sudo password in macOS keychain (one-time)
python -m brew_maintainer --use-keychain  # Run with stored password
```

No test suite exists yet (tests/ directory is empty).

## Architecture

```
CLI (cli.py) → BrewMaintainer (maintainer.py) → BrewBackupManager (backup.py)
                                              ↘ utils.py (run_command, logging, parsing)
```

**Key components:**
- `cli.py`: argparse-based CLI with subcommands (all/update/cleanup/backup/restore)
- `maintainer.py`: `BrewMaintainer` class orchestrates update → cleanup → backup workflow
- `backup.py`: `BrewBackupManager` handles Brewfile generation via `brew bundle dump` and git auto-commits
- `utils.py`: `run_command()` subprocess wrapper with dry-run support, logging setup, output parsing

**Data flow:**
- Brewfile generated at `backups/Brewfile` with timestamp header
- Git auto-commits if repo detected (checked via `git rev-parse --git-dir`)
- Logs written to `logs/brew_maintainer.log` (rotating: 10MB, 5 backups)

**Error handling:**
- `BrewNotFoundError` (exit 2): Homebrew not installed
- `BrewCommandError` (exit 1): brew command failed
- `BrewError` (exit 1): General errors (timeout, file issues)

## Technical Notes

- Python 3.8+ only, zero external dependencies (pure stdlib)
- All brew commands use 1-hour timeout via `run_command()`
- Dry-run mode propagates through all operations including backup file writes
- Keychain integration uses `SUDO_ASKPASS` env var with a temp script that reads from macOS keychain (service: `brew-maintainer-sudo`)
