"""Main application window — re-export implementation."""

from src.ui.app_impl import App, launch

__all__ = ["App", "launch"]

if __name__ == "__main__":
    launch()
