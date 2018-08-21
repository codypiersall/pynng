import setuptools

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

setuptools.setup(
    name='pynng',
    version='0.1.0-pre',
    author='Cody Piersall',
    author_email='cody.piersall@gmail.com',
    description='Networking made simply using nng',
    long_description=long_description,
    license='MIT',
    keywords='networking nng nanomsg zmq messaging message',
    long_description_content_type='text/markdown',
    url='https://github.com/codypiersall/pynng',
    packages=setuptools.find_packages(),
    classifiers=(
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Development Status :: 3 - Alpha',
        'Topic :: Software Development :: Libraries',
        'Topic :: System :: Networking',
    ),
    setup_requires=['cffi'],
    cffi_modules=['build.py:ffibuilder'],
    install_requires=['cffi'],
)

