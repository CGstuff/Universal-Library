"""
Blender Addon Installation Service

Handles automatic installation of the Universal Library addon to Blender.
Supports two installation methods:
1. Folder copy (legacy) - copies addon folder directly
2. Zip + script (recommended) - creates zip and uses Blender's addon installer

The zip method auto-configures storage path and exe path in addon preferences.
"""

import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AddonInstallerService:
    """Service for installing Blender addon programmatically"""

    ADDON_FOLDER_NAME = "UL_blender_plugin"

    def __init__(self):
        """
        Initialize addon installer service

        Auto-detects project root based on file location or PyInstaller bundle
        """
        # Check if running as PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running as compiled exe - use internal _MEIPASS path
            base_path = Path(sys._MEIPASS)
            self.addon_source_path = base_path / "UL_blender_plugin"
            self.install_script_path = base_path / "universal_library" / "services" / "utils" / "install_addon.py"
            self.exe_path = Path(sys.executable)  # Path to this exe
            logger.info(f"Running as bundled exe, using internal plugin path: {self.addon_source_path}")
        else:
            # Running in development mode - auto-detect root
            # This file is at: universal_library/services/addon_installer_service.py
            # Plugin is at: UL_blender_plugin/
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent  # Up 3 levels
            self.addon_source_path = project_root / "UL_blender_plugin"
            self.install_script_path = current_file.parent / "utils" / "install_addon.py"
            self.exe_path = project_root / "run.py"  # Dev mode uses script
            logger.info(f"Running in dev mode, using project plugin path: {self.addon_source_path}")

    def verify_blender_executable(self, blender_path: str) -> Tuple[bool, str, Optional[str]]:
        """
        Verify that the provided path is a valid Blender executable

        Args:
            blender_path: Path to blender.exe

        Returns:
            Tuple of (is_valid, message, version_string)
        """
        blender_path = Path(blender_path)

        if not blender_path.exists():
            return False, "Blender executable not found at specified path", None

        if not blender_path.is_file():
            return False, "Specified path is not a file", None

        if blender_path.name.lower() not in ['blender.exe', 'blender']:
            return False, "File does not appear to be a Blender executable", None

        try:
            result = subprocess.run(
                [str(blender_path), '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )

            version_output = result.stdout.strip()

            if "Blender" in version_output:
                version_line = version_output.split('\n')[0]
                logger.info(f"Found Blender: {version_line}")
                return True, f"Valid Blender installation: {version_line}", version_line
            else:
                return False, "Could not verify Blender version", None

        except subprocess.TimeoutExpired:
            return False, "Blender executable timed out during verification", None
        except Exception as e:
            return False, f"Error verifying Blender: {str(e)}", None

    def get_blender_addons_directory(self, blender_path: str) -> Optional[Path]:
        """
        Get the Blender addons directory for the user

        Args:
            blender_path: Path to blender.exe

        Returns:
            Path to addons directory or None if not found
        """
        blender_path = Path(blender_path)
        logger.info(f"Attempting to locate Blender addons directory for: {blender_path}")

        # Get the Blender version from the executable
        _, _, version_str = self.verify_blender_executable(str(blender_path))
        blender_version = None

        if version_str:
            try:
                parts = version_str.split()
                for part in parts:
                    if part[0].isdigit() and '.' in part:
                        version_parts = part.split('.')
                        blender_version = f"{version_parts[0]}.{version_parts[1]}"
                        logger.info(f"Detected Blender version: {blender_version}")
                        break
            except Exception as e:
                logger.warning(f"Could not parse Blender version: {e}")

        try:
            # Run Blender to get config directory
            logger.info("Attempting to get config directory from Blender...")
            script = "import bpy; print(bpy.utils.resource_path('USER'))"
            result = subprocess.run(
                [str(blender_path), '--background', '--python-expr', script],
                capture_output=True,
                text=True,
                timeout=30
            )

            lines = result.stdout.strip().split('\n')
            for line in lines:
                potential_path = Path(line.strip())
                if potential_path.exists() and 'Blender' in str(potential_path):
                    addons_dir = potential_path / "scripts" / "addons"
                    if addons_dir.exists() or addons_dir.parent.exists():
                        addons_dir.mkdir(parents=True, exist_ok=True)
                        logger.info(f"Found Blender addons directory via config path: {addons_dir}")
                        return addons_dir

            # Fallback: construct path manually using detected version
            logger.info("Config path method failed, using fallback path construction...")

            if not blender_version:
                logger.error("Could not determine Blender version for fallback path")
                return None

            if sys.platform == 'win32':
                base = Path(os.environ.get('APPDATA', '')) / "Blender Foundation" / "Blender"
            elif sys.platform == 'darwin':
                base = Path.home() / "Library" / "Application Support" / "Blender"
            else:  # Linux
                base = Path.home() / ".config" / "blender"

            logger.info(f"Base Blender config path: {base}")

            version_dir = base / blender_version
            addons_dir = version_dir / "scripts" / "addons"

            logger.info(f"Constructed addons path: {addons_dir}")

            try:
                addons_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Successfully created/verified Blender {blender_version} addons directory: {addons_dir}")
                return addons_dir
            except Exception as mkdir_error:
                logger.error(f"Could not create addons directory at {addons_dir}: {mkdir_error}")
                return None

        except Exception as e:
            logger.error(f"Error getting Blender addons directory: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def install_addon(self, blender_path: str) -> Tuple[bool, str]:
        """
        Install the addon to Blender

        Args:
            blender_path: Path to blender.exe

        Returns:
            Tuple of (success, message)
        """
        # Verify Blender executable
        is_valid, verify_msg, version = self.verify_blender_executable(blender_path)
        if not is_valid:
            return False, verify_msg

        # Check source addon exists
        if not self.addon_source_path.exists():
            error_msg = f"Addon source not found at: {self.addon_source_path}\n\n"
            error_msg += "This usually means the Blender plugin was not bundled with the application.\n"
            error_msg += "If you're running from source, make sure 'UL_blender_plugin' folder exists."
            logger.error(error_msg)
            return False, error_msg

        # Get addons directory
        logger.info(f"Looking for Blender addons directory for version: {version}")
        addons_dir = self.get_blender_addons_directory(blender_path)
        if not addons_dir:
            error_msg = f"Could not locate Blender addons directory for version {version}\n\n"
            error_msg += "Please check the application logs for more details."
            logger.error(error_msg)
            return False, error_msg

        # Destination path
        addon_dest_path = addons_dir / self.ADDON_FOLDER_NAME

        try:
            # Remove existing installation if present
            if addon_dest_path.exists():
                logger.info(f"Removing existing addon at {addon_dest_path}")
                shutil.rmtree(addon_dest_path)

            # Copy addon files
            logger.info(f"Installing addon to {addon_dest_path}")
            shutil.copytree(self.addon_source_path, addon_dest_path)

            return True, (
                f"Successfully installed addon to:\n{addon_dest_path}\n\n"
                "Please restart Blender and enable the addon in:\n"
                "Edit > Preferences > Add-ons > Search for 'Universal Library'"
            )

        except Exception as e:
            logger.error(f"Error installing addon: {e}")
            return False, f"Error installing addon: {str(e)}"

    def _create_addon_zip(self) -> Optional[Path]:
        """
        Create a temporary zip file of the addon folder.

        Returns:
            Path to the temporary zip file, or None if failed
        """
        if not self.addon_source_path.exists():
            logger.error(f"Addon source not found: {self.addon_source_path}")
            return None

        try:
            # Create temp directory for zip
            temp_dir = Path(tempfile.mkdtemp())
            zip_path = temp_dir / f"{self.ADDON_FOLDER_NAME}.zip"

            logger.info(f"Creating addon zip at: {zip_path}")

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in self.addon_source_path.rglob('*'):
                    # Skip __pycache__ and .pyc files
                    if '__pycache__' in file_path.parts or file_path.suffix == '.pyc':
                        continue

                    # Calculate relative path within the zip
                    # Files should be under UL_blender_plugin/ in the zip
                    rel_path = file_path.relative_to(self.addon_source_path.parent)
                    if file_path.is_file():
                        zf.write(file_path, rel_path)

            logger.info(f"Created addon zip: {zip_path} ({zip_path.stat().st_size} bytes)")
            return zip_path

        except Exception as e:
            logger.error(f"Failed to create addon zip: {e}")
            return None

    def install_addon_with_config(
        self,
        blender_path: str,
        storage_path: Optional[str] = None,
        auto_configure_exe: bool = True
    ) -> Tuple[bool, str]:
        """
        Install addon using zip + script method with auto-configuration.

        This method:
        1. Creates a zip of the addon folder
        2. Runs Blender with install_addon.py script
        3. Script installs addon and configures preferences
        4. Cleans up temporary files

        Args:
            blender_path: Path to blender.exe
            storage_path: Library storage path to configure (optional)
            auto_configure_exe: Whether to auto-set exe path in addon prefs

        Returns:
            Tuple of (success, message)
        """
        # Verify Blender executable
        is_valid, verify_msg, version = self.verify_blender_executable(blender_path)
        if not is_valid:
            return False, verify_msg

        # Check install script exists
        if not self.install_script_path.exists():
            logger.warning(f"Install script not found at {self.install_script_path}, falling back to folder copy")
            return self.install_addon(blender_path)

        # Create zip
        zip_path = self._create_addon_zip()
        if not zip_path:
            return False, "Failed to create addon zip file"

        try:
            # Build command arguments
            exe_arg = str(self.exe_path) if auto_configure_exe else "none"
            storage_arg = storage_path if storage_path else "none"

            cmd = [
                str(blender_path),
                '--background',
                '--python', str(self.install_script_path),
                '--',
                str(zip_path),
                storage_arg,
                exe_arg
            ]

            logger.info(f"Running Blender install command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            # Log output for debugging
            if result.stdout:
                logger.info(f"Blender stdout:\n{result.stdout}")
            if result.stderr:
                logger.warning(f"Blender stderr:\n{result.stderr}")

            if result.returncode != 0:
                error_msg = f"Blender install script failed (code {result.returncode})"
                if result.stderr:
                    error_msg += f"\n{result.stderr}"
                return False, error_msg

            # Build success message
            success_msg = (
                f"Successfully installed Universal Library addon!\n\n"
                f"Blender version: {version}\n"
            )
            if storage_path:
                success_msg += f"Library path: {storage_path}\n"
            if auto_configure_exe:
                success_msg += f"Desktop app: {self.exe_path}\n"

            success_msg += (
                f"\nThe addon is now enabled and configured.\n"
                f"Restart Blender to ensure all changes take effect."
            )

            return True, success_msg

        except subprocess.TimeoutExpired:
            return False, "Blender installation timed out after 60 seconds"
        except Exception as e:
            logger.error(f"Error during addon installation: {e}")
            return False, f"Installation error: {str(e)}"
        finally:
            # Cleanup temp zip
            if zip_path and zip_path.exists():
                try:
                    shutil.rmtree(zip_path.parent)
                    logger.info("Cleaned up temporary zip file")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp zip: {e}")

    def check_addon_installed(self, blender_path: str) -> Tuple[bool, Optional[Path]]:
        """
        Check if the addon is currently installed

        Args:
            blender_path: Path to blender.exe

        Returns:
            Tuple of (is_installed, installation_path)
        """
        addons_dir = self.get_blender_addons_directory(blender_path)
        if not addons_dir:
            return False, None

        addon_dest_path = addons_dir / self.ADDON_FOLDER_NAME

        if addon_dest_path.exists() and addon_dest_path.is_dir():
            init_file = addon_dest_path / "__init__.py"
            if init_file.exists():
                return True, addon_dest_path

        return False, None


# Singleton instance
_installer_instance: Optional[AddonInstallerService] = None


def get_addon_installer() -> AddonInstallerService:
    """Get global AddonInstallerService singleton instance"""
    global _installer_instance
    if _installer_instance is None:
        _installer_instance = AddonInstallerService()
    return _installer_instance


__all__ = ['AddonInstallerService', 'get_addon_installer']
