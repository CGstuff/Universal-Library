"""
Universal Library (UL) - Main Entry Point

An asset library for Blender with modern Qt6 architecture.

Usage:
    python -m universal_library.main
"""

import sys
import shutil
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmapCache

from .config import Config
from .events.event_bus import get_event_bus
from .themes import get_theme_manager
from .utils.logging_config import LoggingConfig


def sync_protocol_to_library():
    """
    Copy protocol schema files to library/.schema/protocol/ for Blender addon access.

    This ensures the Blender addon can import the protocol from the library path
    without needing a separate copy bundled with the addon.
    """
    library_path = Config.load_library_path()
    if not library_path or not library_path.exists():
        return

    # Source: protocol/ directory next to this file
    source_protocol = Path(__file__).parent / 'protocol'
    if not source_protocol.exists():
        return

    # Destination: library/.schema/protocol/
    dest_schema = library_path / '.schema'
    dest_protocol = dest_schema / 'protocol'

    try:
        # Create .schema directory if needed
        dest_schema.mkdir(parents=True, exist_ok=True)

        # Copy protocol files (overwrite existing)
        if dest_protocol.exists():
            shutil.rmtree(dest_protocol)
        shutil.copytree(source_protocol, dest_protocol)

    except Exception as e:
        # Non-fatal - addon can fall back to bundled copy
        pass


def setup_application() -> QApplication:
    """
    Initialize and configure the Qt application

    Returns:
        Configured QApplication instance
    """
    # Create application
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName(Config.APP_NAME)
    app.setApplicationVersion(Config.APP_VERSION)
    app.setOrganizationName(Config.APP_AUTHOR)

    # Configure global pixmap cache for thumbnail performance
    QPixmapCache.setCacheLimit(Config.PIXMAP_CACHE_SIZE_KB)

    # Initialize event bus (singleton)
    get_event_bus()

    # Initialize ReviewService early to connect event handlers
    # This enables auto-join of new versions to active review cycles
    from .services.review import get_review_service
    get_review_service()

    # Initialize theme manager and apply current theme
    theme_manager = get_theme_manager()
    stylesheet = theme_manager.get_current_stylesheet()
    app.setStyleSheet(stylesheet)

    # Connect theme changes to stylesheet updates
    def on_theme_changed(theme_name: str):
        """Update stylesheet when theme changes"""
        new_stylesheet = theme_manager.get_current_stylesheet()
        app.setStyleSheet(new_stylesheet)

    theme_manager.theme_changed.connect(on_theme_changed)

    return app


def main():
    """
    Main entry point for Universal Library

    Creates the application, sets up the main window, and runs the event loop.
    """
    # Setup logging first
    log_dir = Config.get_user_data_dir() / 'logs'
    LoggingConfig.setup_logging(log_dir)

    logger = LoggingConfig.get_logger(__name__)
    logger.info(f"Starting {Config.APP_NAME} {Config.APP_VERSION}...")
    logger.info(f"Database: {Config.get_database_path()}")
    logger.info(f"Cache: {Config.get_cache_dir()}")

    # Sync protocol schema to library for Blender addon access
    sync_protocol_to_library()

    # Setup application
    app = setup_application()

    # Log theme info
    theme_manager = get_theme_manager()
    current_theme = theme_manager.get_current_theme()
    if current_theme:
        logger.info(f"Theme: {current_theme.name}")

    # Create and show main window
    from .widgets.main_window import MainWindow
    window = MainWindow()
    window.show()

    logger.info("Application started successfully!")
    logger.info(f"Pixmap cache: {Config.PIXMAP_CACHE_SIZE_KB / 1024:.0f} MB")

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
