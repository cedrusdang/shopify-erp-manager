"""Package entrypoint: allows running with `python -m shopify_erp`."""

import sys
import os
import logging
import tkinter as tk
from tkinter import messagebox

# Initialize logging FIRST, before suppressing console
from .logger import setup_logging

logger = setup_logging(log_dir="logs")

# Suppress console output on Windows (hide CLI/console window) - but keep logging
stdout_obj = getattr(sys, "stdout", None)
if sys.platform == "win32" and (stdout_obj is None or not stdout_obj.isatty()):
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
    except Exception as e:
        logger.warning(f"Could not suppress console: {e}")


def _check_dependencies() -> bool:
    missing: list[str] = []

    try:
        import openpyxl  # noqa: F401
    except ImportError:
        missing.append("openpyxl")

    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")

    if missing:
        logger.error(f"Missing dependencies: {', '.join(missing)}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Missing Dependencies",
            "Required packages are missing:\n"
            + "\n".join(f"- {name}" for name in missing)
            + "\n\nInstall with:\n"
            + ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt",
        )
        root.destroy()
        return False

    return True


def main() -> None:
    """Main entry point with error handling."""
    try:
        logger.info("Checking dependencies...")
        if not _check_dependencies():
            logger.error("Dependency check failed")
            sys.exit(1)

        logger.info("Starting login window...")
        from .ui.login import LoginWindow
        from .ui.app import ShopifyERPApp

        login = LoginWindow()
        if not login.authenticated:
            logger.info("User cancelled login")
            sys.exit(0)

        logger.info("Starting main application...")
        app = ShopifyERPApp()
        app.mainloop()
        logger.info("Application closed normally")
        
    except Exception as e:
        logger.exception(f"Fatal error in main: {e}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Fatal Error",
            f"An unexpected error occurred:\n\n{str(e)}\n\n"
            "Please check the log file for details.",
        )
        root.destroy()
        sys.exit(1)


if __name__ == "__main__":
    main()
