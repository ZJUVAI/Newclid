# Directory Structure & Environment

## Directory Structure

```
src/newclid/                     # 核心代码
├── DDAR/                        # C++ 符号推理引擎
├── agent/                       # 推理 agent (ddarn, lm)
├── generation/                  # 合成数据生成
├── proof_scout/                 # 知识发现 pipeline
│   ├── core/                    # 图结构 (ProofGraph, GraphPruner, FilterAndPruneEngine)
│   ├── extraction/              # 规则提取 (RuleExtractor, RuleConverter, RuleTester)
│   ├── ml/                      # ML pipeline (scout_pipeline, model_utils)
│   └── reduction/               # 规则规约 (GeneralityScorer, SubsumptionTester, RuleReducer)
├── api.py                       # GeometricSolverBuilder / GeometricSolver
├── proof.py                     # ProofState
└── match_theorems.py            # Python-side theorem matching

scripts/                         # 脚本
├── discovery_pipeline.py        # 知识发现 pipeline 入口
├── reduce_rules.py              # 规则规约入口
├── evaluation.py                # 基准测试
├── figures/                     # 可视化脚本
└── ...

outputs/
├── datasets/                    # 合成数据集
│   ├── synthetic_220k_aux/      # 最新 (1.2G)
│   ├── synthetic_10k_aux_only/  # 双组测试用 (39M)
│   └── archive/                 # 旧版本
├── experiments/                 # 实验结果 (每个子目录含 info.md)
└── archive/                     # 过时杂项

datasets/                        # 参考数据和辅助点
├── aux_points/                  # 辅助点 (benchmarks 用)
├── imo_ag_50/                   # IMO-AG-50 参考
├── mo_tg_225/                   # MO-TG-225 参考
└── tong_geometry_cases/         # tong 几何案例

benchmarks/                      # 测试基准
├── core/                        # 核心基准 (imo_ag_30, imo_ag_50)
├── extended/                    # 扩展基准
├── coords/                      # 带坐标版本
└── dev/                         # 开发测试
```

## Environment Configuration

**Git 远端**:
- origin → git@github.com:ZhengtongDu/Try-GeoDiscovery-Using-CC.git
- GenesisGeo → git@github.com:ZJUVAI/GenesisGeo.git

**Discovery 环境**:
- 环境路径: /C20545/home/duzhengtong/miniconda3/envs/Discovery
- Python: 3.10
- PyTorch: 2.5.1+cu121
- 所有 C++ 扩展已编译完成（matchinC, geometry, DDAR）
