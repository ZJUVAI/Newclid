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

Still, some problems may not be written into the GeoSolver for being overdetermined, or may demand the offering of extra information to the solver, such as extra points, with respect to its original statement. To evaluate if such modifications preserve the nature of the original problem is a matter of considering which facts/predicates are offered to the solver as hypothesis and exercising judgement. Sometimes there is no clear-cut way to decide if a problem was modified or simply translated into the GeoSolver.

When giving a problem to the solver, the problem, definitions to be used, and set of rules to be assumed in the derivation can be given in dedicated .txt files with the proper formatting, or as strings directly in the builder function. See .

.. Add a reference to the module that describes the builder.

Definitions
-----------

Problems are written using definitions, from the defs.txt or the new_defs.txt files. Each new point (or points) has to be defined by one or two definitions, two in the case of an intersection. Each definition is a term that expects a number of arguments, typically the point (or points) being defined plus a collection of other previously defined points. A definition will trigger tests to see if the arguments given are compatible, the addition of new predicates (facts) to the proof state, and a numerical construction to be added to the diagram. For details, check .

.. Create a separate module and link here

How is a Problem Built
----------------------

When a problem is given, with a chosen deductive agent (see below), and the program is initialized, the engine will read the files that contain the problem (in its entirety, even if there is more than one problem in the file), the definitions, and the rules to be used. Any formatting mistake anywhere is those files, even if at elements not relevant to the problem being checked, will raise processing errors.

Next, the builder will construct the problem itself. This means compiling the information of the problem in two directions: the numerical diagram and the symbolic statements (proof state, dependency graph, and symbols graph). Symbolically, the builder checks if the symbolic conditions for each definition is satisfied, and adds the predicates assigned to each point to the proof state.

The numerical diagram is built by calling the functions on the sketch.py module (see :ref:`Sketch`). The numerical diagram generated will be used in the construction of the pictures in the problem, but not only. It assigns coordinates to each point, according to the sketch functions. Such coordinates will be used during reasoning to check numerically for some predicates (non-collinearity, non-parallelism, non-perpendicularity, different points). Also, after finishing the constructions, the builder will numerically check if the goal is satisfied in the constructed diagram.

The numerical check of the goal exists for two reasons. First, it is a sanity check to the user, that tells if the problem is well-written or not. Second, the construction functions have intrinsic degrees of freedom, some of which may not be compatible with the problem (non-degeneracy conditions). If one of those is randomly hit by a construction, the goal will not be satisfied and the builder will start building again from scratch. This will be attempted a fixed number of times (max_attempts) before the program decides that the goal is not reacheable, on the assumption that the probability of a failure at random is low.

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

More info on :ref:`Dependencies`.

Writing the Proof
-----------------