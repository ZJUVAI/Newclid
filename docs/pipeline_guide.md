# GenesisGeo-GRPO 完整流程指南

最后更新：2026-04-27

---

## 概览

GenesisGeo-GRPO 是一个几何定理证明的强化学习训练流程，包含：
1. 数据生成（合成几何问题）
2. 数据标注与筛选（难度评估）
3. GRPO 训练（强化学习）
4. 评估（IMO/JGEX 等基准测试）

---

## 1. 数据生成

### 1.1 基础数据生成

**脚本**：`src/newclid/generation/pipeline.py`

**命令示例**：
```bash
python src/newclid/generation/pipeline.py \
  --n_clauses 10 \
  --n_samples 1000000 \
  --n_threads 40 \
  --max_auxiliary_points 8 \
  --aux_only 2 \
  --dir datasets/0123 \
  --img 2 \
  --prune \
  --seed_cache
```

**关键参数**：
- `--n_clauses`：每个问题的最大构造子句数（默认 15）
- `--n_samples`：生成问题总数（默认 10000）
- `--max_auxiliary_points`：每个问题的最大辅助点数（默认 2）
- `--aux_only`：过滤模式（0=全部，1=10%非辅助，2=仅辅助）
- `--img`：图像模式（0=无，1=标注，2=纯净，3=两者）
- `--dir`：输出目录（默认 `./datasets`）

**输出**：
- 位置：`datasets/YYYYMMDD/`
- 文件：`geometry_clauses{N}_samples{M}_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
- 格式：每行一个 JSON 对象，包含：
  - `query`：XML 格式的谓词问题
  - `fl_problem`：函数式语言格式（带坐标）
  - `response`：辅助构造 DSL
  - `llm_input_renamed` / `llm_output_renamed`：重命名版本

**数据源**：
- 定义：`src/newclid/configs/default_defs.txt`
- 规则：`src/newclid/configs/default_rules.txt`

---

## 2. 数据标注与筛选

### 2.1 构建候选池

**脚本**：`scripts/grpo/build_candidate_pool.py`

**命令示例**：
```bash
python scripts/grpo/build_candidate_pool.py \
  datasets/0123/geometry_clauses10_samples1M.jsonl \
  datasets/grpo_geometry100k_candidate_pool.jsonl \
  --target-size 100000
```

**输出字段**：
- `sample_id`, `query`, `fl_problem`, `response`
- `goal_predicate`, `predicate_family_tags`
- `aux_segment_count`, `aux_points_total`
- `n_premises`, `problem_predicate_count`, `problem_clause_count`

### 2.2 难度标注（VLM）

**脚本**：`scripts/grpo/label_difficulty_vlm.py`

**命令示例**：
```bash
python scripts/grpo/label_difficulty_vlm.py \
  datasets/grpo_geometry100k_candidate_pool.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  --model-path /C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084 \
  --num-samples 16 \
  --batch-size 4 \
  --num-workers 40
```

**关键参数**：
- `--model-path`：VLM 模型路径（用于评估难度）
- `--num-samples`：每个问题采样次数（默认 16，用于计算 pass@16）
- `--batch-size`：GPU 批次大小
- `--num-workers`：Ray 并行度

**输出字段**（新增）：
- `pass_at_16`：16 次采样的通过率
- `greedy_success`：贪婪解码是否成功
- `valid_ratio`：有效构造占比
- `proxy_reward_std`：奖励标准差（衡量难度多样性）

### 2.3 选择训练集

**脚本**：`scripts/grpo/select_debug_set.py`

**命令示例**：
```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN_bucket_unified_Nk_vXX/grpo_train_selected_N000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN_bucket_unified_Nk_vXX/grpo_train_report_N000.json \
  --selection-policy bucket_unified \
  --target-size N000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --near-high-mid-max-pass 0.75 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --reward-mixed-zero-max-fraction 0.20 \
  --near-high-mid-min-fraction 0.03 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0
```

**常用配置**：
- v16/v17: `--target-size 2000/5000`, `--reward-mixed-zero-max-fraction 0.20`
- v18 (10k): `--target-size 10000`, `--reward-mixed-zero-max-fraction 0.15`（降低零通过率样本比例）

**选择策略**：
- `bucket_unified`：当前主线策略
- `v10_auxfix_stage_balanced`：阶段平衡策略
- 其他：`v3_tiered`, `v4_reward_mixed`, `v6_mid_strict_zero`, `v7_structure_strict_zero`

**分桶逻辑**（bucket_unified）：
- `core`：中等难度（pass@16 ∈ [0.125, 0.625]）
- `near_low`：低通过率边界（pass@16 ∈ [0.0625, 0.125)）
- `reward_mixed_zero`：零通过但有信号（pass@16=0，但 valid_ratio>0.25，proxy_reward_std>0.15）
- `near_high_mid`：高通过率边界（pass@16 ∈ (0.625, 0.75]）
- `mastered`：过于简单（pass@16 > 0.75）

### 2.4 准备 GRPO 训练数据

**脚本**：`scripts/grpo/prepare_grpo_aux_dataset.py`

**命令示例**：
```bash
python scripts/grpo/prepare_grpo_aux_dataset.py \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN_bucket_unified_Nk_vXX/grpo_train_selected_N000.jsonl \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN_bucket_unified_Nk_vXX/grpo_train.jsonl
```

**输出格式**：
```json
{"query": "<problem>...</problem>", "fl_problem": "...", "response": "<aux>...</aux>"}
```

---

## 3. GRPO 训练

### 3.1 基础模型

**路径**：`/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`

这是 SFT 预训练的 VLM 模型，作为 GRPO 的起点。

### 3.2 训练脚本

**入口**：`scripts/grpo/train_grpo.sh`

**命令示例**：
```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 \
NPROC_PER_NODE=4 \
MODEL_PATH="/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084" \
DATASET_PATH="datasets/<dataset_dir>/grpo_train_selected_N000.jsonl" \
OUTPUT_DIR="models/<output_dir>" \
NUM_GENERATIONS=8 \
TEMPERATURE=1.1 \
TOP_P=0.95 \
TOP_K=0 \
MAX_COMPLETION_LENGTH=256 \
BETA=0.02 \
REWARD_LOG_INTERVAL=20 \
bash scripts/grpo/train_grpo.sh \
  --tuner_type lora \
  --lora_rank 8 \
  --lora_alpha 32 \
  --lora_dropout 0.05 \
  --target_modules all-linear \
  --freeze_vit true \
  --freeze_aligner true \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 8 \
  --learning_rate 5e-6 \
  --warmup_steps 10 \
  --lr_scheduler_type cosine \
  --weight_decay 0.1 \
  --max_grad_norm 1.0 \
  --bf16 true \
  --gradient_checkpointing true \
  --logging_steps 5 \
  --logging_first_step true \
  --save_steps 50 \
  --max_steps 500
```

**注意**：`DATASET_PATH` 直接指向 `grpo_train_selected_N000.jsonl`，不需要额外的 `prepare_grpo_aux_dataset.py` 步骤（`train_grpo.sh` 内部会处理格式转换）。

### 3.3 关键参数

**模型与数据**：
- `MODEL_PATH`：基础模型路径
- `DATASET_PATH`：训练数据 JSONL（直接指向 `grpo_train_selected_N000.jsonl`）
- `OUTPUT_DIR`：模型保存目录

**GRPO 超参数**：
- `NUM_GENERATIONS`：每个 prompt 生成的候选数（推荐 8）
- `TEMPERATURE`：采样温度（推荐 1.1，提高探索性）
- `TOP_P`：nucleus 采样阈值（推荐 0.95）
- `TOP_K`：top-k 采样（推荐 0，即不限制，配合 top_p 使用）
- `MAX_COMPLETION_LENGTH`：最大生成长度（推荐 256）
- `BETA`：KL 惩罚系数（推荐 0.02，低惩罚有助于探索）

**训练配置**：
- `learning_rate`：学习率（推荐 5e-6，基于 SFT 阶段 1e-5 的 1/2）
- `warmup_steps`：预热步数（推荐 10）
- `lr_scheduler_type`：学习率调度器（推荐 cosine）
- `per_device_train_batch_size`：每卡批次大小（推荐 1）
- `gradient_accumulation_steps`：梯度累积步数（推荐 8）
- `max_steps`：最大训练步数（推荐 500）
- `save_steps`：保存间隔（推荐 50）

**Effective batch size 计算**：
```
generation_batch_size = per_device_train_batch_size × num_processes × gradient_accumulation_steps
                      = 1 × 4 × 8 = 32 problems/step（4 卡 DDP）
```

**奖励配置**（环境变量）：
- `NEWCLID_GRPO_SOLVED_REWARD`：正确证明（默认 1.0）
- `NEWCLID_GRPO_VALID_REWARD`：有效但不完整（默认 0.25）
- `NEWCLID_GRPO_INVALID_BUILD_REWARD`：无效构造（默认 -0.25）
- `NEWCLID_GRPO_INVALID_FORMAT_REWARD`：格式错误（默认 -1.0）
- `NEWCLID_GRPO_ENGINE_ERROR_REWARD`：引擎崩溃（默认 0.0）

### 3.4 输出

**模型保存**：
- 位置：`models/{OUTPUT_DIR}/v0-{timestamp}/`
- 文件：
  - `checkpoint-{step}/`：模型权重
  - `logging.jsonl`：训练日志
  - `args.json`：训练参数
  - `run_metadata.json`：运行元数据

**训练日志字段**：
- `reward`：平均奖励
- `reward_std`：奖励标准差
- `frac_reward_zero_std`：零方差样本占比
- `kl`：KL 散度
- `loss`：训练损失

---

## 4. 评估

### 4.1 评估脚本

**入口**：`scripts/evaluation.py`

**命令示例（dev_imo）**：
```bash
python scripts/evaluation.py \
  --problems_path benchmarks/dev_imo.txt \
  --model_path models/<output_dir>/v0-<timestamp>/checkpoint-<N> \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --max_workers 40 \
  --enable_trace \
  --log_dir results/<experiment_name>
```

**命令示例（imo_95）**：
```bash
python scripts/evaluation.py \
  --problems_path benchmarks/imo_95.txt \
  --model_path models/<output_dir>/v0-<timestamp>/checkpoint-<N> \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --max_workers 40 \
  --enable_trace \
  --log_dir results/<experiment_name>
```

**注意**：两个评估不能同时运行（共享 Ray cluster），需顺序执行。如果评估中途因 Ray 崩溃中断，使用 `scripts/resume_eval_progress.py` 从已完成的 trace 恢复。

### 4.2 关键参数

**基础配置**：
- `--problems_path`：基准测试文件路径
- `--model_path`：模型 checkpoint 路径
- `--agent`：代理类型（`lm`, `vlm`, `qwen3_vl_text` 等）
- `--log_dir`：结果输出目录（默认 `./results`）

**搜索配置**：
- `--decoding_size`：每个 beam 节点的候选数（推荐 32）
- `--beam_size`：深度间的最大候选数（推荐 512）
- `--search_depth`：辅助扩展轮数（推荐 4）

**性能配置**：
- `--timeout`：每个问题的超时时间（默认 3600s）
- `--max_workers`：Ray CPU 容量（推荐 40）

**输出配置**：
- `--enable_trace`：写入每个问题的 trace JSONL（推荐开启，用于断点续跑）

### 4.3 基准测试

**位置**：`benchmarks/`

| 文件 | 描述 | 题数 |
|------|------|------|
| `dev_imo.txt` | IMO 开发集 | 16 |
| `imo_95.txt` | IMO-95 | 95 |
| `imo_30.txt` | IMO-30 | 30 |
| `imo_ag_30.txt` | IMO-AG-30 | 30 |
| `hageo_409.txt` | HAGeo-409 | 409 |
| `jgex_231.txt` | JGEX-231 | 231 |
| `jgex_ag_231.txt` | JGEX-AG-231 | 231 |
| `larger_imo_eval.txt` | 扩展 IMO 集 | - |

**格式**：每两行一个问题
```
problem_name
problem_definition_in_fl_format
```

### 4.4 输出

**位置**：`results/`

**文件结构**：
```
results/
├── eval_single_problem_multi_gpu_vlm_dev_imo_{run_id}.csv  # 汇总 CSV
├── eval_single_problem_multi_gpu_vlm_dev_imo_{run_id}/     # 详细结果
│   ├── problems/                                            # 每题 trace
│   │   ├── 0000_translated_imo_2000_p6.jsonl
│   │   ├── 0001_translated_imo_2004_p1.jsonl
│   │   └── ...
│   ├── attempts/                                            # 尝试记录
│   └── run_meta.json                                        # 运行元数据
```

**CSV 格式**：
```csv
"Dataset: dev_imo, Solved: 14/16, Total Time: 4668.07s"
Problem Name,Solved,Time (s)
translated_imo_2000_p6,√,13.06
translated_imo_2004_p1,√,5.06
...
```

**Trace JSONL 事件**：
- `problem_start` / `problem_end`：问题开始/结束
- `depth_start` / `depth_end`：深度开始/结束
- `candidate_transition`：候选转换（包含 `construction_text`）
- `ddar_submit` / `ddar_result`：DDAR 提交/结果
- `gpu_batch_submitted` / `gpu_batch_done`：GPU 批次提交/完成

---

## 5. 目录结构

```
/C20545/home/wangzi/GenesisGeo-grpo/
├── datasets/                          # 生成的训练数据
│   ├── 0123/                          # 原始生成数据（1M）
│   ├── grpo_geometry100k_*/           # 候选池与标注
│   └── grpo_geometry100k_*_vXX/       # 各版本训练集
├── models/                            # 训练的模型
│   └── grpo_vlm_sft44_*_vXX_*/        # 各版本模型
├── results/                           # 评估结果
│   └── vXX_lr5e6_checkpointN/         # 各版本评估
├── benchmarks/                        # 基准测试集
│   ├── dev_imo.txt
│   ├── imo_95.txt
│   └── ...
├── scripts/                           # 脚本
│   ├── grpo/                          # GRPO 流程脚本
│   │   ├── train_grpo.sh              # 训练入口
│   │   ├── select_debug_set.py        # 数据选择
│   │   ├── label_difficulty_vlm.py    # VLM 标注
│   │   └── build_candidate_pool.py    # 构建候选池
│   ├── evaluation.py                  # 评估入口
│   └── resume_eval_progress.py        # 断点续跑
├── src/newclid/                       # 核心代码
│   ├── generation/                    # 数据生成
│   ├── training/                      # 训练工具
│   └── agent/                         # 推理代理
└── docs/                              # 文档
    ├── grpo_pipeline_optimization_plan.md  # 实验记录
    └── pipeline_guide.md                   # 流程指南
```

---

## 6. 外部数据路径

**基础模型**：
- SFT baseline：`/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`

**原始数据源**：
- 1M 生成数据：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`

---

## 7. 完整流程示例

### Step 1: 数据生成（已完成）
```bash
# 原始 1M 数据已生成
# 位置：/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/
```

### Step 2: 构建候选池
```bash
python scripts/grpo/build_candidate_pool.py \
  /C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN/candidate_pool.jsonl \
  --target-size 100000
```

### Step 3: VLM 标注
```bash
python scripts/grpo/label_difficulty_vlm.py \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN/candidate_pool.jsonl \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN/difficulty_labels.jsonl \
  --model-path /C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084 \
  --num-samples 16 \
  --batch-size 4 \
  --num-workers 40
```

### Step 4: 选择训练集
```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN_bucket_unified_Nk_vXX/grpo_train_selected_N000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN_bucket_unified_Nk_vXX/grpo_train_report_N000.json \
  --selection-policy bucket_unified \
  --target-size N000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --mastered-max-fraction 0.0
```

### Step 5: GRPO 训练
```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 \
NPROC_PER_NODE=4 \
MODEL_PATH="/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084" \
DATASET_PATH="datasets/grpo_geometry100k_vlm_label_YYYYMMDD_maxauxN_bucket_unified_Nk_vXX/grpo_train_selected_N000.jsonl" \
OUTPUT_DIR="models/grpo_vlm_sft44_geometry100k_vXX_s1_4gpu_lr5e6" \
NUM_GENERATIONS=8 \
TEMPERATURE=1.1 \
TOP_P=0.95 \
TOP_K=0 \
MAX_COMPLETION_LENGTH=256 \
BETA=0.02 \
bash scripts/grpo/train_grpo.sh \
  --learning_rate 5e-6 \
  --warmup_steps 10 \
  --lr_scheduler_type cosine \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 8 \
  --max_steps 500 \
  --save_steps 50
```

### Step 6: 评估 dev_imo
```bash
python scripts/evaluation.py \
  --problems_path benchmarks/dev_imo.txt \
  --model_path models/grpo_vlm_sft44_geometry100k_vXX_s1_4gpu_lr5e6/v0-<timestamp>/checkpoint-500 \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --max_workers 40 \
  --enable_trace \
  --log_dir results/vXX_lr5e6_checkpoint500
```

### Step 7: 评估 imo_95
```bash
python scripts/evaluation.py \
  --problems_path benchmarks/imo_95.txt \
  --model_path models/grpo_vlm_sft44_geometry100k_vXX_s1_4gpu_lr5e6/v0-<timestamp>/checkpoint-500 \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --max_workers 40 \
  --enable_trace \
  --log_dir results/vXX_lr5e6_checkpoint500
```

---

## 8. 常见问题

**Q: 如何调整训练集大小？**
A: 修改 `select_debug_set.py` 的 `--target-size` 参数（例如：2000, 5000, 10000）

**Q: 如何调整学习率？**
A: 修改 `train_grpo.sh` 的 `--learning_rate` 参数（推荐 5e-6）

**Q: 如何增加训练步数？**
A: 修改 `train_grpo.sh` 的 `--max_steps` 参数（推荐 500）

**Q: 如何使用不同的基础模型？**
A: 修改 `MODEL_PATH` 环境变量指向新的 checkpoint

**Q: 评估结果在哪里？**
A: `results/` 目录下，CSV 文件包含汇总，子目录包含详细 trace

**Q: 如何对比两个版本？**
A: 使用 `scripts/grpo/compare_imo95_versions.py` 或 `scripts/grpo/analyze_proposal_distribution.py`

**Q: 评估中途 Ray 崩溃怎么办？**
A: 使用 `scripts/resume_eval_progress.py` 从已完成的 trace 恢复，生成剩余题目列表，然后继续评估

**Q: 如何验证 checkpoint-300 vs checkpoint-500？**
A: 分别评估两个 checkpoint 的 dev_imo，对比 solved 数量
