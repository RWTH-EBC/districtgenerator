# coding=utf-8
import setuptools

setuptools.setup(name='districtgenerator',
                 version='0.0.1',
                 description='Energy profile generation and '
                             'optimization of districts',
                 url='https://github.com/RWTH-EBC/districtgenerator',
                 author='Joel Schölzel',
                 author_email='joel.schoelzel@eonerc.rwth-aachen.de',
                 license='MIT License',
                 packages=setuptools.find_packages(),
                 install_requires=['numpy', 'pandas', 'matplotlib', 'scipy',
                                   'teaser', 'richardsonpy', 'pylightxl', 'gurobipy', 'seaborn', 'openpyxl'],
                 classifiers=("Programming Language :: Python :: 3", ),
                 )