"""Main application window — re-export full implementation."""

from src.ui._app_body import App, launch

__all__ = ["App", "launch"]

if __name__ == "__main__":
    launch()
