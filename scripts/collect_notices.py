"""Inventory installed dependencies and retain their supplied license/notice texts.

This is an attribution aid, not a license-compliance certification. It excludes
OS packages and container contents, which retain their own package notices.
"""
from importlib.metadata import distributions
import json
from pathlib import Path
import re


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "artifacts/notices"
    output.mkdir(parents=True, exist_ok=True)
    inventory = []

    def save(scope, name, version, license_name, files):
        key = re.sub(r"[^a-zA-Z0-9_.-]", "_", f"{scope}-{name}-{version}")
        retained = []
        for number, path in enumerate(files):
            destination = output / key / f"{number:03d}-{path.name}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
            retained.append(str(destination.relative_to(output)))
        inventory.append({"runtime": scope, "name": name, "version": version,
                          "declared_license": license_name, "notice_files": retained})

    for scope, environment in (("python-api", root / ".venv"),
                               ("python-mcp", root / "infra/mcp-clickhouse/.venv")):
        paths = [str(path) for path in environment.glob("lib/python*/site-packages")]
        for dist in distributions(path=paths):
            files = [Path(dist.locate_file(item)) for item in dist.files or []
                     if ".dist-info/" in str(item)
                     and item.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS"))]
            save(scope, dist.metadata["Name"], dist.version,
                 dist.metadata.get("License-Expression") or dist.metadata.get("License"), files)

    modules = root / "node_modules"
    packages = list(modules.glob("*/package.json")) + list(modules.glob("@*/*/package.json"))
    for package in packages:
        metadata = json.loads(package.read_text())
        files = [path for path in package.parent.iterdir() if path.is_file()
                 and path.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS"))]
        save("npm", metadata.get("name", package.parent.name), metadata.get("version", "unknown"),
             metadata.get("license"), files)
    inventory.sort(key=lambda row: (row["runtime"], row["name"].lower()))
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(json.dumps({"packages": len(inventory), "notice_files": sum(len(row["notice_files"]) for row in inventory),
                      "output": str(output), "scope": "Installed Python/npm packages; not OS/container coverage"}))


if __name__ == "__main__":
    main()
