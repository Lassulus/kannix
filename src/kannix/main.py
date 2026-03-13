"""Kannix application entry point."""

import uvicorn

from kannix.app import create_app

app = create_app()


def main() -> None:
    """Run the Kannix server."""
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
