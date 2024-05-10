
GeoSolver: Symbolic solver for Geometric problems
=================================================

A standalone package of the geometric solver introduced 
in the Nature 2024 paper:
`Solving Olympiad Geometry without Human Demonstrations
<https://www.nature.com/articles/s41586-023-06747-5>`_.


.. image:: _static/AlphaGeometryMainPicture.svg



Installation
------------

Using pip

.. code:: bash

  pip install git+https://rnd-gitlab-eu.huawei.com/Noahs-Ark/libraries/ddar


Contributing
------------

1. Clone the repository

.. code:: bash

  git clone git+https://rnd-gitlab-eu.huawei.com/Noahs-Ark/libraries/ddar
  cd path/to/repo

2. (Optional) Create a virtual environment, for example with venv:

.. code:: bash

  python -m venv venv

  # On UNIX
  source ./bin/activate

  # On Windows
  .\venv\Scripts\activate


3. Install as an editable package with dev requirements

.. code:: bash

  pip install -e .[dev]


4. Install pre-commit and pre-push checks

.. code:: bash

  pre-commit install -t pre-commit -t pre-push


5. Run tests

.. code:: bash

  pytest tests


About AlphaGeometry
-------------------

See [original repository](https://github.com/google-deepmind/alphageometry).

.. code:: bibtex

  @Article{AlphaGeometryTrinh2024,
    author  = {Trinh, Trieu and Wu, Yuhuai and Le, Quoc and He, He and Luong, Thang},
    journal = {Nature},
    title   = {Solving Olympiad Geometry without Human Demonstrations},
    year    = {2024},
    doi     = {10.1038/s41586-023-06747-5}
  }


The AlphaGeometry checkpoints and vocabulary are made available
under the terms of the Creative Commons Attribution 4.0
International (CC BY 4.0) license.
You can find details at:
https://creativecommons.org/licenses/by/4.0/legalcode

