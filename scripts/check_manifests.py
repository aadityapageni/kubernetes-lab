"""Validate YAML syntax and required metadata in the optional Kubernetes labs."""

from pathlib import Path

import yaml


def main():
    paths = sorted(Path("labs").glob("*/*.yaml"))
    checked = 0
    for path in paths:
        if path.name == "monitoring-values.yaml":
            yaml.safe_load(path.read_text())
            continue
        for document in yaml.safe_load_all(path.read_text()):
            if not isinstance(document, dict) or not all(
                key in document for key in ("apiVersion", "kind", "metadata")
            ):
                raise ValueError(f"Invalid Kubernetes resource in {path}")
            checked += 1
    print(f"Validated {checked} optional Kubernetes resources")


if __name__ == "__main__":
    main()
