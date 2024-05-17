Definitions
===========

The language used to state problems is that of the definitions in the defs.txt/new_defs.txt files. Each definition is composed of a block of 5 lines divided in the following way:

* 1st line: Contains the syntax to be used when using the definition (term followed by expected arguments).
* 2nd line: Describes the dependency between elements being created and the other arguments, separated by a ":". If it is to be used for intersecting, the point created should be present on both sides of the colon.
* 3rd line: Lists the arguments that should be existing points in the definition, on the left-hand side, and symbolic conditions they must satisfy for validity, on the right-hand side, separated by a "=". If the line is simply " = ", no previous points are needed for the definition.
* 4th line: Lists the points created and the symbolic predicates to be assigned to each. Those predicates will be the information effectively fed to the solver.
* 5th line: Gives the function to be called in the sketch module to add the created points to the numerical representation of the problem, with the proper arguments.

Some definitions can be used in combination with others (stated in the definition of a point with a separation by ","), as intersections of geometric elements.

The current definitions are the following: