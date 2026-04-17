import os
import json
from pathlib import Path
from PIL import Image, ImageOps
from scripts._tqdm import tqdm

# ================= 配置路径 =================
# 从环境变量读取最大并行任务数，默认为 None (自动使用所有CPU核心)
MAX_JOBS = int(os.environ.get("MAX_JOBS", 0)) or None

BASE_DIR = Path("datasets/0123")
SRC_IMG_DIR = BASE_DIR / "imgs_png_256"
DST_IMG_DIR = BASE_DIR / "imgs_png_512_inverted"

SRC_JSONL = BASE_DIR / "geometry_clauses10_samples1M_aux_updated_img256.jsonl"
DST_JSONL = BASE_DIR / "geometry_clauses10_samples1M_aux_updated_img512_inverted.jsonl"


# ================= 任务 1: 图片反色函数 =================
def invert_image_file(file_info):
    """
    读取图片，反色(保留Alpha通道)，并保存到新位置
    """
    src_path, dst_path = file_info

    try:
        with Image.open(src_path) as img:
            # 处理带透明度(Alpha)的图片：只反转RGB，保留A
            if img.mode == "RGBA":
                r, g, b, a = img.split()
                rgb_img = Image.merge("RGB", (r, g, b))
                inverted_rgb = ImageOps.invert(rgb_img)
                r_inv, g_inv, b_inv = inverted_rgb.split()
                img_out = Image.merge("RGBA", (r_inv, g_inv, b_inv, a))
            elif img.mode == "LA":  # 灰度+透明
                lum, a = img.split()
                l_inv = ImageOps.invert(lum)
                img_out = Image.merge("LA", (l_inv, a))
            else:
                # 普通 RGB 或 L (灰度)
                img_out = ImageOps.invert(img.convert("RGB"))

            img_out.save(dst_path)
            return True
    except Exception as e:
        print(f"Error processing {src_path}: {e}")
        return False


# ================= 主程序 =================
def main():
    # # 1. 确保输出目录存在
    # if not DST_IMG_DIR.exists():
    #     DST_IMG_DIR.mkdir(parents=True, exist_ok=True)
    #     print(f"Created directory: {DST_IMG_DIR}")

    # # 2. 扫描所有 PNG 图片
    # print("Scanning image files...")
    # image_files = list(SRC_IMG_DIR.glob("*.png"))

    # # 准备任务列表 [(src, dst), ...]
    # tasks = []
    # for img_path in image_files:
    #     dst_path = DST_IMG_DIR / img_path.name
    #     tasks.append((img_path, dst_path))

    # print(f"Found {len(tasks)} images. Starting inversion...")
    # if MAX_JOBS:
    #     print(f"Using MAX_JOBS={MAX_JOBS} workers")

    # # 3. 多进程处理图片 (图像处理是计算密集型，多进程可显著加速)
    # # 通过 MAX_JOBS 环境变量控制并行数，未设置时自动使用所有CPU核心
    # with ProcessPoolExecutor(max_workers=MAX_JOBS) as executor:
    #     results = list(tqdm(executor.map(invert_image_file, tasks), total=len(tasks), unit="img"))

    # print(f"Image processing complete. Success: {sum(results)}, Failed: {len(results) - sum(results)}")

    # # ================= 任务 2: 处理 JSONL =================
    # print(f"Processing JSONL file: {SRC_JSONL}")

    # if not SRC_JSONL.exists():
    #     print(f"Error: Source JSONL not found at {SRC_JSONL}")
    #     return

    # 定义路径替换的字符串
    old_path_str = "datasets/0123/imgs_png_256"
    new_path_str = "datasets/0123/imgs_png_512_inverted"

    line_count = 0
    with (
        open(SRC_JSONL, "r", encoding="utf-8") as f_in,
        open(DST_JSONL, "w", encoding="utf-8") as f_out,
    ):
        for line in tqdm(f_in, desc="Updating JSONL"):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                # 修改 image_path 字段
                if "image_path" in data:
                    # 简单字符串替换，确保路径结构匹配
                    data["image_path"] = data["image_path"].replace(
                        old_path_str, new_path_str
                    )

                if "image_path_no_annotations" in data:
                    # 简单字符串替换，确保路径结构匹配
                    data["image_path_no_annotations"] = data[
                        "image_path_no_annotations"
                    ].replace(old_path_str, new_path_str)

                # 写入新文件
                f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                line_count += 1

            except json.JSONDecodeError:
                print(f"Skipping invalid JSON line: {line[:50]}...")

    print("JSONL processing complete.")
    print(f"Saved {line_count} lines to: {DST_JSONL}")


if __name__ == "__main__":
    main()
