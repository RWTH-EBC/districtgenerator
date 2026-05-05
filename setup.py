# coding=utf-8
import setuptools

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setuptools.setup(name='districtgenerator',
                 python_requires='~=3.12',
                 version='0.0.1',
                 description='Energy profile generation and '
                             'optimization of districts',
                 url='https://github.com/RWTH-EBC/districtgenerator',
                 author='Joel Schölzel',
                 author_email='joel.schoelzel@eonerc.rwth-aachen.de',
                 license='MIT License',
                 packages=setuptools.find_packages(),
                 include_package_data=True,
                 install_requires=requirements,
                 classifiers=("Programming Language :: Python :: 3", ),
                 )