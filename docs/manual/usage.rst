Usage
=====

The basic functionality of the GeoSolver/AlphaGeometry is to write down a problem, which will be processed by one of the multiple solvers supported. The difference from using the GeoSolver only and AlphaGeometry is that AlphaGeometry is equipped with a language model that proposes new constructions if a problem gets stuck. Currently, that can be done in the GeoSolver only by human suggested constructions if the Human Agent solver is used.

Definitions and Predicate's Languages
-------------------------------------

The GeoSolver uses two languages. To state problems, one should use the terminology described in the definitions (defs.txt and new_defs.txt files). The solver will convert that, and reason, with its predicates. Predicates are not isolated anywhere in the codebase, but can be found being used in the rules' files (rules.txt, new_rules.txt, testing_minimal_rules.txt, etc.).

For detailed information on definitions, check .
.. Add a defs module and link here

For detailed information on predicates, check .
.. Add a predicates module and link here

Feeding a problem
-----------------

Problems must be written in a formal language, that can be processed by the solver. This involves translating the problems to the software's language, but not only. In order to write a problem, a numerical diagram representation for it must be built alongside, so constructions must be stated in an order that allows the drawing to be made. The process is similar to that of building a straightedge and compass construction of the problem statement, although more tools are available for the definition of the problem. This translation may involve changing the order of terms presented, or even reversing a construction altogether.

Still, some problems may not be written into the GeoSolver for being overdetermined, or may demand the offering of extra information to the solver, as extra points, with respect to its original statement. To evaluate if such modifications preserve the nature of the original problem is a matter of considering which facts are offered to the solver as hypothesis and exercising judgement. Sometimes there is no clear-cut way to decide if a problem was modified or simply translated into the GeoSolver.

Definitions
-----------

Problems are written using definitions, from the defs.txt or the new_defs.txt files. Each new point (or points) has to be defined by one or two definitions, two in the case of an intersection. Each definition is a term that expects a number of arguments, typically the point (or points) being defined plus a collection of other previously defined points. A definition will trigger tests to see if the arguments given are compatible, the addition of new predicates (facts) to the proof state, and a numerical construction to be added to the diagram. For details, check .
.. Create a separate module and link here

How is a Problem Built
----------------------

Deductive Agents
----------------
.. Also create a separate module

BFS Agent (Traditional Solver)
------------------------------

Deductive Agent (DD)
^^^^^^^^^^^^^^^^^^^^

Algebraic Reasoning (AR)
^^^^^^^^^^^^^^^^^^^^^^^^

Traceback
---------

Dependency Structure
^^^^^^^^^^^^^^^^^^^^

More info on :ref:`dependency-graph`.

Writing the Proof
-----------------