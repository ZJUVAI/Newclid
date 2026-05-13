#!/usr/bin/env python3
"""
从原始数据集中随机选取样本，反转图片，并准备元数据。
"""
import argparse
import json
import random
from pathlib import Path
from PIL import Image, ImageOps
from tqdm import tqdm

EXPERIMENT_DIR = Path(__file__).parent
DEFAULT_METADATA_DIR = EXPERIMENT_DIR / "metadata"
DEFAULT_OUTPUT_JSONL = DEFAULT_METADATA_DIR / "metadata.jsonl"
DEFAULT_NUM_SAMPLES = 100
DEFAULT_RANDOM_SEED = 42


def invert_image(src_path, dst_path):
    """反转图片（保留Alpha通道）"""
    try:
        with Image.open(src_path) as img:
            if img.mode == 'RGBA':
                r, g, b, a = img.split()
                rgb_img = Image.merge('RGB', (r, g, b))
                inverted_rgb = ImageOps.invert(rgb_img)
                r_inv, g_inv, b_inv = inverted_rgb.split()
                img_out = Image.merge('RGBA', (r_inv, g_inv, b_inv, a))
            elif img.mode == 'LA':
                l, a = img.split()
                l_inv = ImageOps.invert(l)
                img_out = Image.merge('LA', (l_inv, a))
            else:
                img_out = ImageOps.invert(img.convert('RGB'))

            img_out.save(dst_path)
            return True
    except Exception as e:
        print(f"Error processing {src_path}: {e}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sample geometry items and generate local metadata assets."
    )
    parser.add_argument(
        "--src-jsonl",
        type=Path,
        required=True,
        help="Path to the source dataset JSONL file.",
    )
    parser.add_argument(
        "--src-img-dir",
        type=Path,
        required=True,
        help="Directory containing source PNG images.",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=DEFAULT_METADATA_DIR,
        help=f"Directory to store generated metadata assets. Default: {DEFAULT_METADATA_DIR}",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=DEFAULT_OUTPUT_JSONL,
        help=f"Path to the generated metadata JSONL. Default: {DEFAULT_OUTPUT_JSONL}",
    )
    parser.add_argument(
        "-n",
        "--num-samples",
        type=int,
        default=DEFAULT_NUM_SAMPLES,
        help=f"Maximum number of samples to select. Default: {DEFAULT_NUM_SAMPLES}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"Random seed for sampling. Default: {DEFAULT_RANDOM_SEED}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    src_jsonl = args.src_jsonl.resolve()
    src_img_dir = args.src_img_dir.resolve()
    metadata_dir = args.metadata_dir.resolve()
    output_jsonl = args.output_jsonl.resolve()
    img_dir = metadata_dir / "images"

    if not src_jsonl.exists():
        raise FileNotFoundError(f"Source JSONL not found: {src_jsonl}")
    if not src_img_dir.exists():
        raise FileNotFoundError(f"Source image directory not found: {src_img_dir}")
    if args.num_samples <= 0:
        raise ValueError("--num-samples must be a positive integer")

    # 创建输出目录
    metadata_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading from: {src_jsonl}")
    print(f"Source images: {src_img_dir}")
    print(f"Output to: {metadata_dir}")

    # 第一步：扫描所有存在的图片
    print("Scanning existing images...")
    existing_images = set(img.name for img in src_img_dir.glob("*.png"))
    print(f"Found {len(existing_images)} existing images")

    # 第二步：随机选取图片
    random.seed(args.seed)
    selected_images = random.sample(list(existing_images), min(args.num_samples, len(existing_images)))
    print(f"Selected {len(selected_images)} images")

    # 第三步：读取所有数据并建立图片名到数据的映射
    print("Building image-to-data mapping...")
    image_to_data = {}
    with open(src_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    img_path = data.get('image_path', '')
                    if img_path:
                        img_filename = Path(img_path).name
                        # 保存第一条匹配的数据（可能有重复）
                        if img_filename not in image_to_data:
                            image_to_data[img_filename] = data
                except json.JSONDecodeError:
                    pass

    print(f"Mapped {len(image_to_data)} unique images to data")

    # 第四步：处理选中的图片和对应的数据
    processed_count = 0
    failed_count = 0
    no_data_count = 0

    with open(output_jsonl, 'w', encoding='utf-8') as f_out:
        for idx, img_filename in enumerate(tqdm(selected_images, desc="Processing samples")):
            try:
                src_img_path = src_img_dir / img_filename

                # 获取对应的数据
                if img_filename not in image_to_data:
                    no_data_count += 1
                    continue

                data = image_to_data[img_filename]

                # 生成新的图片文件名
                new_img_name = f"sample_{processed_count:04d}.png"
                dst_img_path = img_dir / new_img_name

                # 反转图片
                if not invert_image(src_img_path, dst_img_path):
                    failed_count += 1
                    continue

                # 更新数据中的图片路径
                data['image_path'] = f"metadata/images/{new_img_name}"
                if 'image_path_no_annotations' in data:
                    data['image_path_no_annotations'] = f"metadata/images/{new_img_name}"

                # 写入输出 JSONL
                f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                processed_count += 1

            except Exception as e:
                print(f"Error processing image {img_filename}: {e}")
                failed_count += 1

    print(f"\nProcessing complete!")
    print(f"Successfully processed: {processed_count}")
    print(f"No corresponding data: {no_data_count}")
    print(f"Failed: {failed_count}")
    print(f"Output JSONL: {output_jsonl}")
    print(f"Output images: {img_dir}")


if __name__ == "__main__":
    main()
