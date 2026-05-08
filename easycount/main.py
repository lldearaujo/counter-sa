"""Entry point — run with: uvicorn easycount.main:app or python -m easycount.main"""

from __future__ import annotations

import multiprocessing

from easycount.api.app import create_app

# Required on Windows for multiprocessing with 'spawn' start method
multiprocessing.set_start_method("spawn", force=True)

app = create_app()


def main() -> None:
    import uvicorn
    import yaml
    from pathlib import Path

    cfg = {}
    config_path = Path("config/settings.yaml")
    if config_path.exists():
        cfg = yaml.safe_load(config_path.read_text())

    app_cfg = cfg.get("app", {})
    uvicorn.run(
        "easycount.main:app",
        host=app_cfg.get("host", "0.0.0.0"),
        port=app_cfg.get("port", 8000),
        log_level=app_cfg.get("log_level", "info").lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
