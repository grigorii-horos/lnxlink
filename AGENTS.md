# Repository Guidelines

## Project Structure & Module Organization
`lnxlink/` contains the Python package and entrypoint (`__main__.py`) plus core services like `mqtt.py` and `system_monitor.py`. Feature modules live in `lnxlink/modules/` and are loaded dynamically; helper scripts sit in `lnxlink/modules/scripts/`. Packaging/configuration lives in `pyproject.toml` and `setup.cfg`. Assets are under `images/`. Deployment helpers include `Dockerfile`, `docker-compose.yaml`, and `install.sh`.

## Build, Test, and Development Commands
- `pip install -e .` installs the package in editable mode for local development.
- `python -m lnxlink --config lnxlink_config/lnxlink.yaml` runs the service from source (same as `lnxlink --config ...` once installed).
- `lnxlink --setup --config lnxlink.yaml` creates/updates the config only; `lnxlink --moduleselector --config lnxlink.yaml` runs the module selection wizard.
- `docker build -t lnxlink .` builds the container image; `docker compose up` runs the Docker setup if you are using it.

## Coding Style & Naming Conventions
Use 4-space indentation and standard Python naming: `snake_case` for modules/functions/variables and `CapWords` for classes. Keep new modules in `lnxlink/modules/` with descriptive `snake_case.py` filenames. Linting is configured via `setup.cfg` for `flake8` (E501 is ignored), so keep line lengths reasonable but focus on readability.

## Testing Guidelines
There is no dedicated test suite in this repo. Validate changes with a local run (`lnxlink --config ...`) and, if relevant, by checking MQTT behavior with `--logging DEBUG`. If you add tests, document how to run them here.

## Commit & Pull Request Guidelines
Commit messages are short, descriptive summaries; they sometimes use a `fix:` prefix and often include issue references like `#223`. Keep commits focused and reference related issues in the message or PR description. PRs should include a concise summary, the validation performed (commands or manual checks), and any config/schema changes; include screenshots or logs when behavior is user-visible.

## Configuration Notes
The default config path is `lnxlink_config/lnxlink.yaml`. Running without `--ignore-systemd` will attempt to set up a SystemD service; call it out in your PR if you change startup or service behavior.
