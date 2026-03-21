"""Command-line interface for brew-maintainer."""

import argparse
import getpass
import sys
import logging

from .maintainer import BrewMaintainer
from .utils import (
    setup_logging, BrewError, BrewNotFoundError,
    keychain_store_password, keychain_delete_password, keychain_has_password
)


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

    # Setup keychain command
    subparsers.add_parser(
        'setup-keychain',
        help='Store sudo password in macOS keychain for unattended operation'
    )

    # Remove keychain command
    subparsers.add_parser(
        'remove-keychain',
        help='Remove sudo password from macOS keychain'
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
        '--use-keychain',
        action='store_true',
        help='Use macOS keychain for sudo password (run setup-keychain first)'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )

    return parser


def _setup_keychain(logger: logging.Logger) -> None:
    """Set up sudo password in macOS keychain."""
    if keychain_has_password():
        logger.info("Keychain already has a stored password.")
        response = input("Replace it? [y/N]: ").strip().lower()
        if response != 'y':
            logger.info("Keeping existing password.")
            return

    print("Enter your sudo password (will be stored securely in macOS keychain):")
    password = getpass.getpass("Password: ")

    if not password:
        logger.error("No password provided.")
        sys.exit(1)

    # Verify the password works
    import subprocess
    verify = subprocess.run(
        ['sudo', '-S', '-v'],
        input=password + '\n',
        capture_output=True,
        text=True
    )
    if verify.returncode != 0:
        logger.error("Password verification failed. Please check your password.")
        sys.exit(1)

    if keychain_store_password(password):
        logger.info("Password stored successfully in keychain.")
        logger.info("You can now use --use-keychain for unattended operation.")
    else:
        logger.error("Failed to store password in keychain.")
        sys.exit(1)


def _remove_keychain(logger: logging.Logger) -> None:
    """Remove sudo password from macOS keychain."""
    if not keychain_has_password():
        logger.info("No password stored in keychain.")
        return

    if keychain_delete_password():
        logger.info("Password removed from keychain.")
    else:
        logger.error("Failed to remove password from keychain.")
        sys.exit(1)


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
        # Handle keychain setup commands (don't need BrewMaintainer)
        if args.command == 'setup-keychain':
            _setup_keychain(logger)
            return

        if args.command == 'remove-keychain':
            _remove_keychain(logger)
            return

        # Validate keychain password exists if --use-keychain was specified
        if args.use_keychain and not keychain_has_password():
            logger.error(
                "No sudo password found in keychain. "
                "Run 'brew-maintainer setup-keychain' first."
            )
            sys.exit(1)

        # Initialize maintainer
        maintainer = BrewMaintainer(
            dry_run=args.dry_run,
            skip_backup=args.no_backup,
            backup_dir=args.backup_dir,
            use_keychain=args.use_keychain
        )

        # Execute command
        try:
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
        finally:
            # Clean up askpass temp file if created
            maintainer._cleanup_env()

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
