"""Entry point for the Screen-Aware AI Assistant."""

import os
import sys

# Force CPU-only mode for PyTorch/EasyOCR before any imports
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from PyQt5.QtWidgets import QApplication

from src.controller.controller import Controller
from src.models import ConfigError


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running even if overlay is hidden

    try:
        controller = Controller.from_config("config.yaml")
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    # Keep strong references so Qt doesn't garbage collect them
    app._controller = controller
    app._overlay = controller._overlay

    controller._overlay.show()
    controller._hotkeys.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
