#! /bin/bash
#
# Meant to be called in Travis-ci, not really for anything else.
for v in 34 35 36 37; do
    python=/opt/python/cp${v}-cp${v}m/bin/python
    $python -m pip install .
    $python setup.py build
    $python setup.py build_ext --inplace
    $python setup.py bdist_wheel
    $python -m pip install pytest
    $python -m pytest .
    rm pynng/*.so
done
$python setup.py sdist
# rename wheels so they'll be officially compatible
rename linux manylinux1 dist/*.whl
# artifacts diretory should have been mounted under /mnt/artifacts
mv dist /mnt/artifacts
