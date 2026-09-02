Follow the CONVENTIONS.md and the naming-things guidelines.

Apps must not import or otherwise know of the concrete implementation of
their dependents. Dependencies must flow in a single direction. The
enforcing contracts live in `pyproject.toml` (`[tool.importlinter]`).
