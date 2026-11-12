# coding=utf-8
import setuptools

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setuptools.setup(name='districtgenerator',
                 python_requires='~=3.12',
                 version='1.0.1',
                 description='Energy profile generation and '
                             'optimization of districts',
                 long_description=long_description,
                 long_description_content_type='text/markdown',
                 url='https://github.com/RWTH-EBC/districtgenerator',
                 project_urls={
                     'Documentation': 'https://rwth-ebc.github.io/districtgenerator/master/docs/README.html',
                     'Source': 'https://github.com/RWTH-EBC/districtgenerator',
                     'Changelog': 'https://github.com/RWTH-EBC/districtgenerator/blob/master/docs/about/CHANGELOG.md',
                 },
                 author='Joel Schölzel',
                 author_email='joel.schoelzel@eonerc.rwth-aachen.de',
                 license='MIT License',
                 packages=setuptools.find_packages(),
                 include_package_data=True,
                 install_requires=requirements,
                 classifiers=[
                     "Programming Language :: Python :: 3",
                     "Programming Language :: Python :: 3.12",
                     "License :: OSI Approved :: MIT License",
                     "Operating System :: OS Independent",
                     "Topic :: Scientific/Engineering",
                 ],
                 )
