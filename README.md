# Homebrew Maintainer

Automated Homebrew package maintenance tool that updates formulae and casks, cleans up old versions, and maintains a backup of installed packages.

## Features

- **Update**: Automatically updates all Homebrew formulae and casks (including greedy casks)
- **Cleanup**: Removes old versions and clears cache to free disk space
- **Backup**: Maintains a Brewfile with all installed packages, tracked via git
- **Restore**: Reinstall packages from backup

## Installation

```bash
# Clone or navigate to the project directory
cd /Users/carlos/dev/carlos/brew-maintainer

# Install as a package (optional)
pip install -e .

# Or run directly with Python
python -m brew_maintainer
```

## Usage

### Run All Operations (Default)

Updates packages, runs cleanup, and creates backup:

```bash
python -m brew_maintainer
# or if installed:
brew-maintainer
```

### Individual Commands

```bash
# Update packages only
python -m brew_maintainer update

# Cleanup only
python -m brew_maintainer cleanup

# Create backup only
python -m brew_maintainer backup

# Restore from backup
python -m brew_maintainer restore
```

### Options

```bash
# Verbose output (shows all command details)
python -m brew_maintainer --verbose

# Dry run (preview without executing)
python -m brew_maintainer --dry-run

# Skip backup
python -m brew_maintainer --no-backup

# Custom backup directory
python -m brew_maintainer --backup-dir /path/to/backups

# Quiet mode (errors only)
python -m brew_maintainer --quiet
```

## Backup System

The backup is stored as a single `Brewfile` in the `backups/` directory. Each time you run the maintainer, it overwrites this file with the current state of your Homebrew packages. Git tracks the history of changes, so you can see what was added or removed over time.

```bash
# View backup
cat backups/Brewfile

# View backup history
git log backups/Brewfile

# See changes since last backup
git diff backups/Brewfile
```

## Logs

Logs are stored in `logs/brew_maintainer.log` with rotating file handlers (max 10MB per file, 5 backups kept).

## Automation

To run automatically on a schedule, add to crontab:

```bash
# Edit crontab
crontab -e

# Add line to run daily at 2 AM
0 2 * * * cd /Users/carlos/dev/carlos/brew-maintainer && python -m brew_maintainer --quiet
```

## Requirements

- Python 3.8 or higher
- Homebrew installed and in PATH
- No external Python dependencies

## Project Structure

```
brew-maintainer/
├── .gitignore
├── README.md
├── pyproject.toml
├── requirements.txt
├── brew_maintainer/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── maintainer.py
│   ├── backup.py
│   └── utils.py
├── backups/
│   └── Brewfile
├── logs/
│   └── brew_maintainer.log
└── tests/
    └── (test files)
```

## License

MIT
