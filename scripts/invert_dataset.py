import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps
from tqdm import tqdm


DEFAULT_BASE_DIR = Path("datasets")
DEFAULT_SRC_IMG_DIR = DEFAULT_BASE_DIR / "imgs_png"
DEFAULT_SRC_JSONL = (
    DEFAULT_BASE_DIR / "geometry_clauses10_samples1M.jsonl"
)


def derive_inverted_path(path: Path) -> Path:
    if path.suffix:
        return path.with_name(f"{path.stem}_inverted{path.suffix}")
    return path.parent / f"{path.name}_inverted"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Invert dataset images and update image paths inside a JSONL file."
    )
    parser.add_argument(
        "--src-img-dir",
        type=Path,
        default=DEFAULT_SRC_IMG_DIR,
        help="Source image directory.",
    )
    parser.add_argument(
        "--dst-img-dir",
        type=Path,
        default=None,
        help="Destination image directory. Defaults to src dir with '_inverted' suffix.",
    )
    parser.add_argument(
        "--src-jsonl",
        type=Path,
        default=DEFAULT_SRC_JSONL,
        help="Source JSONL file.",
    )
    parser.add_argument(
        "--dst-jsonl",
        type=Path,
        default=None,
        help="Destination JSONL file. Defaults to src jsonl with '_inverted' suffix.",
    )
    parser.add_argument(
        "--old-path-str",
        default=None,
        help="Original path prefix to replace in JSONL. Defaults to --src-img-dir.",
    )
    parser.add_argument(
        "--new-path-str",
        default=None,
        help="New path prefix to write in JSONL. Defaults to --dst-img-dir.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=int(os.environ.get("MAX_JOBS", 0)) or None,
        help="Maximum worker count for image inversion. Defaults to MAX_JOBS env or all CPU cores.",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip image inversion and only update JSONL.",
    )
    parser.add_argument(
        "--skip-jsonl",
        action="store_true",
        help="Skip JSONL update and only invert images.",
    )
    return parser.parse_args()


def invert_image_file(file_info):
    """
    读取图片，反色(保留 Alpha 通道)，并保存到新位置。
    """
    src_path, dst_path = file_info

    try:
        with Image.open(src_path) as img:
            if img.mode == "RGBA":
                r, g, b, a = img.split()
                rgb_img = Image.merge("RGB", (r, g, b))
                inverted_rgb = ImageOps.invert(rgb_img)
                r_inv, g_inv, b_inv = inverted_rgb.split()
                img_out = Image.merge("RGBA", (r_inv, g_inv, b_inv, a))
            elif img.mode == "LA":
                lum, a = img.split()
                l_inv = ImageOps.invert(lum)
                img_out = Image.merge("LA", (l_inv, a))
            else:
                img_out = ImageOps.invert(img.convert("RGB"))

            img_out.save(dst_path)
            return True
    except Exception as exc:
        print(f"Error processing {src_path}: {exc}")
        return False


def invert_images(src_img_dir: Path, dst_img_dir: Path, max_jobs: int | None):
    if not src_img_dir.exists():
        raise FileNotFoundError(f"Source image directory not found: {src_img_dir}")

    dst_img_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created or verified directory: {dst_img_dir}")

    print("Scanning image files...")
    image_files = list(src_img_dir.glob("*.png"))
    tasks = [(img_path, dst_img_dir / img_path.name) for img_path in image_files]

    print(f"Found {len(tasks)} images. Starting inversion...")
    if max_jobs:
        print(f"Using MAX_JOBS={max_jobs} workers")

    with ProcessPoolExecutor(max_workers=max_jobs) as executor:
        results = list(
            tqdm(executor.map(invert_image_file, tasks), total=len(tasks), unit="img")
        )

    success_count = sum(results)
    print(
        f"Image processing complete. Success: {success_count}, Failed: {len(results) - success_count}"
    )


def update_jsonl(
    src_jsonl: Path,
    dst_jsonl: Path,
    old_path_str: str,
    new_path_str: str,
):
    print(f"Processing JSONL file: {src_jsonl}")

    if not src_jsonl.exists():
        raise FileNotFoundError(f"Source JSONL not found: {src_jsonl}")

    dst_jsonl.parent.mkdir(parents=True, exist_ok=True)

    line_count = 0
    with (
        open(src_jsonl, "r", encoding="utf-8") as f_in,
        open(dst_jsonl, "w", encoding="utf-8") as f_out,
    ):
        for line in tqdm(f_in, desc="Updating JSONL"):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                if "image_path" in data:
                    data["image_path"] = data["image_path"].replace(
                        old_path_str, new_path_str
                    )

                if "image_path_no_annotations" in data:
                    data["image_path_no_annotations"] = data[
                        "image_path_no_annotations"
                    ].replace(old_path_str, new_path_str)

                f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                line_count += 1
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON line: {line[:50]}...")

    print("JSONL processing complete.")
    print(f"Saved {line_count} lines to: {dst_jsonl}")


def main():
    args = parse_args()

    if args.skip_images and args.skip_jsonl:
        raise ValueError("Cannot use --skip-images and --skip-jsonl at the same time.")

    args.dst_img_dir = args.dst_img_dir or derive_inverted_path(args.src_img_dir)
    args.dst_jsonl = args.dst_jsonl or derive_inverted_path(args.src_jsonl)

    old_path_str = args.old_path_str or args.src_img_dir.as_posix()
    new_path_str = args.new_path_str or args.dst_img_dir.as_posix()

    if not args.skip_images:
        invert_images(args.src_img_dir, args.dst_img_dir, args.max_jobs)

    if not args.skip_jsonl:
        update_jsonl(args.src_jsonl, args.dst_jsonl, old_path_str, new_path_str)


if __name__ == "__main__":
    main()
