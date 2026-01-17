"""Command-line interface for brew-maintainer."""

import argparse
import sys
import logging

from .maintainer import BrewMaintainer
from .utils import setup_logging, BrewError, BrewNotFoundError


def create_parser() -> argparse.ArgumentParser:
    """
    Create and configure the argument parser.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog='brew-maintainer',
        description='Automated Homebrew package maintenance',
        epilog='Maintains Homebrew packages with automatic updates, cleanup, and backups.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Subcommands
    subparsers = parser.add_subparsers(
        dest='command',
        help='Command to run',
        metavar='COMMAND'
    )

    # All command (default)
    subparsers.add_parser(
        'all',
        help='Run all operations: update, cleanup, and backup (default)'
    )

    # Update command
    subparsers.add_parser(
        'update',
        help='Update packages only'
    )

    # Cleanup command
    subparsers.add_parser(
        'cleanup',
        help='Cleanup old versions and cache only'
    )

    # Backup command
    subparsers.add_parser(
        'backup',
        help='Create backup only'
    )

    # Restore command
    subparsers.add_parser(
        'restore',
        help='Restore packages from backup Brewfile'
    )

    # Global options
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output (DEBUG level)'
    )

    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Quiet mode - only show errors'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without executing'
    )

    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backup operation'
    )

    parser.add_argument(
        '--backup-dir',
        type=str,
        metavar='PATH',
        help='Custom backup directory path'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )

    return parser


def main() -> None:
    """
    Main entry point for the CLI.

    Parses arguments, configures logging, and executes commands.
    """
    parser = create_parser()
    args = parser.parse_args()

    # Default to 'all' if no command specified
    if args.command is None:
        args.command = 'all'

    # Setup logging
    logger = setup_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        # Initialize maintainer
        maintainer = BrewMaintainer(
            dry_run=args.dry_run,
            skip_backup=args.no_backup,
            backup_dir=args.backup_dir
        )

        # Execute command
        if args.command == 'all':
            maintainer.run_all()

        elif args.command == 'update':
            maintainer.update_packages()

        elif args.command == 'cleanup':
            maintainer.cleanup()

        elif args.command == 'backup':
            maintainer.create_backup()

        elif args.command == 'restore':
            maintainer.restore_from_backup()

        else:
            logger.error(f"Unknown command: {args.command}")
            sys.exit(1)

    except BrewNotFoundError as e:
        logger.error(str(e))
        logger.error("Please install Homebrew from https://brew.sh")
        sys.exit(2)

    except BrewError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user")
        sys.exit(130)

    except Exception as e:
        logger.critical(f"Unexpected error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == '__main__':
    main()
