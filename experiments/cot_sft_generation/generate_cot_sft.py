import os
import json
import argparse
import re
import base64
import mimetypes
import logging
import time
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

logger = logging.getLogger(__name__)


def configure_logging(log_path=None):
    """Configure console logging and optionally mirror logs to a file."""
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_path is not None:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


configure_logging()

def validate_cot_format(output_text, expected_aux):
    """
    严格验证 CoT 输出格式。

    要求:
    1. 必须包含 <thinking>...</thinking> 标签
    2. 必须包含 <aux>...</aux> 标签
    3. <thinking> 必须在 <aux> 之前
    4. <aux> 内容必须与预期的 aux 完全匹配（去除首尾空格）
    5. 不能包含 <proof> 标签（只要 aux，不要完整证明）
    6. <thinking> 内容不能为空，至少要有 50 个字符

    Returns:
        tuple: (is_valid, error_message)
    """
    if not output_text:
        return False, "Output is None or empty"

    # 检查是否包含 <proof> 标签（不应该有）
    if "<proof>" in output_text:
        return False, "Output contains <proof> tag - should only contain <thinking> and <aux>"

    # 检查 <thinking> 标签
    thinking_match = re.search(r'<thinking>(.*?)</thinking>', output_text, re.DOTALL)
    if not thinking_match:
        return False, "Missing or malformed <thinking>...</thinking> tags"

    thinking_content = thinking_match.group(1).strip()
    if len(thinking_content) < 50:
        return False, f"<thinking> content too short ({len(thinking_content)} chars, minimum 50)"

    # 检查 <aux> 标签
    aux_match = re.search(r'<aux>(.*?)</aux>', output_text, re.DOTALL)
    if not aux_match:
        return False, "Missing or malformed <aux>...</aux> tags"

    # 检查标签顺序：<thinking> 必须在 <aux> 之前
    thinking_pos = output_text.find("<thinking>")
    aux_pos = output_text.find("<aux>")
    if thinking_pos > aux_pos:
        return False, "<thinking> must appear before <aux>"

    # 验证 <aux> 内容是否与预期匹配
    aux_content = aux_match.group(1).strip()
    expected_aux_content = re.search(r'<aux>(.*?)</aux>', expected_aux, re.DOTALL)
    if expected_aux_content:
        expected_content = expected_aux_content.group(1).strip()
        if aux_content != expected_content:
            return False, f"<aux> content mismatch - expected exact match with provided aux"

    return True, "Valid format"

# 初始化客户端
# 从环境变量读取 API 的令牌和基础 URL
# 设置方法: export ZJUVAI_API_KEY="sk-xxxxxx"
# 设置方法: export ZJUVAI_BASE_URL="https://api.zjuqx.cn/v1"  # 可选，如果不设置则使用默认值
client = OpenAI(
    api_key=os.getenv("ZJUVAI_API_KEY"),
    base_url=os.getenv("ZJUVAI_BASE_URL", "https://api.zjuqx.cn/v1"),
)

# 默认模型名称
DEFAULT_MODEL_NAME = "qwen/qwen3.5-plus-02-15"
SCRIPT_DIR = Path(__file__).resolve().parent


def build_default_output_jsonl():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return SCRIPT_DIR / "generated" / timestamp / "cot_sft_dataset.jsonl"


def _encode_image_base64(image_path: str) -> str:
    """将本地图片编码为 base64 data URL，供 DashScope API 使用。"""
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        mime_type = "image/png"
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def ensure_parent_dir(file_path):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)


def build_run_dir(output_jsonl):
    output_path = Path(output_jsonl)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = output_path.stem or "cot_sft"
    return output_path.parent / f"{stem}_artifacts_{timestamp}"


def write_json(file_path, data):
    ensure_parent_dir(file_path)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(file_path, records):
    ensure_parent_dir(file_path)
    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_run_manifest(args_dict, output_jsonl, run_dir, model_name):
    return {
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": os.path.abspath(__file__),
        "cwd": os.getcwd(),
        "model_name": model_name,
        "api_base_url": os.getenv("ZJUVAI_BASE_URL", "https://api.zjuqx.cn/v1"),
        "output_jsonl": os.path.abspath(output_jsonl),
        "run_dir": os.path.abspath(run_dir),
        "arguments": args_dict,
    }

def generate_cot_text_only(problem, aux_part, rest_of_proof, model_name, verbose=False, max_retries=3):
    """
    调用 Qwen API（纯文本模式），传入分离后的 aux 和 proof，生成专注推导 aux 的思维链。

    Args:
        max_retries: 最大重试次数（默认3次）
    """
    prompt_text = (
        "You are an expert in geometry and formal mathematics. I will provide you with a formal problem description, the required auxiliary constructions (aux) that need to be discovered, and the rest of the formal proof for context.\n"
        "Your task is to simulate the FORWARD thinking process of discovering these specific auxiliary constructions. You must act as if you are solving the problem from scratch. Analyze the problem description, identify the missing links or bottlenecks in reaching the goal, and naturally deduce that these exact auxiliary points, lines, or relations are required to proceed.\n\n"
        
        "[Predicate Definitions (Dictionary)]:\n"
        "- cong a b c d: Length of segment AB equals CD (AB = CD).\n"
        "- perp a b c d: Line AB is perpendicular to CD (AB ⊥ CD).\n"
        "- para a b c d: Line AB is parallel to CD (AB || CD).\n"
        "- coll a b c: Points A, B, and C are collinear.\n"
        "- cyclic a b c d: Points A, B, C, and D are concyclic points.\n"
        "- eqangle a b c d e f g h: The directed angle from line AB to line CD equals the directed angle from line EF to line GH. Note: ab, cd, ef, gh represent LINES. The angle is defined as the counter-clockwise rotation required to map the first line to the second line.\n"
        "- eqratio a b c d e f g h: The ratio of lengths AB/CD = EF/GH.\n"
        "- aconst a b c d x: The directed angle from line AB to line CD is equal to x, where x is in [0, 180). Measured by rotating line AB counter-clockwise to line CD.\n"
        "- rconst a b c d y: The ratio of lengths AB:CD = y, where y is a constant.\n\n"
        
        "[Important Constraints]:\n"
        "1. FORWARD REASONING ONLY: Write your <thinking> as a genuine, step-by-step mathematical discovery. Do not retroactively explain or prematurely reveal the final aux; let it be the natural conclusion of your analysis.\n"
        "2. NO ID LEAKAGE & TRANSLATE LOGIC (CRITICAL): Never output bracketed IDs (e.g., [015]) inside <thinking>. You may read the future proof for dependencies, but MUST translate them into natural geometric language (e.g., say 'Since AI = AD', not 'From [014]').\n"
        "3. NO META-TALK: Act entirely as a mathematician. Never mention prompt instructions, the 'required aux', or state that you are 'simulating' the process.\n"
        "4. FOCUS ON DISCOVERY: Center your reasoning on the journey of finding the aux. You may mention the ultimate goal for intuition, but do not narrate the routine steps of the rest of the proof.\n"
        "5. SYMBOL CONSISTENCY: Use standard geometric notation in your <thinking> (e.g., AB ⊥ AC), but strictly maintain the original point names (a, b, c) provided in the problem.\n"
        "6. EXACT AUX BLOCK: Output your reasoning within <thinking>...</thinking> tags first, followed ONLY by the EXACT <aux>...</aux> block provided, completely unchanged. Do not append the remaining proof.\n\n"
        
        "Now solve the following problem. Follow all constraints above exactly, and output only <thinking>...</thinking> followed by the exact <aux>...</aux> block.\n\n"
        f"[Formal Problem]\n{problem}\n\n"
        f"[Required Auxiliary Elements]\n{aux_part}\n\n"
        f"[Rest of the Formal Proof (for context)]\n{rest_of_proof}\n\n"
        "Do not output <proof>, <numerical_check>, or any extra text.\n"
        "[Output]\n"
    )

    if verbose:
        logger.info(f"\n{'='*60}")
        logger.info(f"[Mode] Text-only")
        logger.info(f"[Full Prompt]\n{prompt_text}")
        logger.info(f"{'='*60}\n")

    messages = [
        {
            "role": "user",
            "content": prompt_text
        }
    ]

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[Text-only mode] Attempt {attempt}/{max_retries}")
            t_start = time.time()
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=4096,
                temperature=0.3,
            )
            elapsed = time.time() - t_start
            logger.info(f"[API Response Time] {elapsed:.2f}s")

            output = response.choices[0].message.content

            # 验证输出格式
            is_valid, error_msg = validate_cot_format(output, aux_part)
            if is_valid:
                logger.info(f"[Text-only mode] Valid output on attempt {attempt}")
                return {
                    "success": True,
                    "output": output,
                    "prompt_text": prompt_text,
                    "attempts_used": attempt,
                    "error": None,
                    "elapsed_seconds": elapsed,
                }
            else:
                last_error = error_msg
                logger.warning(f"[Text-only mode] Attempt {attempt} failed validation: {error_msg}")
                if attempt < max_retries:
                    logger.info(f"[Text-only mode] Retrying...")
                    time.sleep(1)  # 短暂延迟避免过快重试
                else:
                    logger.error(f"[Text-only mode] All {max_retries} attempts failed validation")
                    return {
                        "success": False,
                        "output": output,
                        "prompt_text": prompt_text,
                        "attempts_used": attempt,
                        "error": error_msg,
                        "elapsed_seconds": elapsed,
                    }

        except Exception as e:
            last_error = str(e)
            logger.error(f"[Text-only mode] Attempt {attempt} API call failed: {e}")
            if attempt < max_retries:
                logger.info(f"[Text-only mode] Retrying after API error...")
                time.sleep(2)  # API 错误后稍长延迟
            else:
                logger.error(f"[Text-only mode] All {max_retries} attempts failed due to API errors")
                return {
                    "success": False,
                    "output": None,
                    "prompt_text": prompt_text,
                    "attempts_used": attempt,
                    "error": str(e),
                    "elapsed_seconds": None,
                }

    return {
        "success": False,
        "output": None,
        "prompt_text": prompt_text,
        "attempts_used": max_retries,
        "error": last_error or "Unknown error",
        "elapsed_seconds": None,
    }

def generate_cot_with_vision(problem, aux_part, rest_of_proof, image_path, model_name, verbose=False, max_retries=3):
    """
    调用 Qwen 多模态 API，传入分离后的 aux 和 proof，生成专注推导 aux 的思维链。

    Args:
        max_retries: 最大重试次数（默认3次）
    """
    if not os.path.exists(image_path):
        logger.warning(f"[Vision mode] Image not found at {image_path}. Skipping this item.")
        return {
            "success": False,
            "output": None,
            "prompt_text": None,
            "attempts_used": 0,
            "error": f"Image not found at {image_path}",
            "elapsed_seconds": None,
        }

    prompt_text = (
        "You are an expert in geometry and formal mathematics. I will provide you with an image of a geometry problem, its formal problem description, the target auxiliary constructions (aux) that need to be discovered, and the rest of the formal proof for context.\n"
        "Your task is to simulate the FORWARD thinking process of discovering these specific auxiliary constructions. You must act as if you are solving the problem from scratch. Analyze the image and the problem description, identify the missing links or bottlenecks in reaching the goal, and naturally deduce that these exact auxiliary points, lines, or relations are required to proceed.\n\n"
        "[Predicate Definitions (Dictionary)]:\n"
        "- cong a b c d: Length of segment AB equals CD (AB = CD).\n"
        "- perp a b c d: Line AB is perpendicular to CD (AB ⊥ CD).\n"
        "- para a b c d: Line AB is parallel to CD (AB || CD).\n"
        "- coll a b c: Points A, B, and C are collinear.\n"
        "- cyclic a b c d: Points A, B, C, and D are concyclic points.\n"
        "- eqangle a b c d e f g h: The directed angle from line AB to line CD equals the directed angle from line EF to line GH. Note: ab, cd, ef, gh represent LINES. The angle is defined as the counter-clockwise rotation required to map the first line to the second line.\n"
        "- eqratio a b c d e f g h: The ratio of lengths AB/CD = EF/GH.\n"
        "- aconst a b c d x: The directed angle from line AB to line CD is equal to x, where x is in [0, 180). Measured by rotating line AB counter-clockwise to line CD.\n"
        "- rconst a b c d y: The ratio of lengths AB:CD = y, where y is a constant.\n\n"
        "[Important Constraints]:\n"
        "1. VISUAL INTUITION FIRST: You must heavily rely on the provided image. Start your thinking process by visually inspecting the geometric figure. What visual relationships, symmetries, intersections, or alignments suggest the need for extra lines or points? Let the visual evidence naturally drive the formal mathematical deduction of the aux.\n"
        "2. FORWARD REASONING ONLY: Your <thinking> process must NOT read like a retroactive explanation of the provided aux. It must read like a genuine, step-by-step mathematical discovery. Do not reveal or state the final aux constructions early in your thoughts; let them be the natural, inevitable conclusion of your visual and logical analysis.\n"
        "3. NO FUTURE ID LEAKAGE (CRITICAL): You are strictly forbidden from referencing step IDs (e.g., [015], [016]) in your <thinking> that only appear in the [Rest of the Formal Proof]. You must act as if you haven't seen the future proof yet. When citing IDs to support your logic, you may ONLY use the IDs explicitly present in the [Formal Problem] block.\n"
        "4. Focus your reasoning entirely on the journey of finding the necessary aux. You can briefly consider the ultimate goal of the proof to guide your intuition, but do not narrate or explain the routine deductive steps of the rest of the proof.\n"
        "5. Strictly use the original symbols, logical terms, and step numbers exactly as they appear in the problem statement.\n"
        "6. Your output format MUST be: first, output your step-by-step reasoning process enclosed strictly within <thinking>...</thinking> tags. Then, output ONLY the EXACT <aux>...</aux> block I provided, completely unchanged. Do NOT output the rest of the proof.\n\n"
        f"[Formal Problem]\n{problem}\n\n"
        f"[Target Auxiliary Constructions (to be naturally discovered)]\n{aux_part}\n\n"
        f"[Rest of the Formal Proof (for context)]\n{rest_of_proof}\n\n"
        "Please generate the forward-thinking discovery process, strongly guided by the visual image, followed by the exact aux block."
    )

    if verbose:
        logger.info(f"\n{'='*60}")
        logger.info(f"[Image Path] {os.path.abspath(image_path)}")
        logger.info(f"[Full Prompt]\n{prompt_text}")
        logger.info(f"{'='*60}\n")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": _encode_image_base64(image_path)}
                },
                {
                    "type": "text",
                    "text": prompt_text
                }
            ]
        }
    ]

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[Vision mode] Attempt {attempt}/{max_retries}")
            t_start = time.time()
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=4096,
                temperature=0.3,
            )
            elapsed = time.time() - t_start
            logger.info(f"[API Response Time] {elapsed:.2f}s")

            output = response.choices[0].message.content

            # 验证输出格式
            is_valid, error_msg = validate_cot_format(output, aux_part)
            if is_valid:
                logger.info(f"[Vision mode] Valid output on attempt {attempt}")
                return {
                    "success": True,
                    "output": output,
                    "prompt_text": prompt_text,
                    "attempts_used": attempt,
                    "error": None,
                    "elapsed_seconds": elapsed,
                }
            else:
                last_error = error_msg
                logger.warning(f"[Vision mode] Attempt {attempt} failed validation: {error_msg}")
                if attempt < max_retries:
                    logger.info(f"[Vision mode] Retrying...")
                    time.sleep(1)  # 短暂延迟避免过快重试
                else:
                    logger.error(f"[Vision mode] All {max_retries} attempts failed validation")
                    return {
                        "success": False,
                        "output": output,
                        "prompt_text": prompt_text,
                        "attempts_used": attempt,
                        "error": error_msg,
                        "elapsed_seconds": elapsed,
                    }

        except Exception as e:
            last_error = str(e)
            logger.error(f"[Vision mode] Attempt {attempt} API call failed: {e}")
            if attempt < max_retries:
                logger.info(f"[Vision mode] Retrying after API error...")
                time.sleep(2)  # API 错误后稍长延迟
            else:
                logger.error(f"[Vision mode] All {max_retries} attempts failed due to API errors")
                return {
                    "success": False,
                    "output": None,
                    "prompt_text": prompt_text,
                    "attempts_used": attempt,
                    "error": str(e),
                    "elapsed_seconds": None,
                }

    return {
        "success": False,
        "output": None,
        "prompt_text": prompt_text,
        "attempts_used": max_retries,
        "error": last_error or "Unknown error",
        "elapsed_seconds": None,
    }

def process_and_generate_sft(input_jsonl, output_jsonl, sample_size=3, num_workers=4, mode="vision", model_name=DEFAULT_MODEL_NAME, verbose=False, random_sample=True, process_all=False, max_retries=3, run_metadata=None, run_dir=None):
    """
    读取指定 jsonl 文件，抽取包含 aux 的数据，分离 aux 和 proof，多线程生成 SFT 数据。

    Args:
        mode: "vision" 使用带图片的生成流程，"text" 使用纯文本生成流程
        verbose: 是否输出详细的 prompt 信息
        random_sample: True 为随机抽取，False 为顺序抽取
        process_all: True 为处理所有数据，False 为按 sample_size 抽取
        max_retries: 每个样本的最大重试次数（默认3次）
    """
    if not os.path.exists(input_jsonl):
        logger.error(f"The input file '{input_jsonl}' does not exist.")
        return

    if run_dir is None:
        run_dir = build_run_dir(output_jsonl)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"
    configure_logging(log_path)
    logger.info(f"Run artifacts will be stored in {run_dir}")

    if run_metadata is not None:
        write_json(run_dir / "run_config.json", run_metadata)

    start_time = time.time()

    logger.info(f"Reading {input_jsonl} ...")
    all_aux_data = []
    with open(input_jsonl, 'r', encoding='utf-8') as f:
        for line_idx, line in enumerate(f):
            if line.strip():
                data = json.loads(line.strip())
                data["_source_index"] = line_idx
                formal_output = data.get("llm_output_renamed", "")
                if "<aux>" in formal_output:
                    all_aux_data.append(data)

    logger.info(f"Found {len(all_aux_data)} items containing <aux> in total.")

    if process_all:
        extracted_data = all_aux_data
        logger.info(f"Processing all {len(all_aux_data)} items.")
    elif len(all_aux_data) < sample_size:
        logger.warning(f"Only found {len(all_aux_data)} items containing <aux>, less than requested {sample_size}. Using all.")
        extracted_data = all_aux_data
    else:
        if random_sample:
            extracted_data = random.sample(all_aux_data, sample_size)
            logger.info(f"Randomly sampled {sample_size} items.")
        else:
            extracted_data = all_aux_data[:sample_size]
            logger.info(f"Sequentially selected first {sample_size} items.")

    sampled_records = []
    for i, data in enumerate(extracted_data):
        sampled_records.append({
            "sample_order": i,
            "input_index": data.get("_source_index"),
            "image_path": data.get("image_path", ""),
            "n_premises": data.get("n_premises"),
            "n_proof_steps": data.get("n_proof_steps"),
            "llm_input_renamed": data.get("llm_input_renamed", ""),
            "llm_output_renamed": data.get("llm_output_renamed", ""),
        })

    if verbose:
        write_jsonl(run_dir / "sampled_inputs.jsonl", sampled_records)

    def process_item(idx_data):
        i, data = idx_data
        logger.info(f"Processing item {i+1}/{len(extracted_data)}...")

        problem_input = data.get("llm_input_renamed", "")
        formal_output = data.get("llm_output_renamed", "")
        img_path = data.get("image_path", "")

        aux_match = re.search(r'(<aux>.*?</aux>)', formal_output, re.DOTALL)
        if not aux_match:
            logger.warning(f"[Item {i+1}] Aux extraction failed - no <aux>...</aux> tags found in llm_output_renamed, skipping.")
            return {
                "result_data": None,
                "item_record": {
                    "sample_order": i,
                    "input_index": data.get("_source_index"),
                    "mode": mode,
                    "instruction": None,
                    "input": problem_input,
                    "expected_aux": None,
                    "rest_of_proof_sanitized": None,
                    "image_path": img_path,
                    "prompt_text": None,
                    "output": None,
                    "success": False,
                    "attempts_used": 0,
                    "error": "Aux extraction failed - no <aux>...</aux> tags found",
                    "elapsed_seconds": None,
                },
            }

        aux_part = aux_match.group(1).strip()
        rest_of_proof = formal_output.replace(aux_part, "").strip()

        # delete all the id and rule names
        rest_of_proof = re.sub(r' \[\d{3}\]', '', rest_of_proof)  # remove [012] style IDs
        rest_of_proof = re.sub(r' (r\d+|AR)\b', '', rest_of_proof)  # remove r63, AR style rules

        # 根据模式选择生成函数
        if mode == "vision":
            generation_result = generate_cot_with_vision(problem_input, aux_part, rest_of_proof, img_path, model_name, verbose, max_retries)
            instruction = "Solve the geometry problem by analyzing the image and problem description. Provide a step-by-step thinking process focused on finding necessary auxiliary constructions (aux), followed by the aux constructions."
            result_data = {
                "instruction": instruction,
                "input": problem_input,
                "output": generation_result["output"],
                "image_path": img_path,
                "_order": i,
            }
        else:  # mode == "text"
            generation_result = generate_cot_text_only(problem_input, aux_part, rest_of_proof, model_name, verbose, max_retries)
            instruction = "Solve the geometry problem by analyzing the problem description. Provide a step-by-step thinking process focused on finding necessary auxiliary constructions (aux), followed by the aux constructions."
            result_data = {
                "instruction": instruction,
                "input": problem_input,
                "output": generation_result["output"],
                "_order": i,
            }

        item_record = {
            "sample_order": i,
            "input_index": data.get("_source_index"),
            "mode": mode,
            "instruction": instruction,
            "input": problem_input,
            "expected_aux": aux_part,
            "rest_of_proof_sanitized": rest_of_proof,
            "image_path": img_path,
            "prompt_text": generation_result["prompt_text"],
            "output": generation_result["output"],
            "success": generation_result["success"],
            "attempts_used": generation_result["attempts_used"],
            "error": generation_result["error"],
            "elapsed_seconds": generation_result["elapsed_seconds"],
        }

        if generation_result["success"]:
            logger.info(f"Item {i+1} processed successfully!")
            return {
                "result_data": result_data,
                "item_record": item_record,
            }
        else:
            logger.warning(f"[Item {i+1}] Failed to generate CoT - API returned None (check error logs above for details), skipping.")
            return {
                "result_data": None,
                "item_record": item_record,
            }

    sft_dataset = []
    item_records = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_item, (i, data)): i for i, data in enumerate(extracted_data)}
        for future in as_completed(futures):
            result = future.result()
            item_records.append(result["item_record"])
            if result["result_data"] is not None:
                sft_dataset.append(result["result_data"])

    # 按原始顺序排序后移除辅助字段
    sft_dataset.sort(key=lambda x: x["_order"])
    for item in sft_dataset:
        item.pop("_order")

    item_records.sort(key=lambda x: x["sample_order"])

    logger.info(f"Writing {len(sft_dataset)} results to {output_jsonl} ...")
    ensure_parent_dir(output_jsonl)
    with open(output_jsonl, 'w', encoding='utf-8') as f:
        for item in sft_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    if verbose:
        write_jsonl(run_dir / "item_records.jsonl", item_records)

    summary = {
        "total_candidates_with_aux": len(all_aux_data),
        "sampled_items": len(extracted_data),
        "successful_items": len(sft_dataset),
        "failed_items": len(extracted_data) - len(sft_dataset),
        "mode": mode,
        "random_sample": random_sample,
        "max_retries": max_retries,
        "num_workers": num_workers,
        "output_jsonl": os.path.abspath(output_jsonl),
        "artifacts_dir": os.path.abspath(run_dir),
        "runtime_seconds": time.time() - start_time,
    }
    write_json(run_dir / "summary.json", summary)

    logger.info("SFT dataset generation completed!")
    logger.info(f"Run summary saved to {run_dir / 'summary.json'}")

    return {
        "output_jsonl": os.path.abspath(output_jsonl),
        "run_dir": os.path.abspath(run_dir),
        "summary": summary,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate CoT SFT dataset (AUX only).")
    default_output_jsonl = build_default_output_jsonl()

    # /C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples5M_aux_updated_img512_inverted_remove_proof_task12.jsonl
    parser.add_argument("-i", "--input", type=str, required=True, help="Path to the input raw geometry .jsonl file.")
    parser.add_argument(
        "-o", "--output", type=str, default=str(default_output_jsonl),
        help="Path where the generated SFT .jsonl file will be saved. "
             f"Default: {default_output_jsonl}"
    )
    parser.add_argument("-n", "--num_samples", type=int, default=3, help="Number of samples to extract and process (default: 3).")
    parser.add_argument("-w", "--num_workers", type=int, default=4, help="Number of parallel threads for API calls (default: 4).")
    parser.add_argument("-m", "--mode", type=str, choices=["vision", "text"], default="vision",
                        help="Generation mode: 'vision' for image-based generation, 'text' for text-only generation (default: vision).")
    parser.add_argument("--model_name", type=str, default=DEFAULT_MODEL_NAME,
                        help=f"Model name used for API generation (default: {DEFAULT_MODEL_NAME}).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging (show full prompts).")
    parser.add_argument("--sequential", action="store_true", help="Use sequential sampling instead of random sampling.")
    parser.add_argument("-r", "--max_retries", type=int, default=3, help="Maximum number of retries per sample if validation fails (default: 3).")

    args = parser.parse_args()
    args_dict = vars(args).copy()
    run_dir = build_run_dir(args.output)
    run_metadata = build_run_manifest(args_dict, args.output, run_dir, args.model_name)

    process_and_generate_sft(args.input, args.output, sample_size=args.num_samples, num_workers=args.num_workers,
                             mode=args.mode, model_name=args.model_name, verbose=args.verbose, random_sample=not args.sequential,
                             max_retries=args.max_retries, run_metadata=run_metadata, run_dir=run_dir)
