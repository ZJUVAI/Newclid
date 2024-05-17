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

Next, the builder will construct the problem itself. This means compiling the information of the problem in two directions: the numerical diagram and the symbolic statements (proof state, dependency graph, and symbols graph). Symbolically, the builder checks if the symbolic conditions for each definition is satisfied, and adds the predicates assigned to each point to the proof state (cached and ).

The numerical diagram is built by calling the functions on the sketch.py module (see :ref:`Sketch`). The numerical diagram generated will be used in the construction of the pictures in the problem, but not only. It assigns coordinates to each point, according to the sketch functions. Such coordinates will be used during reasoning to check numerically for some predicates (non-collinearity, non-parallelism, non-perpendicularity, different points). Also, after finishing the constructions, the builder will numerically check if the goal is satisfied in the constructed diagram.

The numerical check of the goal exists for two reasons. First, it is a sanity check to the user, that tells if the problem is well-written or not. Second, the construction functions have intrinsic degrees of freedom, some of which may not be compatible with the problem (non-degeneracy conditions). If one of those is randomly hit by a construction, the goal will not be satisfied and the builder will start building again from scratch. This will be attempted a fixed number of times (max_attempts) before the program decides that the goal is not reacheable, on the assumption that the probability of a failure at random is low.

Deductive Agents
----------------

The GeoSolver can use different reasoning agents to try to solve the problem given. They can be chosen when running the problem by specifying the deductive agent in the GeometricSolverBuilder class used to run the problem (see details in ).

.. Add reference to whatever describes the building of the problem, then recover skipped line.

As of now, one can choose to run the problems either using an automatic agent (the BFS-DDAR engine, as in the original AlphaGeometry work, and a BFS-DD engine that does not include algebraic manipulations), or a manually guided helper (the Human Agent deductive agent).

More detailed information on the deductive agents is available at .

.. Also create a separate module

BFS Agent (Traditional Solver)
------------------------------

The traditional engine of the GeoSolver is AlphaGeometry's DDAR. It corresponds to the BFSDDAR agent. It is composed of two phases: a symbolic reasoner (deductive derivation - DD) that exhaustively runs a list of rules on the facts/predicates known at each time. BFS stands for Breadth-First Search, as in this method the whole list is run, from beginning to end, without considering the possibility of going deep into a result. Such list will run multiple times, until it either solves the problem or ceases to find new statements (fixpoint).

Once the fixpoint is reached, some equations will have been collected throughout the theorem matching into the algebraic reasoning (AR) module, which will solve a linear system of equations and possibly translate the results it gets as new predicates, to restart the DD loop.

This process repeats until a fixpoint is reached both by DD and AR, or until the goal result is found as a fact.

Traceback
---------

Once the goal statement is found by the solver, in general it will have covered a wide graph of statements that do not necessarily contribute to the proof. To have a clean and coherently written proof, the geosolver uses a traceback, that tries to find the shortest straight path from the premises to the goal through the proof graph (for more details see :ref:`Trace back`).

To be able to keep track of the connection between the steps taken on the graph, an important part of the proof construction is the dependency structure, that assigns to each statement a list of reasons for why that statement was added to the graph.

Dependency Structure
^^^^^^^^^^^^^^^^^^^^

More info on :ref:`Dependencies`.

Writing the Proof
-----------------

After the traceback structures the proof, the predicates are translated into (pseudo) natural language (by a script, see :ref:`Proof writing` and :ref:`Pretty`). The written proof constains the hypothesis ("From theorem premises"), which are the points effectively present in the goal, intermediary points ("Auxiliary Constructions") used in the proof, and the proof steps. Constructions given in the statement of the problem but that do not show up in the proof will not be present.

Each proof step lists the premises used for the step, the consequence, and the reason (dependency) that makes it true. As of now, we still have steps being written with empty reason, due to untracked dependencies. All steps are numerated to help follow the proof.