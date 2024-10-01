# coding=utf-8
import setuptools
import sys

# read the contents of your README file
from pathlib import Path
readme_path = Path(__file__).parent.joinpath("README.md")
long_description = readme_path.read_text()

if sys.version_info.minor >= 9 and sys.version_info.major == 3:
    EXTRAS_REQUIRE['full'].append('fastparquet>=2023.1.0')

with open(Path(__file__).parent.joinpath("ebcpy", "__init__.py"), "r") as file:
    for line in file.readlines():
        if line.startswith("__version__"):
            VERSION = line.replace("__version__", "").split("=")[1].strip().replace("'", "").replace('"', '')
            
setuptools.setup(name='districtgenerator',
                 version=VERSION,
                 long_description=long_description,
                     long_description_content_type='text/markdown',
                 description='Energy profile generation and '
                             'optimization of districts',
                 url='https://github.com/RWTH-EBC/districtgenerator',
                 author='Sarah Henn',
                 author_email='shenn@eonerc.rwth-aachen.de',
                 license='MIT License',
                 packages=setuptools.find_packages(),
                 install_requires=['numpy', 'pandas', 'matplotlib', 'scipy',
                                   'teaser', 'richardsonpy', 'pylightxl', 'gurobipy', 'seaborn', 'openpyxl'],
                 classifiers=("Programming Language :: Python :: 3", ),
                 )