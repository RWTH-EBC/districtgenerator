# coding=utf-8
import setuptools


def parse_requirements(filename):
    with open(filename, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


setuptools.setup(name='districtgenerator',
                 version='0.0.1',
                 description='Energy profile generation and '
                             'optimization of districts',
                 url='https://github.com/RWTH-EBC/districtgenerator',
                 author='Joel Schölzel',
                 author_email='joel.schoelzel@eonerc.rwth-aachen.de',
                 license='MIT License',
                 packages=setuptools.find_packages(),
                 install_requires=parse_requirements('requirements.txt'),
                 classifiers=("Programming Language :: Python :: 3",),
                 )