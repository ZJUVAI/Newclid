
# Symbolic solver for Geometric problems

A standalone package of the geometric solver used for 
introduced in the [Nature 2024](https://www.nature.com/articles/s41586-023-06747-5) paper:.

*<center>"Solving Olympiad Geometry without Human Demonstrations".</center>*


</br>

<center>
<img alt="fig1" width="800px" src="AlphaGeometryMainPicture.svg">
</center>


## Installation

Using pip

```
pip install git+https://rnd-gitlab-eu.huawei.com/Noahs-Ark/libraries/ddar
```

## Contributing

1. Clone the repository

```
git clone git+https://rnd-gitlab-eu.huawei.com/Noahs-Ark/libraries/ddar
cd path/to/repo
```

2. (Optional) Create a virtual environment, for example with venv:

```
python -m venv venv

# On UNIX
source ./bin/activate

# On Windows
.\venv\Scripts\activate
```

3. Install as an editable package with dev requirements

```
pip install -e .[dev]
```

4. Install pre-commit and pre-push checks

```
pre-commit install -t pre-commit -t pre-push
```

5. Run tests

```
pytest tests
```


## Source code description

Modules of the geosolver package implements everything needed to run the solvers and
resource files necessary for the script to execute. We listed below
each of them and their description.

| Module name            | Description                                                                        |
|------------------------|------------------------------------------------------------------------------------|
| `geometry.py`          | Implements nodes (Point, Line, Circle, etc) in the proof state graph.              |
| `numericals.py`        | Implements the numerical engine in the dynamic geometry environment.               |
| `graph_utils.py`       | Implements utilities for the proof state graph.                                    |
| `graph.py`             | Implements the proof state graph.                                                  |
| `problem.py`           | Implements the classes that represent the problem premises, conclusion, DAG nodes. |
| `dd.py`                | Implements DD and its traceback.                                                   |
| `ar.py`                | Implements AR and its traceback.                                                   |
| `trace_back.py`        | Implements the recursive traceback and dependency difference algorithm.            |
| `ddar.py`              | Implements the combination DD+AR.                                                  |
| `beam_search.py`       | Implements beam decoding of a language model in JAX.                               |
| `models.py`            | Implements the transformer model.                                                  |
| `transformer_layer.py` | Implements the transformer layer.                                                  |
| `pretty.py`            | Pretty formating the solutions output by solvers.                                  |


Resource files:

| Resource file name     | Description                                                                        |
|------------------------|------------------------------------------------------------------------------------|
| `defs.txt`             | Definitions of different geometric construction actions.                           |
| `rules.txt`            | Deduction rules for DD.                                                            |
| `imo_ag_30.txt`        | Problems in IMO-AG-30.                                                             |
| `jgex_ag_231.txt`      | Problems in JGEX-AG-231.                                                           |
| `examples.txt`         | Example geometric problems.                                                        |


## About AlphaGeometry

See [original repository](https://github.com/google-deepmind/alphageometry).

```bibtex
@Article{AlphaGeometryTrinh2024,
  author  = {Trinh, Trieu and Wu, Yuhuai and Le, Quoc and He, He and Luong, Thang},
  journal = {Nature},
  title   = {Solving Olympiad Geometry without Human Demonstrations},
  year    = {2024},
  doi     = {10.1038/s41586-023-06747-5}
}
```

## Code License

Copyright 2023 DeepMind Technologies Limited

All software is licensed under the Apache License, Version 2.0 (Apache 2.0);
you may not use this file except in compliance with the Apache 2.0 license.
You may obtain a copy of the Apache 2.0 license at:
https://www.apache.org/licenses/LICENSE-2.0

All other materials are licensed under the Creative Commons Attribution 4.0
International License (CC-BY). You may obtain a copy of the CC-BY license at:
https://creativecommons.org/licenses/by/4.0/legalcode

Unless required by applicable law or agreed to in writing, all software and
materials distributed here under the Apache 2.0 or CC-BY licenses are
distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the licenses for the specific language governing
permissions and limitations under those licenses.

## Model Parameters License

The AlphaGeometry checkpoints and vocabulary are made available
under the terms of the Creative Commons Attribution 4.0
International (CC BY 4.0) license.
You can find details at:
https://creativecommons.org/licenses/by/4.0/legalcode

