GeoSolver: Symbolic solver for Geometric problems
=================================================

An extension of the geometric solver introduced in the Nature 2024 paper:
`Solving Olympiad Geometry without Human Demonstrations
<https://www.nature.com/articles/s41586-023-06747-5>`_.


.. image:: docs/_static/images/overview.drawio.svg
  :alt: overview diagram


AlphaGeometry can be seen as an extension of GeoSolver equipped with a language model
that proposes new auxiliary constructions if a problem gets stuck.

Currently new auxiliary constructions can only be added in Geosolver as human suggested
constructions if the HumanAgent is used instead of BFSDDAR (default).

.. include:: docs/introduction.rst