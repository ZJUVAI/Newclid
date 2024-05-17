
GeoSolver: Symbolic solver for Geometric problems
=================================================

A standalone package of the geometric solver introduced 
in the Nature 2024 paper:
`Solving Olympiad Geometry without Human Demonstrations
<https://www.nature.com/articles/s41586-023-06747-5>`_.


.. image:: ../docs/_static/AlphaGeometryMainPicture.svg
  :alt: Where a geometric problem is fed to a solver (DDAR)
        and helped by an LLM to build auxiliary constructions.


AlphaGeometry can be seen as an extension of GeoSolver equipped with a language model 
that proposes new auxiliary constructions if a problem gets stuck. 

Currently new auxiliary constructions can only be added in Geosolver as human suggested 
constructions if the HumanAgent is used instead of BFSDDAR (default).


Installation
------------

Using pip
^^^^^^^^^

.. code:: bash

  pip install git+https://rnd-gitlab-eu.huawei.com/Noahs-Ark/libraries/geosolver


From source
^^^^^^^^^^^

.. code:: bash

  git clone git+https://rnd-gitlab-eu.huawei.com/Noahs-Ark/libraries/geosolver
  pip install -e . 


Quickstart
----------

To simply solve a problem using geosolver, use the command line:

.. code:: bash

  geosolver --problem path/to/problem:problem_name


For example:

.. code:: bash

  geosolver --problem problems_datasets/examples.txt:orthocenter_consequence_aux


See other command line interface options with:

.. code:: bash

  geosolver --help 

For more complex applications, use the `python interface 
<https://ddar-noahs-ark-libraries-d1a330533fb77a761c85bd7785b7974dd32b06.rnd-gitlab-eu.huawei.com/manual/python_interface.html#/>`_
, some examples of script using it are displayed in the folder `examples`.


Documentation
-------------

See `the online documentation 
<https://ddar-noahs-ark-libraries-d1a330533fb77a761c85bd7785b7974dd32b06.rnd-gitlab-eu.huawei.com/>`_
for more detailed informations about geosolver.


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

See `original repository <https://github.com/google-deepmind/alphageometry>`_.

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

