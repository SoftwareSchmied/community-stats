"""Build the HACS release archive and reject unexpected source files."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components" / "community_stats"
ALLOWED = {".py", ".json", ".png"}


def main() -> None:
    destination = ROOT / "dist" / "community_stats.zip"
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if path.is_file() and path.suffix in ALLOWED and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(SOURCE).as_posix())
        archive.write(ROOT / "LICENSE", "LICENSE")
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert "manifest.json" in archive.namelist()
        assert "brand/icon.png" in archive.namelist()
    print(destination)


if __name__ == "__main__":
    main()
