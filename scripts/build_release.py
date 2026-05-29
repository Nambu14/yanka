#!/usr/bin/env python3
"""Build sdist + wheel and pack them for CI release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

def _platform_slug() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        system = "macos"
    if machine in {"x86_64", "amd64"}:
        machine = "x86_64"
    elif machine in {"aarch64", "arm64"}:
        machine = "arm64"
    return f"{system}-{machine}"


def _write_checksums(bundle_dir: Path) -> None:
    lines: list[str] = []
    for path in sorted(bundle_dir.iterdir()):
        if not path.is_file() or path.name in {"SHA256SUMS.txt", "MANIFEST.txt"}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    (bundle_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _archive_bundle(bundle_dir: Path, archive_path: Path) -> None:
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(bundle_dir.rglob("*")):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(bundle_dir.parent))
        return

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(bundle_dir, arcname=bundle_dir.name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help='Release version (e.g. "0.2.0")')
    parser.add_argument(
        "--output-dir",
        default="release",
        help="Directory for the platform bundle archive (default: release)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "set_version.py"), args.version],
        check=True,
        cwd=root,
    )

    subprocess.run([sys.executable, "-m", "pip", "install", "build"], check=True)

    dist = root / "dist"
    if dist.exists():
        shutil.rmtree(dist)

    subprocess.run([sys.executable, "-m", "build", str(root)], check=True, cwd=root)

    if not dist.is_dir():
        raise SystemExit("dist/ was not created")

    slug = _platform_slug()
    bundle_name = f"yanka-{args.version}-{slug}"
    out_dir = root / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle_dir = out_dir / bundle_name
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    for artifact in sorted(dist.iterdir()):
        if artifact.is_file():
            shutil.copy2(artifact, bundle_dir / artifact.name)

    (bundle_dir / "MANIFEST.txt").write_text(
        "\n".join(
            [
                f"version={args.version}",
                f"platform={slug}",
                f"python={platform.python_version()}",
                "",
                "Artifacts are source/wheel packages from `python -m build`.",
                "Homebrew formulas typically use the .tar.gz sdist; update your tap separately.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_checksums(bundle_dir)

    archive_ext = ".zip" if sys.platform == "win32" else ".tar.gz"
    archive_path = out_dir / f"{bundle_name}{archive_ext}"
    if archive_path.exists():
        archive_path.unlink()
    _archive_bundle(bundle_dir, archive_path)
    print(archive_path)


if __name__ == "__main__":
    main()
