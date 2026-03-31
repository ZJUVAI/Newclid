# Discovery Pipeline 快速上手指南

5分钟快速开始使用 GeoDiscovery 知识发现 pipeline。

## 前置条件

```bash
# 1. 激活conda环境
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery

# 2. 验证环境
which python  # 应显示 .../miniconda3/envs/Discovery/bin/python
python -c "import newclid; print('OK')"  # 应输出 OK

# 3. 进入项目目录
cd /C20545/home/duzhengtong/GeoDiscovery
```

## 快速开始

### 方式1: 使用一键脚本（推荐）

```bash
# 使用现有100k数据运行完整pipeline
./scripts/run_discovery_pipeline.sh

# 查看帮助
./scripts/run_discovery_pipeline.sh --help
```

**输出目录**: `outputs/experiments/YYYYMMDD_HHMMSS_full_pipeline/`

### 方式2: 使用Python脚本

```bash
# 运行完整pipeline（提取 + 规约）
python scripts/discovery_pipeline.py \
    -i datasets/geometry_clauses10_samples100k/geometry_clauses10_samples100k.jsonl \
    -o outputs/experiments/$(date +%Y%m%d)_01_my_experiment \
    --save-intermediates
```

## 常用场景

### 场景1: 快速测试（1k数据）

```bash
# 生成1k测试数据
python src/newclid/generation/generate.py \
    --n_clauses 10 --aux_only 1 --n_threads 10 --n_samples 1000 \
    --dir datasets/test_1k

# 运行pipeline
python scripts/discovery_pipeline.py \
    -i datasets/test_1k/geometry_clauses10_samples1k.jsonl \
    -o outputs/experiments/test_1k_run \
    --save-intermediates
```

**预计耗时**: ~5分钟

### 场景2: 仅规则提取（跳过规约）

```bash
python scripts/discovery_pipeline.py \
    -i datasets/geometry_clauses10_samples100k/geometry_clauses10_samples100k.jsonl \
    -o outputs/experiments/$(date +%Y%m%d)_01_extraction_only \
    --skip-reduction --save-intermediates
```

### 场景3: 仅规则评估（使用已有规则）

```bash
python scripts/evaluate_rules.py evaluate \
    --rules outputs/experiments/20260310_01_10k_normalized_extraction_reduction/extracted_rules.txt \
    --baseline-cache outputs/eval_baselines/ \
    --output outputs/eval_results/$(date +%Y%m%d)_01_my_eval \
    --workers 30
```

## 查看结果

### 提取结果

```bash
# 查看提取的规则
head -20 outputs/experiments/YYYYMMDD_XX_experiment/*_pruned_rules.txt

# 查看中间统计
cat outputs/experiments/YYYYMMDD_XX_experiment/intermediates/step6_rules_stats.json | jq
```

### 规约结果

```bash
# 查看最终规则
head -20 outputs/experiments/YYYYMMDD_XX_experiment/extracted_rules.txt

# 查看规约统计
cat outputs/experiments/YYYYMMDD_XX_experiment/reduction_stats.json | jq
```

### 评估结果

```bash
# 查看对比报告
cat outputs/eval_results/YYYYMMDD_XX_eval/jgex_ag_231_comparison.json | jq
```

## 下一步

- 阅读 [完整参考手册](discovery_pipeline.md) 了解详细原理
- 查看 [数据格式参考](data_formats.md) 了解数据结构
- 参考 [故障排查](discovery_pipeline.md#故障排查) 解决问题

## 常见问题

**Q: 如何使用自己的数据？**

A: 将数据转换为JSONL格式（参见 `data_formats.md`），然后使用 `-i` 参数指定路径。

**Q: 如何调整并行度？**

A: 使用 `--max-workers` 参数（提取）或 `--workers` 参数（评估），推荐设为 CPU核心数 × 1.5。

**Q: 如何跳过某个阶段？**

A: 使用 `--skip-extraction` 或 `--skip-reduction` 参数。

**Q: 如何查看详细日志？**

A: 日志文件位于输出目录下，如 `outputs/experiments/.../extraction.log`。

**Q: 遇到错误怎么办？**

A: 查看 [故障排查](discovery_pipeline.md#故障排查) 章节，或查看 `docs/tiny_error_records.md` 中的历史问题。
