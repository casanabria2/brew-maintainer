"""Core Homebrew maintenance operations."""

import logging
from typing import Any, Dict, Optional
from pathlib import Path

from .utils import (
    run_command, parse_upgrade_count, parse_upgraded_names, parse_cleanup_size,
    create_askpass_env, cleanup_askpass_env, keychain_has_password,
    prime_sudo_credentials
)


class BrewMaintainer:
    """Manages Homebrew package updates and cleanup."""

    def __init__(self, dry_run: bool = False, skip_backup: bool = False,
                 backup_dir: Optional[str] = None, use_keychain: bool = False):
        """
        Initialize the Homebrew maintainer.

        Args:
            dry_run: If True, show what would be done without executing
            skip_backup: If True, skip backup operations
            backup_dir: Custom backup directory path
            use_keychain: If True, use macOS keychain for sudo password
        """
        self.logger = logging.getLogger('brew_maintainer')
        self.dry_run = dry_run
        self.skip_backup = skip_backup
        self.backup_dir = Path(backup_dir) if backup_dir else None
        self.use_keychain = use_keychain
        self._env: Optional[Dict[str, str]] = None
        self.stats = {
            'formulae_upgraded': 0,
            'casks_upgraded': 0,
            'formulae_names': [],
            'casks_names': [],
            'space_freed': '0 B',
            'backup_created': False
        }

    def _get_env(self) -> Optional[Dict[str, str]]:
        """Get environment with SUDO_ASKPASS if keychain is enabled."""
        if self.use_keychain and self._env is None:
            if not keychain_has_password():
                self.logger.warning(
                    "Keychain password not found. Run 'brew-maintainer setup-keychain' first."
                )
            else:
                self._env = create_askpass_env()
                # Prime sudo credentials so brew's internal sudo calls won't prompt
                if prime_sudo_credentials():
                    self.logger.debug("Using keychain for sudo authentication")
                else:
                    self.logger.warning(
                        "Could not authenticate sudo with keychain password. "
                        "You may be prompted for password."
                    )
        return self._env

    def _cleanup_env(self) -> None:
        """Clean up temporary askpass script."""
        if self._env is not None:
            cleanup_askpass_env(self._env)
            self._env = None

    def update_packages(self) -> Dict[str, Any]:
        """
        Update all Homebrew formulae and casks.

        Returns:
            Dictionary with update statistics

        Raises:
            BrewError: If update fails
        """
        self.logger.info("Starting package updates...")

        # Step 1: Update Homebrew itself
        self.logger.info("Updating Homebrew...")
        env = self._get_env()
        run_command(['brew', 'update'], dry_run=self.dry_run, env=env, stream_output=True)

        # Step 2: Upgrade formulae
        self.logger.info("Upgrading formulae...")
        try:
            result_formula = run_command(
                ['brew', 'upgrade', '--formula'],
                dry_run=self.dry_run,
                check=False,  # Don't fail if nothing to upgrade
                env=env,
                stream_output=True
            )
            formulae_count = parse_upgrade_count(result_formula.stdout)
            self.stats['formulae_upgraded'] = formulae_count
            self.stats['formulae_names'] = parse_upgraded_names(result_formula.stdout)

            if formulae_count == 0:
                self.logger.info("No formulae to upgrade")

        except Exception as e:
            self.logger.warning(f"Failed to upgrade formulae: {e}")
            self.stats['formulae_upgraded'] = 0
            self.stats['formulae_names'] = []

        # Step 3: Upgrade casks (with --greedy to catch auto-updating casks)
        self.logger.info("Upgrading casks...")
        try:
            result_cask = run_command(
                ['brew', 'upgrade', '--cask', '--greedy', '--force'],
                dry_run=self.dry_run,
                check=False,  # Don't fail if nothing to upgrade
                env=env,
                stream_output=True
            )
            casks_count = parse_upgrade_count(result_cask.stdout)
            self.stats['casks_upgraded'] = casks_count
            self.stats['casks_names'] = parse_upgraded_names(result_cask.stdout)

            if casks_count == 0:
                self.logger.info("No casks to upgrade")

        except Exception as e:
            self.logger.warning(f"Failed to upgrade casks: {e}")
            self.stats['casks_upgraded'] = 0
            self.stats['casks_names'] = []

        total_upgraded = self.stats['formulae_upgraded'] + self.stats['casks_upgraded']
        self.logger.info(f"Package updates complete: {total_upgraded} packages upgraded")

        return {
            'formulae_upgraded': self.stats['formulae_upgraded'],
            'casks_upgraded': self.stats['casks_upgraded'],
            'formulae_names': self.stats['formulae_names'],
            'casks_names': self.stats['casks_names']
        }

    def cleanup(self) -> Dict[str, Any]:
        """
        Clean up old versions and cache.

        Returns:
            Dictionary with cleanup statistics

        Raises:
            BrewError: If cleanup fails
        """
        self.logger.info("Starting cleanup...")

        try:
            env = self._get_env()
            # Run cleanup with scrub flag
            self.logger.info("Removing old versions...")
            result_cleanup = run_command(
                ['brew', 'cleanup', '-s'],
                dry_run=self.dry_run,
                check=False,
                env=env,
                stream_output=True
            )

            # Prune old cache files
            self.logger.info("Pruning cache...")
            result_prune = run_command(
                ['brew', 'cleanup', '--prune=all'],
                dry_run=self.dry_run,
                check=False,
                env=env,
                stream_output=True
            )

            # Parse space freed from both commands
            combined_output = (
                result_cleanup.stdout + result_cleanup.stderr +
                result_prune.stdout + result_prune.stderr
            )
            space_freed = parse_cleanup_size(combined_output)
            self.stats['space_freed'] = space_freed

            if space_freed != "0 B":
                self.logger.info(f"Cleanup complete: freed {space_freed}")
            else:
                self.logger.info("Cleanup complete: no space to free")

        except Exception as e:
            self.logger.warning(f"Cleanup encountered issues: {e}")
            self.stats['space_freed'] = "Unknown"

        return {
            'space_freed': self.stats['space_freed']
        }

    def create_backup(self) -> Dict[str, Any]:
        """
        Create backup of installed packages.

        Returns:
            Dictionary with backup statistics
        """
        if self.skip_backup:
            self.logger.info("Skipping backup (--no-backup)")
            return {'backup_created': False}

        # Import here to avoid circular dependency
        from .backup import BrewBackupManager

        self.logger.info("Creating backup...")

        try:
            backup_manager = BrewBackupManager(
                backup_dir=self.backup_dir,
                dry_run=self.dry_run
            )
            result = backup_manager.create_backup()
            self.stats['backup_created'] = True

            self.logger.info(
                f"Backup created: {result['formulae_count']} formulae, "
                f"{result['casks_count']} casks, {result['taps_count']} taps"
            )

            return result

        except Exception as e:
            self.logger.error(f"Failed to create backup: {e}")
            self.stats['backup_created'] = False
            return {'backup_created': False}

    def restore_from_backup(self) -> None:
        """
        Restore packages from backup Brewfile.

        Raises:
            BrewError: If restore fails
        """
        from .backup import BrewBackupManager

        self.logger.info("Restoring from backup...")

        backup_manager = BrewBackupManager(
            backup_dir=self.backup_dir,
            dry_run=self.dry_run
        )
        backup_manager.restore_from_backup()

        self.logger.info("Restore complete")

    def run_all(self) -> Dict[str, Any]:
        """
        Run complete maintenance workflow: update, cleanup, backup.

        Returns:
            Dictionary with all statistics

        Raises:
            BrewError: On critical failures
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting Homebrew maintenance")
        self.logger.info("=" * 60)

        # Update packages
        try:
            update_stats = self.update_packages()
        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            update_stats = {'formulae_upgraded': 0, 'casks_upgraded': 0, 'formulae_names': [], 'casks_names': []}

        # Cleanup
        try:
            cleanup_stats = self.cleanup()
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
            cleanup_stats = {'space_freed': 'Unknown'}

        # Backup
        try:
            backup_stats = self.create_backup()
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            backup_stats = {'backup_created': False}

        # Combine all stats
        all_stats = {**update_stats, **cleanup_stats, **backup_stats}

        # Clean up askpass script
        self._cleanup_env()

        self.logger.info("=" * 60)
        self.logger.info("Maintenance complete")
        self.logger.info(f"  Formulae upgraded: {all_stats.get('formulae_upgraded', 0)}")
        for name in all_stats.get('formulae_names', []):
            self.logger.info(f"    - {name}")
        self.logger.info(f"  Casks upgraded: {all_stats.get('casks_upgraded', 0)}")
        for name in all_stats.get('casks_names', []):
            self.logger.info(f"    - {name}")
        self.logger.info(f"  Space freed: {all_stats.get('space_freed', 'Unknown')}")
        self.logger.info(f"  Backup created: {all_stats.get('backup_created', False)}")
        self.logger.info("=" * 60)

        return all_stats
