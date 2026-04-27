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

**命令示例（v17 配置）**：
```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_selected_5000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_report_5000.json \
  --selection-policy bucket_unified \
  --target-size 5000 \
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
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_selected_5000.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train.jsonl
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

**命令示例（v17 配置）**：
```bash
export MODEL_PATH="/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084"
export DATASET_PATH="datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train.jsonl"
export OUTPUT_DIR="models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6"
export NUM_GENERATIONS=8
export TEMPERATURE=1.1
export TOP_P=0.95
export TOP_K=0
export MAX_COMPLETION_LENGTH=256
export BETA=0.02
export REWARD_LOG_INTERVAL=5

# 4 卡 DDP 训练
CUDA_VISIBLE_DEVICES=0,1,2,3 \
NPROC_PER_NODE=4 \
bash scripts/grpo/train_grpo.sh \
  --learning_rate 5e-6 \
  --warmup_steps 10 \
  --lr_scheduler_type cosine \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 8 \
  --max_steps 500 \
  --save_steps 50 \
  --logging_steps 1
```

### 3.3 关键参数

**模型与数据**：
- `MODEL_PATH`：基础模型路径
- `DATASET_PATH`：训练数据 JSONL
- `OUTPUT_DIR`：模型保存目录

**GRPO 超参数**：
- `NUM_GENERATIONS`：每个 prompt 生成的候选数（默认 8）
- `TEMPERATURE`：采样温度（v17: 1.1）
- `TOP_P`：nucleus 采样阈值（v17: 0.95）
- `TOP_K`：top-k 采样（v17: 0，即不限制）
- `MAX_COMPLETION_LENGTH`：最大生成长度（v17: 256）
- `BETA`：KL 惩罚系数（v17: 0.02）

**训练配置**：
- `learning_rate`：学习率（v17: 5e-6）
- `warmup_steps`：预热步数（v17: 10）
- `lr_scheduler_type`：学习率调度器（v17: cosine）
- `per_device_train_batch_size`：每卡批次大小（v17: 1）
- `gradient_accumulation_steps`：梯度累积步数（v17: 8）
- `max_steps`：最大训练步数（v17: 500）
- `save_steps`：保存间隔（v17: 50）

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
  --model_path models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/v0-20260423-165556/checkpoint-500 \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --search_version v1 \
  --gpu_batch_size 4 \
  --gpu_batch_timeout_ms 100 \
  --torch_seed 123 \
  --max_workers 40 \
  --enable_trace
```

**命令示例（imo_95）**：
```bash
python scripts/evaluation.py \
  --problems_path benchmarks/imo_95.txt \
  --model_path models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/v0-20260423-165556/checkpoint-500 \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --search_version v1 \
  --gpu_batch_size 2 \
  --gpu_batch_timeout_ms 100 \
  --torch_seed 123 \
  --max_workers 40 \
  --enable_trace
```

### 4.2 关键参数

**基础配置**：
- `--problems_path`：基准测试文件路径
- `--model_path`：模型 checkpoint 路径
- `--agent`：代理类型（`lm`, `vlm`, `qwen3_vl_text` 等）

**搜索配置**：
- `--decoding_size`：每个 beam 节点的候选数（默认 8）
- `--beam_size`：深度间的最大候选数（默认 64）
- `--search_depth`：辅助扩展轮数（默认 4）
- `--search_version`：提示词变体（`v1` 或 `v2`）

**性能配置**：
- `--gpu_batch_size`：每次 GPU 调用的请求数（默认 2）
- `--gpu_batch_timeout_ms`：批次等待预算（默认 100ms）
- `--torch_seed`：随机种子（默认 123）
- `--timeout`：每个问题的超时时间（默认 7200s）
- `--num_gpus_for_eval`：评估使用的 GPU 数（默认 0=全部可见）
- `--max_workers`：Ray CPU 容量（默认 8）

**输出配置**：
- `--enable_trace`：写入每个问题的 trace JSONL
- `--enable_profiling`：写入时间统计 CSV

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
│   └── grpo_geometry100k_*_v17/       # v17 训练集（5k）
├── models/                            # 训练的模型
│   ├── grpo_vlm_sft44_*_v16_*/        # v16 模型
│   └── grpo_vlm_sft44_*_v17_*/        # v17 模型
├── results/                           # 评估结果
│   ├── v16_lr5e6_checkpoint500/       # v16 评估
│   ├── v17_lr5e6_checkpoint500/       # v17 评估
│   └── devimo_grpo_compare/           # 对比评估
├── benchmarks/                        # 基准测试集
│   ├── dev_imo.txt
│   ├── imo_95.txt
│   └── ...
├── scripts/                           # 脚本
│   ├── grpo/                          # GRPO 流程脚本
│   │   ├── train_grpo.sh              # 训练入口
│   │   ├── select_debug_set.py        # 数据选择
│   │   ├── label_difficulty_vlm.py    # VLM 标注
│   │   └── prepare_grpo_aux_dataset.py # 数据准备
│   └── evaluation.py                  # 评估入口
├── src/newclid/                       # 核心代码
│   ├── generation/                    # 数据生成
│   ├── training/                      # 训练工具
│   └── agent/                         # 推理代理
└── docs/                              # 文档
    └── grpo_pipeline_optimization_plan.md
```

---

## 6. 外部数据路径

**基础模型**：
- SFT baseline：`/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`

**原始数据源**：
- 1M 生成数据：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`

---

## 7. 完整流程示例（v17）

### Step 1: 数据生成（已完成）
```bash
# 原始 1M 数据已生成
# 位置：/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/
```

### Step 2: 构建候选池
```bash
python scripts/grpo/build_candidate_pool.py \
  /C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/candidate_pool.jsonl \
  --target-size 100000
```

### Step 3: VLM 标注
```bash
python scripts/grpo/label_difficulty_vlm.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/candidate_pool.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  --model-path /C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084 \
  --num-samples 16 \
  --batch-size 4 \
  --num-workers 40
```

### Step 4: 选择训练集（5k）
```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_selected_5000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_report_5000.json \
  --selection-policy bucket_unified \
  --target-size 5000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --mastered-max-fraction 0.0
```

### Step 5: 准备 GRPO 数据
```bash
python scripts/grpo/prepare_grpo_aux_dataset.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_selected_5000.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train.jsonl
```

### Step 6: GRPO 训练
```bash
export MODEL_PATH="/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084"
export DATASET_PATH="datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train.jsonl"
export OUTPUT_DIR="models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6"
export NUM_GENERATIONS=8
export TEMPERATURE=1.1
export TOP_P=0.95
export TOP_K=0
export MAX_COMPLETION_LENGTH=256
export BETA=0.02

CUDA_VISIBLE_DEVICES=0,1,2,3 NPROC_PER_NODE=4 \
bash scripts/grpo/train_grpo.sh \
  --learning_rate 5e-6 \
  --warmup_steps 10 \
  --lr_scheduler_type cosine \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 8 \
  --max_steps 500 \
  --save_steps 50
```

### Step 7: 评估 dev_imo
```bash
python scripts/evaluation.py \
  --problems_path benchmarks/dev_imo.txt \
  --model_path models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/v0-20260423-165556/checkpoint-500 \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --max_workers 40 \
  --enable_trace
```

### Step 8: 评估 imo_95
```bash
python scripts/evaluation.py \
  --problems_path benchmarks/imo_95.txt \
  --model_path models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/v0-20260423-165556/checkpoint-500 \
  --agent vlm \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --max_workers 40 \
  --enable_trace
```

---

## 8. 常见问题

**Q: 如何调整训练集大小？**
A: 修改 `select_debug_set.py` 的 `--target-size` 参数（v16: 2000, v17: 5000）

**Q: 如何调整学习率？**
A: 修改 `train_grpo.sh` 的 `--learning_rate` 参数（v16/v17: 5e-6）

**Q: 如何增加训练步数？**
A: 修改 `train_grpo.sh` 的 `--max_steps` 参数（v16/v17: 500）

**Q: 如何使用不同的基础模型？**
A: 修改 `MODEL_PATH` 环境变量指向新的 checkpoint

**Q: 评估结果在哪里？**
A: `results/` 目录下，CSV 文件包含汇总，子目录包含详细 trace

**Q: 如何对比两个版本？**
A: 使用 `scripts/grpo/compare_imo95_versions.py` 或 `scripts/grpo/analyze_proposal_distribution.py`
