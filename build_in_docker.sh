#! /bin/bash
#
# Meant to be called in Travis-ci, not really for anything else.
for v in 35 36 37; do
    python=/opt/python/cp${v}-cp${v}m/bin/python
    $python setup.py build_ext --inplace
    $python setup.py bdist_wheel
    # if pytest fails we've got a problem.  This will allow us to check in
    # Docker that everything is okay.
    $python setup.py pytest --addopts -s -v && touch /mnt/artifacts/v${v}_success
    rm pynng/*.so
done
$python setup.py sdist
# rename wheels so they'll be officially compatible
rename linux manylinux1 dist/*.whl
# artifacts diretory should have been mounted under /mnt/artifacts
mv dist /mnt/artifacts
