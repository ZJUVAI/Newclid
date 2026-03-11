# MAX_AUXILIARY_POINTS 消融实验

## 实验目的

探究数据生成阶段 `max_auxiliary_points` 参数对最终模型性能的影响。该参数控制在几何构造中为每个问题添加的辅助点（如中点、垂足、交点等）的最大数量。

## 实验设计

### 参数设置

| 实验编号 | 模型名称 | `max_auxiliary_points` | 数据量 | 其他参数 |
|---------|---------|----------------------|--------|---------|
| 1 | sft35 | 2 (默认值) | 200k | 统一 |
| 2 | sft36 | 4 | 200k | 统一 |
| 3 | sft37 | 6 | 200k | 统一 |
| 4 | sft38 | 8 | 200k | 统一 |

### 统一参数

**数据生成：**
- `n_clauses`: 10
- `n_threads`: 32
- `aux_only`: 1
- `add_auxiliary`: true
- `prune`: true
- `img`: 0（纯文本，无图像）

**模型训练：**
- 基础模型：`Qwen/Qwen3-0.6B-Base`
- 训练类型：全量微调（full）
- GPU：0, 1, 2（3卡）
- `per_device_train_batch_size`: 7
- `per_device_eval_batch_size`: 3
- 学习率：1e-4
- Epoch：1
- DeepSpeed：zero1

**模型评估：**
- 评估脚本：`scripts/evaluation.py`
- 评估数据集：`dev_imo.txt`, `imo_95_reorder.txt`
- 解码配置：`decoding_size=32, beam_size=512`
- 最大并发数：40 workers

## 异步调度策略

### run_ablation.sh（一站式脚本）

为了最大化资源利用率，实验采用异步流水线调度：

```
时间 →
实验1: [数据生成1] [训练1           ] [评估1]
实验2:             [数据生成2       ] ---等待训练1完成--- [训练2           ] [评估2]
实验3:                               [数据生成3       ] ----等待训练2---- [训练3           ] [评估3]
实验4:                                                  [数据生成4       ] --等待训练3----- [训练4           ] [评估4]
```

**调度规则：**
1. 数据生成仅使用 CPU，可以与 GPU 训练并行执行
2. 训练使用 GPU，同一时刻只有一个训练任务运行（串行）
3. 实验 i 的训练需同时满足两个条件才能开始：
   - 实验 i 的数据生成已完成
   - 实验 i-1 的训练已完成（GPU 已释放）
4. 实验 i 的数据生成在实验 i-1 的训练开始时同步启动
5. 评估在对应实验的训练完成后立即执行

### generate_data.sh + train_and_eval.sh（分步脚本）

**generate_data.sh 调度策略：**
- 串行执行所有数据生成任务（避免 CPU 资源竞争）
- 每个任务使用 32 个 CPU 线程

**train_and_eval.sh 调度策略：**
```
时间 →
实验1: [等待数据] [训练1] [评估1]
实验2: [等待数据]         [训练2] [评估2]
实验3: [等待数据]                 [训练3] [评估3]
实验4: [等待数据]                         [训练4] [评估4]
                  ↑ 训练和评估可以并行
```

**调度规则：**
1. 训练前自动等待数据就绪（检查 `.data_ready` 标记）
2. 训练使用 GPU，同一时刻只有一个训练任务运行
3. 评估使用 CPU，同一时刻只有一个评估任务运行
4. **训练和评估可以并行**（不同资源，例如实验 1 评估时可以同时进行实验 2 训练）

**优势：**
- 数据生成和训练评估可以同时运行（在不同终端）
- 训练与评估并行，提高资源利用率

## 文件结构

```
experiments/max_aux_points_ablation/
├── README.md                          # 本文档
├── run_ablation.sh                    # 一站式运行脚本（数据生成+训练+评估）
├── generate_data.sh                   # 数据生成脚本（仅数据生成）
├── train_and_eval.sh                  # 训练评估脚本（仅训练+评估）
├── data/                              # 生成的数据集
│   ├── sft35_maxaux2/                 # max_aux=2 的数据
│   │   └── geometry_clauses10_samples200K.jsonl
│   ├── sft36_maxaux4/
│   ├── sft37_maxaux6/
│   └── sft38_maxaux8/
└── logs/                              # 实验日志
    ├── sft35_maxaux2/
    │   ├── .data_ready                # 数据生成完成标记（内容为数据集路径）
    │   ├── .train_done                # 训练完成标记
    │   ├── .eval_done                 # 评估完成标记
    │   ├── experiment_config.json     # 实验配置（run_ablation.sh 生成）
    │   ├── data_generation_config.json # 数据生成配置（generate_data.sh 生成）
    │   ├── data_generation.log        # 数据生成日志
    │   ├── dataset_analysis.txt       # 数据集分析
    │   ├── training.log               # 训练日志
    │   └── evaluation.log             # 评估日志
    ├── sft36_maxaux4/
    ├── sft37_maxaux6/
    └── sft38_maxaux8/

models/                                # 训练产出的模型（在项目根目录）
├── sft35/
│   └── checkpoint-XXXXX/
├── sft36/
├── sft37/
└── sft38/
```

## 运行方式

### 方案 1：一站式运行（原始脚本）

```bash
# 从项目根目录运行（自动跳过已完成的阶段，支持断点续跑）
cd /root/GenesisGeo
bash experiments/max_aux_points_ablation/run_ablation.sh

# 强制全部重跑（清除所有完成标记）
bash experiments/max_aux_points_ablation/run_ablation.sh --force
```

### 方案 2：分步运行（推荐）

```bash
# 步骤 1：生成数据（串行执行，避免 CPU 竞争）
bash experiments/max_aux_points_ablation/generate_data.sh

# 步骤 2：训练和评估（训练与评估可并行）
bash experiments/max_aux_points_ablation/train_and_eval.sh

# 强制重新生成数据
bash experiments/max_aux_points_ablation/generate_data.sh --force

# 强制重新训练和评估
bash experiments/max_aux_points_ablation/train_and_eval.sh --force
```

**优势：** 数据生成和训练评估可以同时运行，训练会自动等待数据就绪。

**推荐使用场景：**

| 场景 | 推荐脚本 | 原因 |
|------|---------|------|
| 从零开始运行全部实验 | `run_ablation.sh` | 一站式，自动协调所有阶段 |
| 数据已生成，只需训练评估 | `train_and_eval.sh` | 跳过数据生成，训练评估并行 |
| 分别控制数据生成和训练 | `generate_data.sh` + `train_and_eval.sh` | 灵活控制，可在不同终端运行 |
| 重新生成某个实验的数据 | `generate_data.sh --force` | 只重新生成数据 |
| 重新训练某个模型 | 删除 `.train_done` + `train_and_eval.sh` | 只重新训练 |

---

## 进度监控命令

### 查看整体状态

```bash
# 查看所有实验的完成标记
ls -lh experiments/max_aux_points_ablation/logs/*/.*_done

# 输出示例：
# .data_ready   - 数据生成完成
# .train_done   - 训练完成
# .eval_done    - 评估完成
```

### 数据生成进度

```bash
# 实时查看数据生成日志
tail -f experiments/max_aux_points_ablation/logs/sft35_maxaux2/data_generation.log

# 查看生成进度
grep -E "Generated|Progress|samples" experiments/max_aux_points_ablation/logs/sft35_maxaux2/data_generation.log | tail -20

# 查看已生成的数据文件
ls -lh experiments/max_aux_points_ablation/data/*/geometry_*.jsonl

# 检查数据生成进程
ps aux | grep "pipeline.py" | grep -v grep
```

### 训练进度

```bash
# 实时查看训练日志
tail -f experiments/max_aux_points_ablation/logs/sft35_maxaux2/training.log

# 查看训练进度（loss 和 step）
grep -E "loss|step" experiments/max_aux_points_ablation/logs/sft35_maxaux2/training.log | tail -20

# 查看 GPU 使用情况
nvidia-smi

# 检查训练进程
ps aux | grep "swift sft" | grep -v grep
```

### 评估进度

```bash
# 实时查看评估日志
tail -f experiments/max_aux_points_ablation/logs/sft35_maxaux2/evaluation.log

# 查看评估结果
grep -E "Solved|Score|problems" experiments/max_aux_points_ablation/logs/sft35_maxaux2/evaluation.log

# 检查评估进程
ps aux | grep "evaluation.py" | grep -v grep
```

### 系统资源监控

```bash
# 查看 CPU 使用情况
top -bn1 | grep "Cpu(s)"

# 查看内存使用
free -h

# 查看磁盘空间
df -h experiments/max_aux_points_ablation/

# 持续监控 GPU
watch -n 1 nvidia-smi

# 查看当前正在运行的所有实验相关进程
ps aux | grep -E "pipeline.py|swift sft|evaluation.py" | grep -v grep
```

### 查看评估结果汇总

```bash
# 查看所有实验的评估结果
for exp in sft35 sft36 sft37 sft38; do
    echo "=== $exp ==="
    grep -E "Solved|Score" experiments/max_aux_points_ablation/logs/${exp}_maxaux*/evaluation.log | tail -5
done
```

### 断点续跑机制

所有脚本都通过标记文件自动检测每个实验的完成状态，支持中断后继续运行：

| 标记文件 | 含义 |
|---------|------|
| `.data_ready` | 数据生成已完成（内容为数据集路径） |
| `.train_done` | 训练已完成 |
| `.eval_done` | 评估已完成 |

**中断恢复示例：**

1. **数据生成中断**
   ```bash
   # 场景：sft35 数据生成完成，sft36 数据生成中断
   # 重新运行脚本会自动跳过 sft35，从 sft36 继续
   bash experiments/max_aux_points_ablation/generate_data.sh
   ```

2. **训练中断**
   ```bash
   # 场景：sft35 训练完成，sft36 训练中断
   # 重新运行会跳过 sft35，从 sft36 训练开始
   bash experiments/max_aux_points_ablation/train_and_eval.sh
   ```

3. **评估中断**
   ```bash
   # 场景：sft35 全部完成，sft36 训练完成但评估中断
   # 重新运行会跳过 sft35，sft36 直接从评估开始
   bash experiments/max_aux_points_ablation/train_and_eval.sh
   ```

**优雅中断：**

所有脚本都支持 Ctrl+C 优雅退出：
- 会自动清理后台进程
- 已完成的阶段会保留标记文件
- 重新运行时自动从中断点继续

**手动重跑某个实验：**

```bash
# 删除该实验的标记文件
rm experiments/max_aux_points_ablation/logs/sft35_maxaux2/.train_done
rm experiments/max_aux_points_ablation/logs/sft35_maxaux2/.eval_done

# 重新运行
bash experiments/max_aux_points_ablation/train_and_eval.sh
```

## 代码修改

### `pipeline.py` 新增命令行参数

在 `src/newclid/generation_new/pipeline.py` 的 `main()` 中新增了 `--max_auxiliary_points` 命令行参数：

```python
parser.add_argument("--max_auxiliary_points", required=False, type=int, default=2,
                    help="Maximum number of auxiliary points to add per problem.")
```

**参数传递链路：**
```
pipeline.py CLI (--max_auxiliary_points)
  → ProblemPipeline.__init__(max_auxiliary_points=...)
    → generate() → task_generator() yield 包含 max_auxiliary_points
      → ProblemWorker.ray_process_single_problem(args)
        → ProblemSampler.generate(max_auxiliary_points=...)
          → ClauseDAG.add_auxiliary_points(max_points=...)
            → auxiliary/finder.py::add_potential_points(max_points=...)
```

该链路在本次修改前已完全打通（`ProblemPipeline` 构造器和内部调用已支持 `max_auxiliary_points`），仅缺少 CLI 入口，本次补充。

## 预期观察

- `max_auxiliary_points` 越大，生成的问题可能包含更多辅助点，问题复杂度更高
- 可能观察到的权衡：
  - 辅助点越多 → 训练数据中的构造更丰富 → 模型可能学到更强的辅助点预测能力
  - 辅助点过多 → 问题噪声增大 → 可能影响训练稳定性
- 评估指标：在 `dev_imo.txt` 和 `imo_95_reorder.txt` 上的求解正确率
