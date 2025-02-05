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
                 install_requires=[
                     'numpy>=1.20.1',
                     'pandas>=1.2.3',
                     'matplotlib>=3.3.4',
                     'scipy>=1.6.1',
                     'teaser==0.7.7',
                     'richardsonpy',
                     'pylightxl',
                     'gurobipy>=9.5.1',
                     'xlsxwriter~=3.2.0',
                     'geopy~=2.4.1',
                     'pyproj~=3.7.0',
                     'openpyxl==3.1.5',
                     'seaborn==0.13.2'
                 ],
                 classifiers=("Programming Language :: Python :: 3", ),
                 )