#! /bin/bash
#
# Meant to be called in Travis-ci, not really for anything else.
#
# example usage:
# docker run --rm -i -t codypiersall/manylinux1-pynng
python=/opt/python/cp35-35m/bin/python
$python -m pip install .
$python -m setup.py build
$python -m setup.py build_ext --inplace
$python -m pip install pytest
$python -m pytest .

