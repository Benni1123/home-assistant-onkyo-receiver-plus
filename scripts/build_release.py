"""Build deterministic manual-install and HACS ZIPs for Onkyo Receiver Plus."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "onkyo_receiver_plus"
COMPONENT = Path("custom_components") / DOMAIN
HACS_ARCHIVE = f"{DOMAIN}.zip"
MANUAL_ARCHIVE = f"{DOMAIN}-ha.zip"
ASSETS = {
    "brand/icon.png", "brand/icon@2x.png", "brand/logo.png", "brand/logo@2x.png",
}
ALLOWED_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".png"}


def build(output: Path, tag: str | None = None) -> list[Path]:
    """Package only integration files, plus source attribution."""
    folder = ROOT / COMPONENT
    manifest = json.loads((folder / "manifest.json").read_bytes())
    hacs = json.loads((ROOT / "hacs.json").read_bytes())
    if manifest.get("domain") != DOMAIN or hacs.get("name") != manifest.get("name"):
        raise ValueError("HA and HACS integration identities do not match.")
    version = manifest.get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-z]+\d+)?", version):
        raise ValueError(f"Unsupported manifest version: {version!r}.")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match manifest version v{version}.")
    if hacs.get("filename") != HACS_ARCHIVE or hacs.get("zip_release") is not True:
        raise ValueError("hacs.json does not point to the generated HACS ZIP.")

    files: dict[str, bytes] = {}
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink: {relative}.")
        if path.is_file() and path.suffix in ALLOWED_SUFFIXES:
            files[relative.as_posix()] = path.read_bytes()
    if missing := {"manifest.json", "__init__.py", *ASSETS} - files.keys():
        raise ValueError(f"Package files missing: {', '.join(sorted(missing))}.")
    for name in ("LICENSE", "NOTICE"):
        files[name] = (ROOT / name).read_bytes()

    output.mkdir(parents=True, exist_ok=True)
    built = []
    for name, prefix in ((MANUAL_ARCHIVE, COMPONENT.as_posix() + "/"), (HACS_ARCHIVE, "")):
        dest = output / name
        with ZipFile(dest, "w", compression=ZIP_DEFLATED) as archive:
            for relative, content in sorted(files.items()):
                info = ZipInfo(prefix + relative)
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content, compress_type=ZIP_DEFLATED, compresslevel=9)
        with ZipFile(dest) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Invalid ZIP: {dest}.")
        built.append(dest)
    sums = output / "SHA256SUMS.txt"
    sums.write_text(
        "".join(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in built),
        encoding="ascii",
        newline="\n",
    )
    return [*built, sums]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--tag", help="Validate a release tag against the manifest version.")
    args = parser.parse_args()
    for path in build(args.output_dir, args.tag):
        print(path)


if __name__ == "__main__":
    main()
