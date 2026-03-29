import os
import re
import shutil
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "tiff", "tif", "bmp", "gif", "webp",
    "docx", "xlsx", "txt", "md", "csv", "rtf",
}


def get_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in ("jpg", "jpeg", "png", "tiff", "tif", "bmp", "gif", "webp"):
        return "image"
    if ext == "pdf":
        return "pdf"
    if ext == "docx":
        return "docx"
    if ext == "xlsx":
        return "xlsx"
    if ext in ("txt", "md", "csv", "rtf"):
        return "text"
    return "unknown"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"_+", "_", name).strip("_. ")
    return name or "unnamed"


def ensure_unique_path(filepath: str) -> str:
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"


def move_file(src: str, dest_dir: str, filename: str | None = None) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    if filename is None:
        filename = os.path.basename(src)
    dest = os.path.join(dest_dir, filename)
    dest = ensure_unique_path(dest)
    shutil.move(src, dest)
    return dest


def list_folders(base_dir: str) -> list[str]:
    if not os.path.exists(base_dir):
        return []
    return sorted([
        d for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d)) and not d.startswith(".")
    ])


def get_file_size(filepath: str) -> int:
    try:
        return os.path.getsize(filepath)
    except OSError:
        return 0
