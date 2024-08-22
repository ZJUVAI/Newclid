python ./docs/reformat.py
sphinx-build -b html ./docs ./docs/_build
sphinx-autobuild docs docs/_build/html
