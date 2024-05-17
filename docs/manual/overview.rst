Overview
========

How is a Problem Built
----------------------

When a problem is given and the program is initialized, 
the engine will read the files that contain the problem 
(in its entirety, even if there is more than one problem in the file), 
the definitions, and the rules to be used. 

Any formatting mistake anywhere is those files, 
even if at elements not relevant to the problem being checked, will raise processing errors.

Next, the builder will construct the problem itself. 
This means compiling the information of the problem in two directions: the numerical diagram and the symbolic statements 
(proof state, dependency graph, and symbols graph). 
Symbolically, the builder checks if the symbolic conditions for each definition is satisfied, 
and adds the predicates assigned to each point to the proof state (cached and ).

The numerical diagram is built by calling the functions on the sketch.py module (see :ref:`Sketch`).
The numerical diagram generated will be used in the construction of the pictures in the problem, but not only.
It assigns coordinates to each point, according to the sketch functions.

Such coordinates will be used during reasoning to check numerically for some predicates (non-collinearity, non-parallelism, non-perpendicularity, different points).
Also, after finishing the constructions, the builder will numerically check if the goal is satisfied in the constructed diagram.

The numerical check of the goal exists for two reasons.
First, it is a sanity check to the user, that tells if the problem is well-written or not.
Second, the construction functions have intrinsic degrees of freedom, some of which may not be compatible with the problem (non-degeneracy conditions).
If one of those is randomly hit by a construction, the goal will not be satisfied and the builder will start building again from scratch.
This will be attempted a fixed number of times (max_attempts) before the program decides that the goal is not reacheable, 
on the assumption that the probability of a failure at random is low.


Deducting Agents
----------------

As of now, one can choose to run the problems either using an automatic agent
(the BFSDDAR engine, as in the original AlphaGeometry work, 
and a BFSDD engine that does not include algebraic manipulations),
or a manually guided helper (the Human Agent deductive agent).

More detailed information on the deductive agents is available at :ref:`Agent`.


BFSDDAR Agent (Traditional and default Solver)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The traditional engine of the GeoSolver is AlphaGeometry's DDAR.
BFS stands for Breadth-First Search, as in this method all rules are applied in that manner, 
from beginning to end, without considering the possibility of going deeper into a result.

DDAR is composed of two phases: 
   1. A symbolic reasoner (deductive derivation - DD) exhaustively runs all rules until no new statements are found.
   2. Once DD's fixpoint is reached, some equations will have been collected throughout the theorem matching into the algebraic reasoning (AR) module, 
      which will solve a linear system of equations and possibly translate the results it gets as new predicates, to restart the DD loop.

This process repeats until a fixpoint is reached both by DD and AR, or until the goal result is found as a fact.


Writing the Proof
------------------

Once the goal statement is found by the solver, 
in general it will have covered a wide graph of statements that do not necessarily contribute to the proof.
To have a clean and coherently written proof, the geosolver uses a traceback, 
that tries to find the shortest straight path from the premises to the goal through the proof graph (for more details see :ref:`Trace back`).

To be able to keep track of the connection between the steps taken on the graph, 
an important part of the proof construction is the dependency structure, 
that assigns to each statement a list of reasons for why that statement was added to the graph.

Dependency Structure
^^^^^^^^^^^^^^^^^^^^

More info on :ref:`Dependencies graph`.

Translating to natural language
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After the traceback structures the proof, 
the predicates are translated into (pseudo) natural language (by a script, see :ref:`Proof writing` and :ref:`Pretty`). 

The written proof constains the hypothesis ("From theorem premises"), 
which are the points effectively present in the goal, 
intermediary points ("Auxiliary Constructions") used in the proof, 
and the proof steps.

Constructions given in the statement of the problem but that do not show up in the proof will not be present.

Each proof step lists the premises used for the step, the consequence, and the reason (dependency) that makes it true.
As of now, we still have steps being written with empty reason, due to untracked dependencies.
All steps are numerated to help follow the proof.
