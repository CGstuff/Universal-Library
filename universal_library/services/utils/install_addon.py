"""
Blender Addon Installation Script

This script runs INSIDE Blender via --python flag.
It installs the Universal Library addon from a zip file and configures paths.

Usage:
    blender --background --python install_addon.py -- <zip_path> [storage_path] [exe_path]

Arguments:
    zip_path: Path to addon zip file (required)
    storage_path: Library storage path to configure (optional, "none" to skip)
    exe_path: Desktop app executable path (optional, "none" to skip)
"""

import bpy
import sys
import os
import addon_utils


def install_addon(zip_path, storage_path=None, exe_path=None):
    """
    Install and configure the Universal Library addon.

    Args:
        zip_path: Path to the addon zip file
        storage_path: Library storage path to set in preferences
        exe_path: Desktop app executable path to set in preferences

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*60}")
    print("Universal Library - Addon Installer")
    print(f"{'='*60}\n")

    print(f"Starting installation of addon from: {zip_path}")

    if not os.path.exists(zip_path):
        print(f"Error: Zip file not found at {zip_path}")
        return False

    try:
        # Install the addon from zip
        print("Installing addon...")
        bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)

        # The addon name matches the folder name inside the zip
        addon_name = "UL_blender_plugin"

        # Enable the addon
        print(f"Enabling addon '{addon_name}'...")
        addon_utils.enable(addon_name, default_set=True)

        # Get preferences object
        prefs = None
        if addon_name in bpy.context.preferences.addons:
            prefs = bpy.context.preferences.addons[addon_name].preferences
        else:
            print(f"Warning: Addon '{addon_name}' not found in preferences after enabling.")

        if prefs:
            # Configure storage/library path if provided
            if storage_path and storage_path.lower() != "none":
                print(f"Configuring library path: {storage_path}")
                try:
                    prefs.library_path = storage_path
                    print("Library path set successfully.")
                except Exception as e:
                    print(f"Error setting library path: {e}")

            # Configure executable path if provided
            if exe_path and exe_path.lower() != "none":
                print(f"Configuring executable path: {exe_path}")
                try:
                    prefs.app_executable_path = exe_path
                    # Also set launch mode to PRODUCTION
                    prefs.launch_mode = 'PRODUCTION'
                    print("Executable path and PRODUCTION mode set successfully.")
                except Exception as e:
                    print(f"Error setting executable path: {e}")

        # Save preferences to make it persistent
        print("Saving user preferences...")
        bpy.ops.wm.save_userpref()

        print(f"\n{'='*60}")
        print("Universal Library addon installed and enabled successfully!")
        print(f"{'='*60}\n")
        return True

    except Exception as e:
        print(f"Error during installation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Get arguments after "--"
    try:
        args_idx = sys.argv.index("--")
        args = sys.argv[args_idx + 1:]

        if not args:
            print("Error: No zip path provided")
            print("Usage: blender --background --python install_addon.py -- <zip_path> [storage_path] [exe_path]")
            sys.exit(1)

        zip_path = args[0]

        # Check for optional arguments
        storage_path = None
        exe_path = None

        if len(args) > 1:
            storage_path = args[1]

        if len(args) > 2:
            exe_path = args[2]

        success = install_addon(zip_path, storage_path, exe_path)

        if not success:
            sys.exit(1)

    except ValueError:
        print("Error: Arguments not found. Use '--' to separate arguments.")
        print("Usage: blender --background --python install_addon.py -- <zip_path> [storage_path] [exe_path]")
        sys.exit(1)
