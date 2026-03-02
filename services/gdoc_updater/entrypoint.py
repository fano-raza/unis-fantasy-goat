import os

from GDoc.GDoc_updater import app, ensure_updater_running


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    started = ensure_updater_running()
    print(f"Updater thread started on boot: {started}")

    host = os.getenv("GDOC_UPDATER_HOST", "0.0.0.0")
    port = int(os.getenv("GDOC_UPDATER_PORT", "5000"))
    debug = _as_bool(os.getenv("GDOC_UPDATER_DEBUG", "0"), default=False)

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
