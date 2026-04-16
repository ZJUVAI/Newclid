# Standard Commands

本文档是 GeoDiscovery 常用操作的权威命令手册。

## Authority

- 对于本页覆盖的常用操作，agent 必须使用这里的标准命令块。
- 允许替换的内容仅限本页显式定义的占位符或变量值。
- 不允许自行增加、删减或改写 flags，不允许把这些标准命令替换成临时 one-liner。
- 如果某个任务需要新的稳定命令变体，先更新本页，再把它作为新标准命令使用。

## Standard Environment Preamble

除非用户明确要求别的环境，所有标准命令都先执行：

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
```

## Allowed Placeholders

| 占位符 | 含义 |
|--------|------|
| `<INPUT_JSONL>` | 输入 JSONL 数据文件 |
| `<EXP_DIR>` | 实验输出目录，通常位于 `outputs/experiments/` 下 |
| `<RULES_FILE>` | 规则文件，通常为 `extracted_rules.txt` 或 `extracted_rules_maxprem7.txt` |
| `<SOURCE_DATA_JSON>` | `step6_rules_stats.json` |
| `<EVAL_DIR>` | 评估输出目录 |
| `<DATA_DIR>` | 数据生成输出目录 |

## 1. Data Generation

### 1.1 快速测试 1k 数据

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python src/newclid/generation/generate.py \
    --n_clauses 10 \
    --n_threads 10 \
    --n_samples 1000 \
    --aux_only 1 \
    --log_level info \
    --timeout 3600 \
    --dir datasets/test_1k
```

### 1.2 标准 100k aux 数据生成

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python src/newclid/generation/generate.py \
    --n_clauses 10 \
    --n_threads 30 \
    --n_samples 100000 \
    --aux_only 1 \
    --log_level info \
    --timeout 3600 \
    --dir <DATA_DIR>
```

### 1.3 标准 220k 数据生成

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python src/newclid/generation/generate.py \
    --n_threads 30 \
    --n_samples 220000 \
    --log_level info \
    --timeout 3600 \
    --dir <DATA_DIR>
```

## 2. Discovery Pipeline

### 2.1 一键完整 pipeline（推荐默认入口）

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
./scripts/run_discovery_pipeline.sh
```

### 2.2 Python 版完整提取 + 规约

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/discovery_pipeline.py \
    -i <INPUT_JSONL> \
    -o <EXP_DIR> \
    --max-workers 30 \
    --save-intermediates \
    --skip-predicates eqpoint,constline \
    --rule-skip-predicates aconst,rconst \
    --timeout 60 \
    --seed 42 \
    --max-premises 7 \
    --batch-size 10
```

### 2.3 Python 版仅规则提取

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/discovery_pipeline.py \
    -i <INPUT_JSONL> \
    -o <EXP_DIR> \
    --max-workers 30 \
    --save-intermediates \
    --skip-predicates eqpoint,constline \
    --rule-skip-predicates aconst,rconst \
    --skip-reduction
```

### 2.4 Python 版仅规则规约

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/discovery_pipeline.py \
    -o <EXP_DIR> \
    --skip-extraction \
    --rules <RULES_FILE> \
    --source-data <SOURCE_DATA_JSON> \
    --max-workers 30 \
    --timeout 60 \
    --seed 42 \
    --max-premises 7 \
    --batch-size 10
```

### 2.5 CSolver 版仅规则规约

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/discovery_pipeline_c.py \
    -o <EXP_DIR> \
    --skip-extraction \
    --rules <RULES_FILE> \
    --source-data <SOURCE_DATA_JSON> \
    --max-workers 30 \
    --timeout 60 \
    --seed 42 \
    --max-premises 7 \
    --batch-size 10 \
    --engine full
```

## 3. Rule Evaluation

### 3.1 Python solver baseline

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/evaluate_rules.py baseline \
    --output outputs/eval_baselines/ \
    --benchmarks hageo_409,imo_95,jgex_ag_231 \
    --workers 30 \
    --timeout 3600
```

### 3.2 Python solver evaluate

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/evaluate_rules.py evaluate \
    --rules <RULES_FILE> \
    --baseline-cache outputs/eval_baselines/ \
    --output <EVAL_DIR> \
    --benchmarks hageo_409,imo_95,jgex_ag_231 \
    --workers 30 \
    --timeout 600 \
    --skip-baseline-solved
```

### 3.3 CSolver baseline

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/evaluate_rules_csolver.py baseline \
    --output outputs/eval_baselines_csolver/ \
    --benchmarks hageo_409,jgex_ag_231 \
    --workers 30 \
    --timeout 600 \
    --engine full
```

### 3.4 CSolver evaluate

```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
cd /C20545/home/duzhengtong/GeoDiscovery
python scripts/evaluate_rules_csolver.py evaluate \
    --rules <RULES_FILE> \
    --baseline-cache outputs/eval_baselines_csolver/ \
    --output <EVAL_DIR> \
    --benchmarks hageo_409,jgex_ag_231 \
    --workers 30 \
    --timeout 600 \
    --skip-baseline-solved \
    --engine full
```

## 4. Deviation Rule

只有以下情况允许偏离本页命令：

- 用户明确指定了不同参数或不同脚本
- 当前任务不属于本页覆盖的 routine 操作
- 代码或 CLI 已经变更，现有标准命令失效，此时必须先更新本文档
