Newclid: A User-Friendly Replacement for AlphaGeometry with Agentic Support
=================================================


Installation
------------

Using pip
^^^^^^^^^

.. code:: bash

  pip install git+https://github.com/LMCRC/Newclid.git


From source
^^^^^^^^^^^

.. code:: bash

  git clone https://github.com/LMCRC/Newclid.git
  cd Newclid
  pip install -e .


Quickstart
----------

To simply solve a problem using Newclid, use the command line:

.. code:: bash

  newclid --problem-name problem_name --problems-file path/to/problem


For example:

.. code:: bash

  newclid --problem-name orthocenter_consequence_aux --problems-file ./problems_datasets/examples.txt


See other command line interface options with:

.. code:: bash

  newclid --help

For more complex applications, use the Python interface.
Below is a minimal example to load a specific problem,
then uses the built solver to solve it:

.. code:: python

    from newclid import GeometricSolverBuilder, GeometricSolver

    solver_builder = GeometricSolverBuilder()
    solver_builder.load_problem_from_txt(
        "a b c = triangle a b c; "
        "d = on_tline d b a c, on_tline d c a b "
        "? perp a d b c"
    )

    # We now obtain the GeometricSolver with the build method
    solver: GeometricSolver = solver_builder.build()

    # And run the GeometricSolver
    success = solver.run()

    if success:
        print("Successfuly solved the problem!")
    else:
        print("Failed to solve the problem...")

    print(f"Run infos {solver.run_infos}")


Some more advanced examples of script using the Python interface
are displayed in the folder ``examples`` or used in ``tests``.


Documentation
-------------

See `the online documentation <https://lmcrc.github.io/Newclid/>`_
for more detailed informations about Newclid.


Contributing
------------

1. Clone the repository

.. code:: bash

  git clone https://github.com/LMCRC/Newclid.git
  cd Newclid

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


About Newclid
-------------------

Newclid is a successor to AlphaGeometry, introduced in this early 2024 Nature paper:
`Solving Olympiad Geometry without Human Demonstrations
<https://www.nature.com/articles/s41586-023-06747-5>`_. whose original codebase can be found `here <https://github.com/google-deepmind/alphageometry>`_.

If you found Newclid useful, please cite us as:

.. code:: bibtex

  @article{newclid2024sicca,
    author  = {Sicca, Vladmir and Xia, Tianxiang and F\'ed\'erico, Math\"is and Gorinski, Philip John and Frieder, Simon and Jui, Shangling},
    journal = {arXiv preprint},
    title   = {Newclid: A User-Friendly Replacement for AlphaGeometry with Agentic Support},
    year    = {2024}
  }


The AlphaGeometry checkpoints and vocabulary are made available
under the terms of the Creative Commons Attribution 4.0
International (CC BY 4.0) license.
You can find details at:
https://creativecommons.org/licenses/by/4.0/legalcode
