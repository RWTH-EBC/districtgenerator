# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys
sys.path.insert(0, os.path.abspath('../'))

from districtgenerator import __version__  # noqa: E402

project = 'DistrictGenerator'
copyright = ('2024-2026, RWTH Aachen University, E.ON Energy Research Center, '
             'Institute for Energy Efficient Buildings and Indoor Climate')
author = 'Joel Schölzel, Carla Wüller, Rawad Hamze, Hannah Görigk'
release = __version__
version = __version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.todo',
    'sphinx.ext.viewcode',
    'myst_parser',
    'sphinxcontrib.mermaid',
    'sphinxcontrib.autodoc_pydantic',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Napoleon: render 'Attributes' sections as fields, so they do not duplicate the attributes documented by autodoc
napoleon_use_ivar = True

# Markdown: render ```mermaid code blocks as diagrams (as on GitHub) and create anchors for headings
myst_fence_as_directive = ['mermaid']
myst_heading_anchors = 3

# Configuration classes (pydantic): list the fields with their defaults, without JSON schema and validators
autodoc_pydantic_model_show_json = False
autodoc_pydantic_settings_show_json = False
autodoc_pydantic_model_show_config_summary = False
autodoc_pydantic_settings_show_config_summary = False
autodoc_pydantic_model_show_validator_summary = False
autodoc_pydantic_settings_show_validator_summary = False
autodoc_pydantic_field_list_validators = False

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = []
