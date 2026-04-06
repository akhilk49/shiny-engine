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

    try:
        controller = Controller.from_config("config.yaml")
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    controller._overlay.show()
    controller._hotkeys.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
