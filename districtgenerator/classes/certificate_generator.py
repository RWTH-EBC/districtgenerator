# -*- coding: utf-8 -*-

"""
This module contains the classes that are used to generate the certificate layout. 

Basic Structure:
- The ThemeManager class defines the design parameters and styles for the certificate, such as colors, fonts, spacing, etc.
- The ReportComponent and BaseReportFlowable bundle important functionalities for generated Classes. The ReportComponent includes the shared theme state, while the BaseReportFlowable includes a debugging functionality for Flowables.
- FrameBox is a basic layout element that creates a framed box with a title and content.
- CertificateBuilder
- DataExtractor
- CertificateTemplate
- CertificateLayout

Individual flowables:
- Header
- Energiekennwerte
- EnergyPieChart
- MaxLoadsBarChart
- Title
- Quartiersstruktur
- Footer
- EnergyHub
- DecentralSystems
- YearlyStackedBarCharts
- InputDataTable

Version Date: 05.06.2026
"""

import json
import math
from districtgenerator.classes import *
from districtgenerator.functions import opti_central
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, PageTemplate, Frame
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, StyleSheet1, ParagraphStyle
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, Spacer
from reportlab.platypus import NextPageTemplate, PageBreak, FrameBreak
from datetime import datetime, timedelta
import os
from collections import OrderedDict
import pandas as pd
import math

from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle, Polygon, Group
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from reportlab.platypus import Flowable
from reportlab.lib import colors
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot

DEBUG = False  # If set to true boxes are drawn around the different components to visualize the layout and available space
debug_line_width = 0.1  # Line width for the debug boxes


################################################################################
# Certificate Style Configuration Class
################################################################################

class ThemeManager:
    """
    This class is responsible for managing the different styles and enforcing a consistent design throughout the certificate.
    """

    FILE_LAYOUT = {
        'A4': {
            'page_margin_x': 72,
            'page_margin_small_x': 36,
            'page_margin_y': 72,
            'page_margin_small_y': 36,
            'section_padding': 10,
            'line_width': {
                'thick': 4,
                'medium': 2,
                'thin': 1
            },
            'spacing': {
                'large': 10,
                'medium': 10,
                'small': 6
            },
            'padding': 10
        },
        'A3': {  # Overwrites for A3. If a parameter is not specified here, the A4 value is used.
            'section_padding': 15,
            'spacing': {
                'large': 30,
                'medium': 20,
                'small': 8
            },
            'padding': 15
        }
    }

    def __init__(self, report_config):
        self.report_config = report_config  # Contains info about sizing, fonts and colors
        self.pagesize = self.report_config["pagesize"]
        self.colors = self.report_config["colors"]
        self.fonts = self.report_config["fonts"]

        available_pagesizes = {"A3", "A4"}
        if self.pagesize not in available_pagesizes:
            print(
                f"Warning: Pagesize '{self.pagesize}' not recognized. Available options are: {available_pagesizes}. Defaulting to 'A4'.")
            self.pagesize = "A4"

        self.layout = self.FILE_LAYOUT["A4"].copy()

        # overwrite the A4 baseline with pagesize specific values
        if self.pagesize != 'A4':
            self.layout.update(self.FILE_LAYOUT[self.pagesize])

    # --- Getters for Styles ---
    def get_color(self, color_type: str):
        """Returns the colors defined in the report configuration."""
        try:
            return self.colors[color_type]
        except KeyError:
            raise KeyError(f"Color type '{color_type}' not found. Available options: {list(self.colors.keys())}")

    def get_energy_color(self, energy_type: str):
        """Returns the color for the specified energy type."""
        try:
            return self.colors["energy"][energy_type]
        except KeyError:
            raise KeyError(
                f"Energy type '{energy_type}' not found. Available options: {list(self.colors['energy'].keys())}")

    def get_source_color(self, source_type: str):
        """Returns the color for the specified energy source type."""
        try:
            return self.colors["source"][source_type]
        except KeyError:
            raise KeyError(
                f"Source type '{source_type}' not found. Available options: {list(self.colors['source'].keys())}")

    def get_layout_color(self, layout_type: str):
        """Returns the color for district layout elements (connected, eh, etc.)."""
        try:
            return self.colors["layout"][layout_type]
        except KeyError:
            raise KeyError(
                f"Layout type '{layout_type}' not found. Available options: {list(self.colors['layout'].keys())}")

    def get_layout_size(self, size_type: str):
        """Returns the size for layout elements."""
        try:
            return self.report_config["sizes"][size_type]
        except KeyError:
            raise KeyError(
                f"Size type '{size_type}' not found. Available options: {list(self.report_config['sizes'].keys())}")

    def get_layout_options(self, option_type: str):
        """Returns the boolean value for the specified layout option."""
        try:
            return self.report_config["layout_options"][option_type]
        except KeyError:
            raise KeyError(
                f"Layout option type '{option_type}' not found. Available options: {list(self.report_config['layout_options'].keys())}")

    def get_font_size(self, font_type: str):
        """Returns the font size for the specified font type."""
        try:
            return self.fonts["sizes"][font_type]
        except KeyError:
            raise KeyError(f"Font type '{font_type}' not found. Available options: {list(self.fonts['sizes'].keys())}")

    def get_font(self, bold: bool = False):
        """Returns the font name based on whether bold is True or False."""
        return self.fonts["bold"] if bold else self.fonts["regular"]

    def get_line_width(self, line_type: str):
        """Returns the line width for the specified line type."""
        try:
            return self.layout['line_width'][line_type]
        except KeyError:
            raise KeyError(
                f"Line type '{line_type}' not found. Available options: {list(self.layout['line_width'].keys())}")

    def get_spacing(self, spacing_type: str):
        """Returns the spacing for the specified spacing type."""
        try:
            return self.layout['spacing'][spacing_type]
        except KeyError:
            raise KeyError(
                f"Spacing type '{spacing_type}' not found. Available options: {list(self.layout['spacing'].keys())}")

    def get_padding(self):
        """Returns the padding for the current pagesize."""
        return self.layout['padding']

    def get_page_margins(self):
        """Returns the page margins for the current pagesize."""
        return {
            'x': self.layout['page_margin_x'],
            'small_x': self.layout['page_margin_small_x'],
            'y': self.layout['page_margin_y'],
            'small_y': self.layout['page_margin_small_y']
        }

    def get_pagesize(self):
        """Returns the pagesize as a tuple (width, height) for the current pagesize."""
        PAGESIZE_MAP = {
            "A4": A4,
            "A3": A3
            # ... add more page sizes if needed (If varying from A4 Layout the ThemeManager needs to be adapted to include the new page size as well)
        }
        try:
            return PAGESIZE_MAP[self.pagesize]
        except KeyError:
            raise ValueError(
                f"Pagesize '{self.pagesize}' not recognized. Available options are: {list(PAGESIZE_MAP.keys())}.")

    # --- Defined Styles for the Certificate ---
    def get_paragraph_styles(self) -> StyleSheet1:
        """Returns an object with the defined paragraph styles for the certificate."""

        styles = StyleSheet1()
        styles.add(ParagraphStyle(
            name='Normal',
            fontName=self.fonts["regular"],
            fontSize=self.fonts["sizes"]["body"],
            textColor=self.colors["text"],
        ))

        styles.add(ParagraphStyle(
            name='SectionTitle',
            fontName=self.fonts["bold"],
            fontSize=self.fonts["sizes"]["section_title"],
            textColor=self.colors["text"],
        ))

        styles.add(ParagraphStyle(
            name='Small',
            fontName=self.fonts["regular"],
            fontSize=self.fonts["sizes"]["small"],
            textColor=self.colors["text_light"]
        ))

        return styles

    def get_table_styles(self) -> dict:
        """Returns a dictionary of table styles that can be used for different types of tables in the certificate."""
        styles = {}

        styles['standard'] = TableStyle([
            # Overall table style
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, self.colors["text"]),
            ('BOX', (0, 0), (-1, -1), 1, self.colors["text"]),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.colors["text"]),
            ('FONTSIZE', (0, 0), (-1, -1), self.fonts["sizes"]["table"]),
            ('BACKGROUND', (0, 0), (-1, -1), self.colors["background"]),

            # Data rows style
            ('FONTNAME', (1, 1), (-1, -1), self.fonts["regular"]),
            # header row bold
            ('FONTNAME', (0, 0), (-1, 0), self.fonts["bold"]),
            # first column bold
            ('FONTNAME', (0, 1), (0, -1), self.fonts["bold"]),
        ])

        styles['input_data'] = TableStyle([
            # General table style
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, self.colors["text"]),

            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), self.colors["background"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors["text"]),
            ('FONTNAME', (0, 0), (-1, 0), self.fonts["bold"]),
            ('FONTSIZE', (0, 0), (-1, 0), self.fonts["sizes"]["dense"]),

            # Body style
            ('TEXTCOLOR', (0, 1), (-1, -1), self.colors["text"]),
            ('FONTNAME', (0, 1), (-1, -1), self.fonts["regular"]),
            ('FONTSIZE', (0, 1), (-1, -1), self.fonts["sizes"]["dense"]),

            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), int(self.fonts["sizes"]["dense"] * 0.25)),
            ('BOTTOMPADDING', (0, 0), (-1, -1), int(self.fonts["sizes"]["dense"] * 0.25)),
        ])

        styles['listed'] = TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.fonts["regular"]),
            ('FONTSIZE', (0, 0), (-1, -1), self.fonts["sizes"]["table"]),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.colors["text"]),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ])

        styles['layout'] = TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ])

        return styles


class ReportComponent:
    """
    Base class to hold the shared theme state. Avoids passing the theme manager to every single component. The theme can be set once using the apply_style method and is then available to all components as a class variable.
    """
    # Shared static variable to hold the theme manager and the translations dictionary
    style = None
    translations = {}

    @classmethod
    def apply_style(cls, theme_manager: ThemeManager, language: str):
        """
        Sets the theme once for all components.
        """
        cls.style = theme_manager
        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        translations_path = os.path.join(srcPath, "data", "report_translations.json")
        cls.__load_translations(translations_path, language)

    @classmethod
    def get_style(cls):
        """
        Returns the theme manager to access the styles. Can be used in all components after the theme has been set.
        """
        if cls.style is None:
            raise Exception(
                "Theme not set. Please call ReportComponent.apply_style(theme_manager) before creating any components.")
        return cls.style

    @classmethod
    def translate(cls, text_key: str) -> str | dict:
        """
        Translates a given key. Returns the key itself if not found.
        """
        return cls.translations.get(text_key, text_key)

    @classmethod
    def __load_translations(cls, file_path, language):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                translation_json = json.load(f)

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load translations from {file_path}. Error: {e}")
            cls.translations = {}
            return

        english_translations = translation_json["en"]
        specific_translations = translation_json.get(language, {})

        # Merge the english translations with the specific language translations, where the specific language translations overwrite the english ones
        cls.translations = english_translations | specific_translations


class BaseReportFlowable(Flowable, ReportComponent):
    """
    Base class for all Flowables in the certificate. Includes drawing of the debug frame if DEBUG is set to True
    """

    def draw(self):
        self.draw_content()

        if DEBUG:
            c = self.canv
            c.saveState()
            c.setStrokeColor(colors.red)
            c.setLineWidth(debug_line_width)
            c.rect(0, 0, self.width, self.height, stroke=1, fill=0)
            c.restoreState()

    def draw_content(self):
        """
        This method should be implemented by all child classes to draw the actual content of the Flowable.
        The base draw() method will handle the drawing of the debug frame if DEBUG is True.
        """
        raise NotImplementedError(
            "Subclasses of BaseReportFlowable must implement the draw_content() method to draw their content.")


################################################################################
# Basic Layout is a Framebox around the content
################################################################################

class FrameBox(BaseReportFlowable):
    def __init__(self, title: str, content_flowable: Flowable = None) -> None:
        """
        title: title as a string
        content_flowable: Single Flowable within the block
        """
        super().__init__()
        self.title = title  # str
        self.style = self.get_style()  # Get the ThemeManager instance to access the styles and design parameters

        # Design parameters
        self.fontstyle = self.style.get_font(bold=True)
        self.fontsize = self.style.get_font_size('section_title')
        self.font_color = self.style.get_color('text')

        # Line parameters
        self.line_width = self.style.get_line_width('medium')
        self.line_color = self.style.get_color('primary_color')

        # Padding -> Distance between content and frame
        self.padding = self.style.get_padding()

        self.width = None
        self.height = None

        # Content Flowable
        self.content_flowable = content_flowable
        self.table_full_width = False  # If True, table columns are adjusted to full width

    def set_content(self, content_flowable: Flowable, full_width: bool = False):
        """Allows placing of the content after initialization."""
        self.content_flowable = content_flowable
        self.table_full_width = full_width

    def get_available_height(self, availHeight=None):
        """Returns the available height for the content within the frame."""
        if self.height is None:
            if availHeight is not None:
                return availHeight - self.fontsize - 2 * self.padding - self.line_width
            else:
                raise ValueError(
                    "FrameBox height is not set and no availHeight is given. Call wrap() first or give <availHeight>.")
        return self.height - self.fontsize - 2 * self.padding - self.line_width

    def get_available_width(self, availWidth=None):
        """Returns the available width for the content within the frame."""
        if self.width is None:
            if availWidth is not None:
                return availWidth - 2 * self.padding - 2 * self.line_width
            else:
                raise ValueError(
                    "FrameBox width is not set and no availWidth is given. Call wrap() first or give <availWidth>.")
        return self.width - 2 * self.padding - 2 * self.line_width

    def wrap(self, availWidth, availHeight):
        # with is the total available width
        self.width = availWidth

        # height of the content area
        if self.content_flowable is not None:

            # Set the size of the content
            availContentWidth = self.get_available_width(availWidth)
            availContentHeight = self.get_available_height(availHeight)

            # dynamic column width for tables
            if isinstance(self.content_flowable, Table) and self.table_full_width:
                n_cols = len(self.content_flowable._cellvalues[0])
                col_width = (self.width - 2 * self.padding) / n_cols
                # Set the column widths
                self.content_flowable._argW = [col_width] * n_cols

            # content_height is height of the content
            content_width, content_height = self.content_flowable.wrap(availContentWidth, availContentHeight)
        else:
            content_height = 0

        # Needed Total height = title + content + padding above and below content + bottom line
        self.height = self.fontsize + content_height + 2 * self.padding + self.line_width

        return self.width, self.height

    def draw_content(self):
        """Draw the frame with title and content."""
        c = self.canv  # Canvas for frame
        c.saveState()

        w = self.width

        y_topframe = int(
            self.height - 2 * self.fontsize / 3 + self.line_width / 2)  # Position of the middle of the top line
        y_bottomframe = 0  # no padding below

        # Linestyle of the frame
        c.setStrokeColorRGB(*self.line_color)
        c.setLineWidth(self.line_width)
        c.setLineCap(2)  #

        title_text = str(self.title)  # Title should be a string

        title_w = c.stringWidth(title_text, self.fontstyle, self.fontsize)

        y_title = int(y_topframe - self.line_width / 2 - self.fontsize / 3)
        gap = 5  # small gap between line and text

        # --- Title centered between lines ---
        x_title = int(self.padding + gap)
        # --- Lines ---
        # Side frame
        c.line(0, y_topframe, 0, y_bottomframe)  # left line
        c.line(0, y_bottomframe, w, y_bottomframe)  # bottom line
        c.line(w, y_bottomframe, w, y_topframe)  # right line

        # left
        c.line(0, y_topframe, x_title - gap, y_topframe)
        # right
        c.line(x_title + title_w + gap, y_topframe, w, y_topframe)

        # --- Title ---
        c.setFont(self.fontstyle, self.fontsize)
        c.setFillColorRGB(*self.font_color)
        c.drawString(x_title, y_title, title_text)

        # Placement of content
        if self.content_flowable is not None:
            y = int(
                y_topframe - self.line_width / 2 - self.fontsize / 3 - self.padding)  # Position of the top of the content area
            x = self.padding + self.line_width
            w_f, h_f = self.content_flowable.wrap(w - 2 * x, y - y_bottomframe - self.padding - self.line_width)
            self.content_flowable.drawOn(c, x, y - h_f)

        c.restoreState()

    @classmethod
    def get_available_space_content(cls, availWidth, availHeight):
        """
        Returns the available space for content within the frame box. Where the frame box has availWidth and availHeight for itself.
        This can be used without instantiating the class. To be used for layout calculations of the content.
        """
        style = cls.get_style()

        # Same calculation as in get_available_width and get_available_height
        padding = style.get_padding()
        line_width = style.get_line_width('medium')
        title_height = style.get_font_size('section_title')

        content_width = availWidth - 2 * padding - 2 * line_width
        content_height = availHeight - 2 * padding - title_height - line_width

        return content_width, content_height


################################################################################
# Base elements (Flowables) that can be used in the layout
################################################################################

class Header(BaseReportFlowable):
    """
    This class generates the header section of the certificate.
    """

    def __init__(self, title) -> None:
        super().__init__()
        self.style = self.get_style()
        self.title = title
        self.width = None
        self.height = None

        # Design parameters
        self.fontstyle = self.style.get_font(bold=True)
        self.fontsize = self.style.get_font_size('title')
        self.font_color = self.style.get_color('text')

        # line parameters
        self.line_width = self.style.get_line_width('thick')
        self.line_color = self.style.get_color('primary_color')
        self.line_gap = 5

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = self.fontsize + self.line_gap + self.line_width
        return self.width, self.height

    def draw_content(self):
        c = self.canv
        c.saveState()

        # Header text
        c.setFont(self.fontstyle, self.fontsize)
        c.setFillColorRGB(*self.font_color)

        # Text position
        y_text = self.height - self.fontsize
        c.drawString(0, y_text, self.title)

        # Line position below the text
        c.setStrokeColorRGB(*self.line_color)
        c.setLineWidth(self.line_width)
        c.line(0, 0, self.width, 0)

        c.restoreState()


class Energiekennwerte(BaseReportFlowable):
    """
    Generates the Energiekennwerte section of the certificate.
    Arranges a summary table on the left, and a pie chart stacked above
    a max loads table on the right.
    """

    def __init__(self, kpi_data: dict, availWidth: float):
        super().__init__()
        self.style = self.get_style()
        self.width = availWidth
        self.height = 0

        self.district_key_kpis = kpi_data["district_key_kpis"]
        self.district_operation_kpis = kpi_data["district_operation_kpis"]
        self.max_loads_data = kpi_data["max_loads_table"]
        self.energy_pie_data = kpi_data["pie_chart_energy"]

        # Arrange components in a transparent layout table
        col_w_left = self.width * 0.6
        col_w_right = self.width * 0.4

        self.t_summary = self._build_listed_table(self.district_key_kpis)
        self.t_operation = self._build_listed_table(self.district_operation_kpis)
        self.pie_chart_flowable = EnergyPieChart(pie_data=self.energy_pie_data, availWidth=col_w_right)
        self.max_loads_flowable = MaxLoadsBarChart(max_loads_data=self.max_loads_data, availWidth=col_w_right)

        left_column_content = [Spacer(1, self.style.get_padding()), self.t_summary,
                               Spacer(1, 3 * self.style.get_padding()),
                               Title(self.translate("title_optimized_operation_kpis")),
                               Spacer(1, self.style.get_padding()), self.t_operation]
        right_column_content = [self.pie_chart_flowable, Spacer(1, self.style.get_padding()), self.max_loads_flowable]

        layout_data = [
            [left_column_content, right_column_content]
        ]

        self.layout_table = Table(layout_data, colWidths=[col_w_left, col_w_right])
        self.layout_table.setStyle(self.style.get_table_styles()['layout'])  # No visible styling, just for layout

    def _build_listed_table(self, data: list) -> Table:
        """Builds table with listed style."""
        t = Table(data)
        t.setStyle(self.style.get_table_styles()['listed'])

        if DEBUG:
            t.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), debug_line_width, colors.red)
            ]))

        return t

    def wrap(self, availWidth, availHeight):
        """Calculates the needed height based on the pre-built layout table."""
        _, self.height = self.layout_table.wrap(availWidth, availHeight)
        return self.width, self.height

    def draw_content(self):
        """Draws the layout table onto the canvas."""
        self.layout_table.drawOn(self.canv, 0, 0)


class EnergyPieChart(BaseReportFlowable):
    """
    Standalone Flowable that generates a pie chart for annual energy demands,
    using the configured corporate colors.
    """

    def __init__(self, pie_data: dict, availWidth: float):
        super().__init__()
        self.style = self.get_style()
        self.pie_data = pie_data
        self.availWidth = availWidth

        self.drawing = self._create_drawing()
        self.width = self.drawing.width
        self.height = self.drawing.height

    def _create_drawing(self) -> Drawing:
        """Constructs the Drawing object containing the Pie and Legend."""
        width = self.availWidth
        padding = self.style.get_padding()

        labels = []
        values = []
        slice_colors = []

        legend_font = self.style.get_font(bold=False)
        legend_size = self.style.get_font_size('small')

        title_font = self.style.get_font(bold=True)
        title_size = self.style.get_font_size('body')
        title_color = colors.Color(*self.style.get_color('text'))

        # Map pie categories to the specific keys in the colors dictionary
        color_mapping = {
            self.translate("name_el"): self.style.get_energy_color("electricity"),
            self.translate("name_heat"): self.style.get_energy_color("heating"),
            self.translate("name_dhw"): self.style.get_energy_color("dhw"),
            self.translate("name_cool"): self.style.get_energy_color("cooling"),
            self.translate("name_ev"): self.style.get_energy_color("ev")
        }

        # Enforce crash if key is missing by accessing the dictionary directly
        for key, color_rgb in color_mapping.items():
            val = self.pie_data[key]

            labels.append(key)
            values.append(float(val))
            slice_colors.append(colors.Color(*color_rgb))

        # --- Shared Legend Logic ---
        legend = Legend()
        legend.alignment = 'right'
        legend.fontName = legend_font
        legend.fontSize = legend_size
        legend.dx = 7
        legend.dy = 7
        legend.yGap = 0
        legend.deltax = 90
        legend.deltay = 10
        legend.strokeWidth = 0
        legend.strokeColor = colors.white
        legend.columnMaximum = 3

        legend.colorNamePairs = [(slice_colors[i], f"{labels[i]}: {round(values[i], 1)}") for i in range(len(labels))]

        # Place temporarily at (0,0) to calculate the bounding box
        legend.x = 0
        legend.y = 0
        bounds = legend.getBounds()
        actual_legend_width = bounds[2] - bounds[0]

        # Place the legend at the proper position based on the actual size
        legend.x = (width - actual_legend_width) / 2
        legend.y = -bounds[1]  # Ensures the true bottom rests exactly at the lower bound

        # --- Pie Chart Logic ---
        pie = Pie()
        pie.width = 90
        pie.height = 90
        pie.x = (width - pie.width) / 2

        # Place pie dynamically above the legend
        pie.y = legend.y + bounds[3] + padding

        pie.data = values
        pie.labels = None
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 1
        pie.slices.labelRadius = 1.5
        pie.slices[3].labelRadius = 1.2
        pie.slices.fontName = self.style.get_font(bold=False)

        for i in range(len(values)):
            pie.slices[i].fillColor = slice_colors[i]

        # Calculate dynamic total height based on pie top position and title space
        title_y = pie.y + pie.height + self.style.get_spacing('small')
        dynamic_height = title_y + title_size

        d = Drawing(width, dynamic_height)

        d.add(pie)
        d.add(legend)

        d.add(String(width / 2.0, title_y, self.translate("title_pie_chart_energy"),
                     fontName=title_font,
                     fontSize=title_size,
                     textAnchor='middle',
                     fillColor=title_color))

        # Draw debug boxes for internal components
        if DEBUG:
            # Pie bounding box
            d.add(Rect(pie.x, pie.y, pie.width, pie.height, strokeColor=colors.red, strokeWidth=debug_line_width,
                       fillColor=None))

            # Legend bounding box using exact final bounds
            final_bounds = legend.getBounds()
            l_x = final_bounds[0]
            l_y = final_bounds[1]
            l_w = final_bounds[2] - final_bounds[0]
            l_h = final_bounds[3] - final_bounds[1]
            d.add(Rect(l_x, l_y, l_w, l_h, strokeColor=colors.red, strokeWidth=debug_line_width, fillColor=None))

            # Title
            d.add(Rect(0, title_y, width, title_size, strokeColor=colors.red, strokeWidth=debug_line_width,
                       fillColor=None))

        return d

    def wrap(self, availWidth, availHeight):
        # The drawing has fixed dimensions, so we just return them directly
        return self.width, self.height

    def draw_content(self):
        # Draw the internal Drawing onto the Flowable's canvas
        self.drawing.drawOn(self.canv, 0, 0)


class MaxLoadsBarChart(BaseReportFlowable):
    """
    Generates a horizontal bar chart representing maximum loads with values aligned to the right.
    """

    def __init__(self, max_loads_data: list, availWidth: float):
        super().__init__()
        self.style = self.get_style()
        self.max_loads_data = max_loads_data
        self.width = availWidth
        self.height = 0
        self.row_height = self.style.get_font_size('body') + 2

        self.title_font = (self.style.get_font(bold=True), self.style.get_font_size('body'))
        self.text_font = (self.style.get_font(bold=False), self.style.get_font_size('body'))
        self.number_font = (self.style.get_font(bold=False), self.style.get_font_size('small'))

    def wrap(self, availWidth, availHeight):
        """Calculates needed height dynamically based on rows."""
        self.width = availWidth
        self.height = len(self.max_loads_data) * self.row_height + self.style.get_spacing('small') + self.title_font[
            1]  # rows + spacing + title
        return self.width, self.height

    def draw_content(self):
        """Draws labels, scaled bars, and values onto the canvas."""
        c = self.canv
        c.saveState()

        labels = []
        values_text = []
        values_num = []

        # Parse data
        for row in self.max_loads_data:
            labels.append(row[0])
            val_str = str(row[1])
            values_text.append(val_str)
            # Extract numerical value for scaling
            try:
                num = float(val_str.split()[0])
            except ValueError:
                num = 0.0
            values_num.append(num)

        max_val = max(values_num) if values_num and max(values_num) > 0 else 1

        # Title
        c.setFont(*self.title_font)
        c.setFillColorRGB(*self.style.get_color('text'))
        c.drawCentredString(self.width / 2.0, self.height - self.title_font[1], self.translate("title_max_loads"))

        # Font settings for body
        c.setFont(*self.text_font)

        # Calculate dynamic layout metrics
        max_label_width = max([c.stringWidth(lbl, *self.text_font) for lbl in labels])
        max_val_width = max([c.stringWidth(val, *self.number_font) for val in values_text])

        x_label = 0
        x_bar = max_label_width + self.style.get_padding()
        gap_after_bar = self.style.get_spacing('small')

        available_bar_width = self.width - x_bar - max_val_width - gap_after_bar
        scale_factor = available_bar_width / max_val

        bar_color = self.style.get_color('secondary_color')
        text_color = self.style.get_color('text')

        for i in range(len(values_num)):
            y_pos = self.height - self.title_font[1] - self.style.get_spacing('small') - self.text_font[1] - (
                        self.row_height * i)

            # Label
            c.setFont(*self.text_font)
            c.setFillColorRGB(*text_color)
            c.drawString(x_label, y_pos, labels[i])

            # Bar
            bar_w = values_num[i] * scale_factor
            c.setFillColorRGB(*bar_color)
            c.rect(x_bar, y_pos, bar_w, 6, stroke=0, fill=1)

            # Value
            c.setFont(*self.number_font)
            c.setFillColorRGB(*text_color)
            c.drawString(x_bar + bar_w + gap_after_bar, y_pos, values_text[i])

        c.restoreState()


class Title(BaseReportFlowable):
    """A simple Flowable to draw a centered bold title."""

    def __init__(self, title_text: str):
        super().__init__()
        self.style = self.get_style()
        self.title_text = title_text
        self.font = self.style.get_font(bold=True)
        self.font_size = self.style.get_font_size('subsection_title')
        self.color = self.style.get_color('text')
        self.width = 0
        self.height = self.font_size + 4

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return self.width, self.height

    def draw_content(self):
        c = self.canv
        c.setFont(self.font, self.font_size)
        c.setFillColorRGB(*self.color)
        c.drawString(0, 0, self.title_text)


class Quartiersstruktur(BaseReportFlowable):
    """
    This class generates the Quartiersstruktur section of the certificate providing a summary of the building stock and the neighborhood characteristics.
    """

    def __init__(self, summary_table_data: list, general_info: list) -> None:
        super().__init__()
        self.style = self.get_style()
        self.width = None
        self.height = None

        # Build the table
        self.table = Table(summary_table_data)
        self.table.setStyle(self.style.get_table_styles()['standard'])

        self.info_table = Table(general_info)
        self.info_table.setStyle(self.style.get_table_styles()['listed'])

        if DEBUG:
            self.table.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), debug_line_width, colors.red)
            ]))
            self.info_table.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), debug_line_width, colors.red)
            ]))

    def wrap(self, availWidth, availHeight):
        self.width = availWidth

        # Main table width (90% of available space to prevent squeezing)
        n_cols = len(self.table._cellvalues[0])
        col_w = (availWidth * 0.9) / n_cols
        self.table._argW = [col_w, col_w, col_w, col_w]  # All columns same width
        self.table_width, self.table_height = self.table.wrap(availWidth, availHeight)

        # Info table width
        self.info_table_width, self.info_height = self.info_table.wrap(availWidth, availHeight)

        # Total height: Main Table + Padding + Info Table
        self.height = self.table_height + self.style.get_padding() + self.info_height
        return self.width, self.height

    def draw_content(self):
        c = self.canv
        y = self.height

        # Main Table (centered)
        x_offset = (self.width - self.table_width) / 2.0
        self.table.drawOn(c, x_offset, y - self.table_height)

        y -= self.table_height + self.style.get_padding()

        # Info Table (centered)
        x_offset = (self.width - self.info_table_width) / 2.0
        self.info_table.drawOn(c, x_offset, y - self.info_height)


class Footer(BaseReportFlowable):
    """
    This class generates the Footer section of the certificate. Visiable on the bottom of the first page.
    """

    def __init__(self, scenario_name) -> None:
        super().__init__()
        self.scenario_name = scenario_name
        self.style = self.get_style()

        # Design Parameters
        self.normal_fontstyle = self.style.get_font(bold=False)
        self.normal_fontsize = self.style.get_font_size('small')
        self.normal_fontcolor = self.style.get_color('text_light')

        self.highlight_fontstyle = self.style.get_font(bold=True)
        self.highlight_fontsize = self.style.get_font_size('highlighted')
        self.highlight_fontcolor = self.style.get_color('text')

        # Line Parameters
        self.line_width = self.style.get_line_width('medium')
        self.line_color = self.style.get_color('primary_color')

        self.padding = self.style.get_padding()

        self.width = None
        self.height = None

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = max(self.normal_fontsize, self.highlight_fontsize) + 2 * self.padding + 2 * self.line_width
        return self.width, self.height

    def draw_content(self):
        w = self.width
        h = self.height
        c = self.canv
        c.saveState()

        # Draw the lines around the footer
        c.setStrokeColorRGB(*self.line_color)
        c.setLineWidth(self.line_width)
        c.rect(0, 0, w, h, stroke=1, fill=0)

        # Draw the text
        available_height = h - 2 * self.padding - 2 * self.line_width
        text_height = max(self.normal_fontsize, self.highlight_fontsize)
        y = self.padding + self.line_width + available_height / 2 - text_height / 3

        x1 = self.padding + self.line_width
        string1 = self.translate("ui_footer_name")
        length1 = c.stringWidth(string1, self.highlight_fontstyle, self.highlight_fontsize)
        gap = 3
        string2 = str(self.scenario_name)
        string3 = f"{self.translate('ui_footer_created')} {datetime.now().strftime('%d.%m.%Y %H:%M')}"

        c.setFont(self.highlight_fontstyle, self.highlight_fontsize)
        c.setFillColorRGB(*self.highlight_fontcolor)
        c.drawString(x1, y, string1)

        c.setFont(self.normal_fontstyle, self.normal_fontsize)
        c.setFillColorRGB(*self.normal_fontcolor)
        c.drawString(x1 + length1 + gap, y, string2)

        c.drawRightString(w - self.padding - self.line_width, y, string3)
        c.restoreState()

    @classmethod
    def get_required_height(cls, pagesize: tuple = A4):
        """
        Returns the required height for the footer.
        Can be used without instantiating the class.
        """
        style = cls.get_style()

        # Design Parameters (same as for __init__)
        normal_fontsize = style.get_font_size('small')
        highlight_fontsize = style.get_font_size('highlighted')

        # Line Parameters
        line_width = style.get_line_width('medium')
        padding = style.get_padding()

        # height calculated same as in wrap()
        required_height = max(normal_fontsize, highlight_fontsize) + 2 * padding + 2 * line_width

        return required_height


class EnergyHub(BaseReportFlowable):
    """
    Flowable that handles the visual layout of the Energy Hub content.
    Provides a class method to handle pagination and FrameBox wrapping.
    """

    def __init__(self, content_flowable: Flowable):
        super().__init__()
        self.style = self.get_style()
        self.content_flowable = content_flowable
        self.width = None
        self.height = None

    def wrap(self, availWidth, availHeight):
        self.width = availWidth

        if hasattr(self.content_flowable, 'table'):
            target_table = self.content_flowable.table
        elif isinstance(self.content_flowable, Table):
            target_table = self.content_flowable
        else:
            target_table = None

        if target_table:
            n_cols = len(target_table._cellvalues[0])
            target_table._argW = [availWidth / n_cols] * n_cols

        _, self.height = self.content_flowable.wrap(availWidth, availHeight)
        return self.width, self.height

    def draw_content(self):
        # Delegate drawing to the internal content
        self.content_flowable.drawOn(self.canv, 0, 0)

        # here additional specifics can be added

    @classmethod
    def create_boxes(cls, data_energyhub: pd.DataFrame, availWidth: float, availHeight: float) -> list:
        """Creates a list of FrameBox objects for the Energy Hub data."""
        style = cls.get_style()
        boxes = []
        title = cls.translate("title_central_devices")

        # Handle empty data
        if data_energyhub is None or data_energyhub.empty:
            box = FrameBox(title=title)
            p = Paragraph(cls.translate("msg_no_central_devices"), style.get_paragraph_styles()['Normal'])
            box.set_content(cls(content_flowable=p))
            boxes.append(box)
            return boxes

        # Handle data with pagination
        eh_tables = PaginatedDataFrameTable.create_all_tables(
            availWidth=availWidth,
            availHeight=availHeight,
            input_data=data_energyhub,
            style_name='standard'
        )

        # Check if it fits on exactly one page
        if len(eh_tables) == 1:
            box = FrameBox(title=title)
            box.set_content(cls(content_flowable=eh_tables[0].table))
            boxes.append(box)

        else:
            for i, eh_table in enumerate(eh_tables, start=1):
                box = FrameBox(title=f"{title} ({i}/{len(eh_tables)})")
                box.set_content(cls(content_flowable=eh_table))
                boxes.append(box)

        return boxes


class DecentralSystems(BaseReportFlowable):
    """
    Flowable that handles the visual layout of the Decentral Systems content.
    Provides a class method to handle pagination and FrameBox wrapping.
    """

    def __init__(self, content_flowable: Flowable):
        super().__init__()
        self.style = self.get_style()
        self.content_flowable = content_flowable
        self.width = None
        self.height = None

    def wrap(self, availWidth, availHeight):
        self.width = availWidth

        if hasattr(self.content_flowable, 'table'):
            target_table = self.content_flowable.table
        elif isinstance(self.content_flowable, Table):
            target_table = self.content_flowable
        else:
            target_table = None

        if target_table:
            n_cols = len(target_table._cellvalues[0])
            target_table._argW = [availWidth / n_cols] * n_cols

        _, self.height = self.content_flowable.wrap(availWidth, availHeight)
        return self.width, self.height

    def draw_content(self):
        # Delegate drawing to the internal content
        self.content_flowable.drawOn(self.canv, 0, 0)

    @classmethod
    def create_boxes(cls, data_decentral: pd.DataFrame, availWidth: float, availHeight: float) -> list:
        """Creates a list of FrameBox objects for the Decentral Systems data."""
        style = cls.get_style()
        boxes = []
        title = cls.translate("title_decentral_devices")
        # Handle empty data
        if data_decentral is None or data_decentral.empty:
            box = FrameBox(title=title)
            p = Paragraph(cls.translate("msg_no_decentral_devices"), style.get_paragraph_styles()['Normal'])
            box.set_content(cls(content_flowable=p))
            boxes.append(box)
            return boxes

        # Handle data with pagination
        dec_tables = PaginatedDataFrameTable.create_all_tables(
            availWidth=availWidth,
            availHeight=availHeight,
            input_data=data_decentral,
            style_name='standard'
        )

        # Check if it fits on exactly one page
        if len(dec_tables) == 1:
            box = FrameBox(title=title)
            box.set_content(cls(content_flowable=dec_tables[0].table))
            boxes.append(box)

        else:
            for i, dec_table in enumerate(dec_tables, start=1):
                box = FrameBox(title=f"{title} ({i}/{len(dec_tables)})")
                box.set_content(cls(content_flowable=dec_table))
                boxes.append(box)

        return boxes


class EnergyHubProfilesYear(BaseReportFlowable):
    """
    Renders all EnergyHub cluster profiles for one simulated year on a single page.
    Generates EXACTLY ONE master legend at the bottom of the page.
    Strictly adheres to the ThemeManager configuration for fonts, colors, and layout widths.
    """

    def __init__(self, year_profiles: dict, cluster_info: dict):
        super().__init__()
        self.style = self.get_style()
        self.year_profiles = year_profiles or {}
        self.cluster_info = cluster_info
        self.width = 0
        self.height = 0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = availHeight
        return self.width, self.height

    def _series_from_profile(self, profile_df: pd.DataFrame, series_names: list[str]) -> dict[str, list[float]]:
        series = {}
        for series_name in series_names:
            if series_name in profile_df.columns:
                series[series_name] = profile_df[series_name].tolist()
        return series

    def _format_sig(self, x, sig):
        if x == 0:
            return "0"
        decimals = sig - 1 - int(math.floor(math.log10(abs(x))))
        return f"{x:.{max(0, decimals)}f}"

    def _nice_num(self, x):
        exp = math.floor(math.log10(x))
        frac = x / 10 ** exp

        if frac <= 1:
            nice = 1
        elif frac <= 2:
            nice = 2
        elif frac <= 5:
            nice = 5
        else:
            nice = 10

        return nice * 10 ** exp

    def _build_plot(self, width: float, height: float, title_key: str, series_map: dict[str, list[float]],
                    dynamic_color_mapping: dict, show_x_axis: bool = True) -> Drawing:
        drawing = Drawing(width, height)

        # 1. Fonts and Colors
        plot_title_size = self.style.get_font_size('body')
        axis_font = self.style.get_font(bold=False)
        axis_size = self.style.get_font_size('axis_values')
        axis_label_font = self.style.get_font(bold=False)
        axis_label_size = self.style.get_font_size('small')
        font_color = colors.Color(*self.style.get_color('text'))

        # 2. Asymmetrische Placement Calculations
        padding = self.style.get_padding()
        x_align_right = 3 * padding
        x_align_left = (4 * padding) + axis_label_size

        chart_width = width - x_align_left - x_align_right
        center_x = x_align_left + (chart_width / 2.0)

        # Prefer device-level series, but keep totals as a fallback if no detailed series survived filtering.
        valid_series_map = {k: v for k, v in series_map.items() if v}
        detailed_series_map = {
            k: v for k, v in valid_series_map.items()
            if not any(x in k.lower() for x in ["generation_total", "consumption_total"])
        }
        filtered_series_map = detailed_series_map if detailed_series_map else valid_series_map

        if not filtered_series_map or height < 20:
            drawing.add(String(center_x, max(5, height / 2.0), self.translate("msg_no_data"),
                               textAnchor='middle', fontName=self.style.get_font(bold=False),
                               fontSize=plot_title_size, fillColor=font_color))
            if DEBUG:
                drawing.add(
                    Rect(x_align_left, 0, chart_width, height, strokeColor=colors.red, strokeWidth=debug_line_width,
                         fillColor=None))
            return drawing

        max_len = max(len(values) for values in filtered_series_map.values())

        cluster_length_hours = self.cluster_info.get('cluster_length_sec', 604800) / 3600.0
        time_step_hours = cluster_length_hours / max(1, max_len)
        x_values = [i * time_step_hours for i in range(max_len)]
        x_max_val = max(1, max_len - 1) * time_step_hours

        series_items = []
        for name, vals in filtered_series_map.items():
            clean_vals = [v if pd.notna(v) else 0.0 for v in vals]
            series_items.append((name, clean_vals))

        pos_series_items = sorted(
            series_items,
            key=lambda item: sum(v for v in item[1] if v > 0),
            reverse=True
        )
        neg_series_items = sorted(
            series_items,
            key=lambda item: abs(sum(v for v in item[1] if v < 0)),
            reverse=True
        )

        pos_plot_data = []
        pos_line_configs = []
        current_pos_cum = [0.0] * max_len

        neg_plot_data = []
        neg_line_configs = []
        current_neg_cum = [0.0] * max_len

        # Positive stacks: largest producer first, so it becomes the visible base layer.
        for name, clean_vals in pos_series_items:
            clean_name = name.replace("Power_kW_", "").replace("Heat_kW_", "")
            color = dynamic_color_mapping.get(clean_name, colors.black)

            # positive (Import from grid / generation)
            pos_vals = [v if v > 0 else 0.0 for v in clean_vals]
            if any(v > 0 for v in pos_vals):
                current_pos_cum = [c + v for c, v in zip(current_pos_cum, pos_vals)]
                poly_data = [(x_values[0], 0.0)] + list(zip(x_values, current_pos_cum)) + [(x_values[-1], 0.0)]
                pos_plot_data.append(poly_data)
                pos_line_configs.append({'color': color})

        # Negative stacks: largest consumer first, mirroring the producer ordering.
        for name, clean_vals in neg_series_items:
            clean_name = name.replace("Power_kW_", "").replace("Heat_kW_", "")
            color = dynamic_color_mapping.get(clean_name, colors.black)

            # negative (Export to grid / consumption)
            neg_vals = [v if v < 0 else 0.0 for v in clean_vals]
            if any(v < 0 for v in neg_vals):
                current_neg_cum = [c + v for c, v in zip(current_neg_cum, neg_vals)]
                poly_data = [(x_values[0], 0.0)] + list(zip(x_values, current_neg_cum)) + [(x_values[-1], 0.0)]
                neg_plot_data.append(poly_data)
                neg_line_configs.append({'color': color})

        # Ensure largest values are in the back
        pos_plot_data.reverse()
        pos_line_configs.reverse()
        neg_plot_data.reverse()
        neg_line_configs.reverse()

        stack_data = pos_plot_data + neg_plot_data
        stack_configs = pos_line_configs + neg_line_configs

        # symmetric y-axis around zero
        max_stacked_pos = max(current_pos_cum) if current_pos_cum else 0
        min_stacked_neg = min(current_neg_cum) if current_neg_cum else 0

        max_abs_y = max(abs(min_stacked_neg), max_stacked_pos)
        max_abs_y = self._nice_num(max_abs_y) if max_abs_y > 0 else 1
        y_min = -max_abs_y
        y_max = max_abs_y

        if (y_max - y_min) < 0.1:
            y_min = math.floor(y_min) - 1
            y_max = math.ceil(y_max) + 1

        # --- LAYER 1: Draw the stacked polygons ---
        plot_height_val = max(1, height)
        x_scale = chart_width / x_max_val if x_max_val > 0 else 1
        y_scale = plot_height_val / (y_max - y_min)

        for data_series, config in zip(stack_data, stack_configs):
            pts = []
            for x_val, y_val in data_series:
                px = x_align_left + x_val * x_scale
                py = 0 + (y_val - y_min) * y_scale
                pts.extend([px, py])

            poly = Polygon(pts)
            poly.fillColor = config['color']
            poly.strokeColor = config['color']
            poly.strokeWidth = 0.5
            drawing.add(poly)

        # --- LAYER 2: Draw the exact gray zero line ---
        if y_min <= 0 <= y_max:
            zero_y_pixel = 0 + (0 - y_min) * y_scale
            zero_line = Line(x_align_left, zero_y_pixel, x_align_left + chart_width, zero_y_pixel)
            zero_line.strokeColor = colors.Color(0, 0, 0)
            zero_line.strokeWidth = 0.4
            drawing.add(zero_line)

        g = Group()
        g.rotate(90)

        title_string = String(height / 2.0, - (axis_label_size), self.translate(title_key),
                              fontName=axis_label_font,
                              fontSize=axis_label_size,
                              textAnchor='middle',
                              fillColor=font_color)
        g.add(title_string)
        drawing.add(g)

        # --- LAYER 3: Draw the line plot ---
        plot = LinePlot()
        plot.x = x_align_left
        plot.y = 0
        plot.width = chart_width
        plot.height = plot_height_val

        plot.data = [[(0, 0)]]  # Dummy-Data
        plot.joinedLines = 1

        plot.xValueAxis.valueMin = 0
        plot.xValueAxis.valueMax = x_max_val

        # Determine xAxis valueStep based on the total time span
        if x_max_val <= 24:
            x_step = 3  # 3 hour steps for up to 1 day
        elif x_max_val <= 48:
            x_step = 6  # 6 hour steps for up to 2 days
        elif x_max_val <= 24 * 4:
            x_step = 12  # 12 hour steps for up to 4 days
        elif x_max_val <= 24 * 14:
            x_step = 24  # 24 hour steps for up to 14 days
        else:
            x_step = 168  # 168 hour steps for longer periods

        plot.xValueAxis.valueStep = x_step
        plot.xValueAxis.labels.fontName = axis_font
        plot.xValueAxis.labels.fontSize = axis_size
        plot.xValueAxis.labels.fillColor = font_color
        plot.xValueAxis.visibleGrid = 1
        plot.xValueAxis.gridStrokeColor = colors.Color(0.85, 0.85, 0.85)
        plot.xValueAxis.gridStrokeDashArray = [2, 2]

        plot.xValueAxis.visibleLabels = 1 if show_x_axis else 0
        plot.xValueAxis.visibleTicks = 1 if show_x_axis else 0
        plot.xValueAxis.visibleAxis = 0

        plot.yValueAxis.valueMin = y_min
        plot.yValueAxis.valueMax = y_max
        plot.yValueAxis.valueStep = max(0.1, (y_max - y_min) / 4)
        plot.yValueAxis.labelTextFormat = lambda v: self._format_sig(v, 2)
        plot.yValueAxis.labels.fontName = axis_font
        plot.yValueAxis.labels.fontSize = axis_size
        plot.yValueAxis.labels.fillColor = font_color
        plot.yValueAxis.visibleGrid = 0
        plot.yValueAxis.visibleTicks = 1

        # Remove the dummy line
        plot.lines[0].strokeColor = colors.transparent
        plot.lines[0].fillColor = None

        drawing.add(plot)
        if show_x_axis:
            x_label = String(center_x, - 2.3 * axis_label_size, self.translate("Hours"),
                             fontName=axis_label_font,
                             fontSize=axis_label_size,
                             textAnchor='middle',
                             fillColor=font_color)
            drawing.add(x_label)

        if DEBUG:
            drawing.add(Rect(x_align_left, 0, chart_width, height, strokeColor=colors.red, strokeWidth=debug_line_width,
                             fillColor=None))
            drawing.add(Rect(0, 0, axis_label_size, height, strokeColor=colors.blue, strokeWidth=debug_line_width,
                             fillColor=None))

        return drawing

    def draw_content(self):
        cluster_names = list(sorted(self.year_profiles.keys(), key=lambda value: str(value)))
        font_color = colors.Color(*self.style.get_color('text'))
        padding = self.style.get_padding()

        if not cluster_names:
            self.canv.setFont(self.style.get_font(bold=False), self.style.get_font_size('body'))
            self.canv.setFillColor(font_color)
            self.canv.drawString(padding, self.height - 12, "No EnergyHub profiles available for this year.")
            return

        # =========================================================
        # 1. PRE-PROCESSING: Aggregate all unique series names
        # =========================================================
        base_series_names = set()
        for profile_df in self.year_profiles.values():
            for col in profile_df.columns:
                if col.startswith("Power_kW_") or col.startswith("Heat_kW_"):
                    if not any(x in col.lower() for x in ["generation_total", "consumption_total"]):
                        clean_col = col.replace("Power_kW_", "").replace("Heat_kW_", "")
                        base_series_names.add(clean_col)

        # =========================================================
        # 2. CREATE MASTER COLOR MAPPING
        # =========================================================
        device_palette = [
            colors.HexColor('#d62728'),
            colors.HexColor('#1f77b4'),
            colors.HexColor('#2ca02c'),
            colors.HexColor('#ff7f0e'),
            colors.HexColor('#9467bd'),
            colors.HexColor('#17becf'),
            colors.HexColor('#e377c2'),
            colors.HexColor('#bcbd22'),
            colors.HexColor('#8c564b'),
            colors.HexColor('#f1c40f'),
            colors.HexColor('#3498db'),
            colors.HexColor('#e74c3c'),
            colors.HexColor('#2ecc71'),
            colors.HexColor('#9b59b6'),
            colors.HexColor('#d35400'),
            colors.HexColor('#1abc9c')
        ]

        device_base_names = sorted(list(base_series_names))

        # Assign colors based on the device palette, with a special case for "residual_grid"
        def resolve_device_color(name: str, index: int) -> colors.Color:
            if "residual_grid" in name.lower():
                return colors.Color(0.7, 0.7, 0.7)  # light gray for grid residuals
            if device_palette:
                return device_palette[index % len(device_palette)]
            return colors.black

        # Color Mapping for all devices
        dynamic_color_mapping = {}
        normal_idx = 0
        for name in device_base_names:
            if "residual_grid" in name.lower():
                dynamic_color_mapping[name] = resolve_device_color(name, 0)
            else:
                dynamic_color_mapping[name] = resolve_device_color(name, normal_idx)
                normal_idx += 1

        # =========================================================
        # 3. CREATE AND DRAW MASTER LEGEND
        # =========================================================
        legend = Legend()
        legend.fontName = self.style.get_font(bold=False)
        legend.fontSize = self.style.get_font_size('small')
        legend.dx = 8
        legend.dy = 8
        legend.yGap = 0
        legend.deltay = 12
        legend.strokeWidth = 0
        legend.dxTextSpace = self.style.get_spacing('medium')
        legend.variColumn = True
        legend.columnMaximum = 4
        legend.alignment = 'right'

        legend_pairs = []

        for name in device_base_names:
            color = dynamic_color_mapping.get(name, colors.black)

            display_name = self.translate(f"device_{name}")

            # Fallback formatting for unmapped translations (e.g., 'residual_grid' -> 'Residual grid')
            if display_name == f"device_{name}" or display_name == name:
                display_name = name.replace("_", " ").capitalize()

            if not any(display_name == existing_name for _, existing_name in legend_pairs):
                legend_pairs.append((color, display_name))

        legend.colorNamePairs = legend_pairs

        # Calculate bounds and place at the bottom
        legend.x = 0
        legend.y = 0
        bounds = legend.getBounds()
        legend_width = bounds[2] - bounds[0]
        legend_height = bounds[3] - bounds[1]

        legend_x_pos = (self.width - legend_width) / 2

        # Adjust legend position (ReportLab legends grow downwards)
        legend.x = legend_x_pos
        legend.y = -bounds[1]

        legend_drawing = Drawing(self.width, legend_height + padding)
        legend_drawing.add(legend)

        if DEBUG:
            legend_drawing.add(
                Rect(legend_x_pos, 0, legend_width, legend_height, strokeColor=colors.red, strokeWidth=debug_line_width,
                     fillColor=None))

        legend_drawing.drawOn(self.canv, 0, 0)

        # =========================================================
        # 4. DISTRIBUTE REMAINING SPACE TO CLUSTER PLOTS
        # =========================================================
        gap = self.style.get_spacing('medium')  # gap between clusters
        usable_height = self.height - legend_height - padding  # Padding above the legend

        available_height = usable_height - gap * (len(cluster_names) - 1)
        cluster_slot_height = available_height / len(cluster_names)
        cluster_title_size = self.style.get_font_size('body')

        for index, cluster_name in enumerate(cluster_names):
            profile_df = self.year_profiles[cluster_name]

            top_y = self.height - index * (cluster_slot_height + gap)
            bottom_y = top_y - cluster_slot_height

            if DEBUG:
                self.canv.saveState()
                self.canv.setStrokeColor(colors.red)
                self.canv.setLineWidth(debug_line_width)
                self.canv.rect(0, bottom_y, self.width, cluster_slot_height, stroke=1, fill=0)
                self.canv.restoreState()

            cluster_title_y = top_y - cluster_title_size
            self.canv.setFont(self.style.get_font(bold=True), cluster_title_size)
            self.canv.setFillColor(font_color)

            title_text = f"{self.translate('Cluster')} {cluster_name}: {self.cluster_info[cluster_name]['span']} ({self.translate('Weight')}: {int(self.cluster_info[cluster_name]['weight'])})"
            self.canv.drawString(padding, cluster_title_y, title_text)

            if DEBUG:
                title_width = self.canv.stringWidth(title_text, self.style.get_font(bold=True), cluster_title_size)
                self.canv.saveState()
                self.canv.setStrokeColor(colors.red)
                self.canv.setLineWidth(debug_line_width)
                self.canv.rect(padding, cluster_title_y, title_width, cluster_title_size, stroke=1, fill=0)
                self.canv.restoreState()

            inner_top = cluster_title_y - gap

            axis_label_size = self.style.get_font_size('small')
            x_axis_padding = axis_label_size * 2.3

            inner_height = max(1, inner_top - (bottom_y + x_axis_padding))
            plot_gap = self.style.get_padding()
            plot_height = max(1, (inner_height - plot_gap) / 2)

            power_cols = [c for c in profile_df.columns if c.startswith("Power_kW_")]
            heat_cols = [c for c in profile_df.columns if c.startswith("Heat_kW_")]

            power_series = self._series_from_profile(profile_df, power_cols)
            heat_series = self._series_from_profile(profile_df, heat_cols)

            power_plot = self._build_plot(self.width, plot_height, "name_el", power_series, dynamic_color_mapping,
                                          show_x_axis=False)
            heat_plot = self._build_plot(self.width, plot_height, "name_heat", heat_series, dynamic_color_mapping,
                                         show_x_axis=True)

            heat_plot.drawOn(self.canv, 0, bottom_y + x_axis_padding)
            power_plot.drawOn(self.canv, 0, bottom_y + x_axis_padding + plot_height + plot_gap)


class YearlyStackedBarCharts(BaseReportFlowable):
    """
    Generates stacked bar charts for each simulated year, with a shared legend below.
    """

    def __init__(self, costs_data: list, co2_data: list, availWidth: float, availHeight: float,
                 observation_time: int = None):
        super().__init__()
        self.style = self.get_style()
        self.costs_data = costs_data
        self.co2_data = co2_data
        self.availWidth = availWidth
        self.availHeight = availHeight
        self.observation_time = observation_time

        self.drawing = self._create_drawing()
        self.width = self.drawing.width
        self.height = self.drawing.height

    def _create_drawing(self) -> Drawing:
        # Interpolation points (years) and categories for both charts
        years = sorted([item["Year"] for item in self.costs_data])
        years_co2 = sorted([item["Year"] for item in self.co2_data])
        if years != years_co2:
            raise ValueError(
                f"Mismatch in years between costs_data and co2_data ({years} vs {years_co2}). Ensure both datasets cover the same years as Simulations are linked.")

        year_labels = []
        for i in range(len(years)):
            start_year = years[i]

            if i < len(years) - 1:
                # Das Ende ist das Folgejahr minus 1
                end_year = years[i + 1] - 1
            else:
                # Der letzte Balken nutzt die observation_time als Obergrenze
                end_year = self.observation_time - 1

            year_labels.append(f"{start_year} - {end_year}")

        # Define categories (excluding 'Year' values)
        cost_categories = [k for k in self.costs_data[0].keys() if k != "Year"]
        co2_categories = [k for k in self.co2_data[0].keys() if k != "Year"]

        # Combine all categories for the shared legend
        all_categories = list(dict.fromkeys(cost_categories + co2_categories))

        # Format data for ReportLab VerticalBarChart (list of tuples/lists per category across all years)
        cost_series = []
        for cat in cost_categories:
            series = [next(item[cat] for item in self.costs_data if item["Year"] == y) for y in years]
            cost_series.append(tuple(series))

        co2_series = []
        for cat in co2_categories:
            series = [next(item[cat] for item in self.co2_data if item["Year"] == y) for y in years]
            co2_series.append(tuple(series))

        # Define order of charts and titles from Bottom to Top

        charts_config = [
            {
                "title": f"{self.translate('title_emissions_graph')} (t/a)",
                "series": co2_series,
                "categories": co2_categories
            },
            {
                "title": f"{self.translate('title_cost_graph')} (€/a)",
                "series": cost_series,
                "categories": cost_categories
            }
        ]

        # CO2 Emissions in t/a or kg/a
        max_co2 = max([max(series) for series in co2_series]) if co2_series else 0  # Unit in t/a
        if max_co2 < 5:
            co2_series = [tuple(val * 1000 for val in series) for series in co2_series]
            charts_config[0]["title"] = f"{self.translate('title_emissions_graph')} (kg/a)"
            charts_config[0]["series"] = co2_series

        # Costs in t€/a or €/a
        max_costs = max([max(series) for series in cost_series]) if cost_series else 0  # Unit in €/a
        if max_costs > 5000:
            cost_series = [tuple(val / 1000 for val in series) for series in cost_series]
            charts_config[1][
                "title"] = f"{self.translate('title_cost_graph')} ({self.translate('name_for_thousand')} €/a)"
            charts_config[1]["series"] = cost_series

        # --- Base Layout ---

        # Fonts
        title_font = self.style.get_font(bold=True)
        title_size = self.style.get_font_size('body')

        axis_font = self.style.get_font(bold=False)
        axis_size = self.style.get_font_size('axis_values')

        axis_label_font = self.style.get_font(bold=False)
        axis_label_size = self.style.get_font_size('small')

        legend_font = self.style.get_font(bold=False)
        legend_size = self.style.get_font_size('small')

        legend_max_cols = 3
        num_legend_items = len(all_categories)

        # Helper function to get color mapping
        def get_cat_color(category):
            """Returns the color based on the exact dictionary key string."""
            try:
                # Direct mapping of your exact keys to the theme color types
                mapping = {
                    self.translate("name_central_costs"): "eh_fixed",
                    self.translate("name_decentral_costs"): "decentral_fixed",
                    self.translate("name_el"): "electricity",
                    self.translate("name_gas"): "gas",
                    self.translate("name_biomethane"): "biomethane",
                    self.translate("name_oil"): "oil",
                    self.translate("name_waste"): "waste",
                    self.translate("name_biomass"): "biomass",
                    self.translate("name_district_heat"): "district_heat",
                    self.translate("name_hydrogen"): "hydrogen",
                    self.translate("name_feed_in_revenue"): "revenue_feed_in_el"
                }

                # Check if the exact string exists in our mapping
                if category in mapping:
                    color_key = mapping[category]
                    return self.style.get_source_color(color_key)

                # Fallback if the string is not in the explicit list
                print(
                    f"Warning: Category '{category}' not found in color mapping. Using secondary color as fallback. Check if color {mapping[category]} is defined in the config.")
                return self.style.get_color("secondary_color")

            except KeyError:
                # Fallback if the color key itself is missing in the theme config
                print(
                    f"Warning: Category '{category}' not defined in color mapping. Using secondary color as fallback.")
                return self.style.get_color("secondary_color")

        # --- Placement Calculations ---
        padding = self.style.get_padding()
        drawing_width = self.availWidth
        x_align = 3 * self.style.get_padding()
        chart_width = drawing_width - 2 * x_align  # Leave padding on the sides

        d = Drawing(drawing_width, self.availHeight)

        # --- Shared Legend ---
        legend = Legend()
        legend.fontName = legend_font
        legend.fontSize = legend_size
        legend.dx = 8
        legend.dy = 8
        legend.yGap = 0
        legend.deltay = 12
        legend.strokeWidth = 0
        legend.dxTextSpace = self.style.get_spacing('medium')
        legend.variColumn = True
        legend.columnMaximum = legend_max_cols
        legend.alignment = 'right'

        legend_pairs = [(colors.Color(*get_cat_color(cat)), cat) for cat in all_categories]
        legend.colorNamePairs = legend_pairs

        # Center legend
        num_columns = math.ceil(num_legend_items / legend.columnMaximum)
        actual_legend_width = num_columns * legend.deltax

        # Place temporarily at (0,0) to calculate the bounding box and get the actual width and height of the legend
        legend.x = 0
        legend.y = 0
        bounds = legend.getBounds()
        actual_legend_width = bounds[2] - bounds[0]
        actual_legend_height = bounds[3] - bounds[1]

        # Place the legend at the proper position based on the actual size
        legend.x = (drawing_width - actual_legend_width) / 2
        legend.y = padding + actual_legend_height
        d.add(legend)

        # Debugging: Draw bounding box around the legend
        if DEBUG:
            d.add(Rect(legend.x, padding, actual_legend_width, actual_legend_height, strokeColor=colors.red,
                       strokeWidth=debug_line_width, fillColor=None))

        current_y = legend.y + padding  # LOWER LIMIT NO element should extend below this!

        # --- Dynamic Height Calculation --
        num_charts = len(charts_config)
        remaining_space = self.availHeight - current_y
        remaining_space -= padding * (num_charts - 1)  # Account for padding between charts

        max_block_height = 200
        total_chart_height = min(remaining_space / num_charts, max_block_height)

        # Iterate through the charts to draw them according to the defined charts_config
        for chart in charts_config:
            setoff_chart_start = (axis_label_size) + self.style.get_spacing("small") + (axis_size * 1.2)
            title_height = title_size * 1.2
            chart_height = total_chart_height - setoff_chart_start - title_height - padding  # Leave space for title and axis labels

            bc = VerticalBarChart()
            bc.x = x_align
            bc.y = current_y + setoff_chart_start
            bc.height = chart_height
            bc.width = chart_width
            bc.data = chart["series"]
            bc.categoryAxis.categoryNames = year_labels
            bc.categoryAxis.labels.fontName = axis_font
            bc.categoryAxis.labels.fontSize = axis_size
            bc.valueAxis.labels.fontName = axis_font
            bc.valueAxis.labels.fontSize = axis_size
            bc.categoryAxis.style = 'stacked'

            for i, cat in enumerate(chart["categories"]):
                bc.bars[i].fillColor = colors.Color(*get_cat_color(cat))
                bc.bars[i].strokeWidth = 0

            d.add(bc)

            title_y = current_y + chart_height + padding + setoff_chart_start
            d.add(String(bc.x + chart_width / 2, title_y, chart["title"], fontName=title_font, fontSize=title_size,
                         textAnchor='middle'))
            d.add(String(bc.x + chart_width / 2, current_y, self.translate("axis_title_simulated_year"),
                         fontName=axis_label_font, fontSize=axis_label_size, textAnchor='middle'))

            total_chart_height = title_y - current_y + title_size

            # For debug purposes: Draw bounding boxes around the charts
            if DEBUG:
                d.add(Rect(bc.x, current_y, bc.width, total_chart_height, strokeColor=colors.red,
                           strokeWidth=debug_line_width, fillColor=None))

            current_y += total_chart_height + padding  # Next chart starts after the chart height including the title and all text.

        # Shrink the drawing height to the actual used height
        d.height = current_y
        return d

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw_content(self):
        self.drawing.drawOn(self.canv, 0, 0)


class InputDataTable(BaseReportFlowable):
    """
    This class generates the Input Data Table section of the certificate.
    """

    def __init__(self, input_data: pd.DataFrame = None) -> None:
        super().__init__()
        self.style = self.get_style()

        self.width = None
        self.height = None
        self.actual_height = None

        if input_data is None or input_data.empty:
            self.input_data = pd.DataFrame()
            table_data = []
        else:
            self.input_data = input_data.copy()
            self.input_data = self.input_data.fillna("-").astype(str)

            header = self.input_data.columns.tolist()
            body = self.input_data.values.tolist()
            table_data = [header] + body

        self.table = Table(table_data)

        # Apply the pre-configured TableStyle
        self.table_style = self.style.get_table_styles()['input_data']
        self.table.setStyle(self.table_style)

    def wrap(self, availWidth, availHeight):
        # Calculates the column widths to fill out the available width equally
        if self.input_data is None or self.input_data.empty:
            self.width = 0
            self.height = 0
            return self.width, self.height

        num_cols = len(self.input_data.columns)
        col_width = availWidth / num_cols
        self.table._argW = [col_width] * num_cols

        actual_width, self.actual_height = self.table.wrap(availWidth, availHeight)
        self.width = availWidth
        self.height = availHeight
        return self.width, self.height  # Takes the whole available space

    def draw_content(self):
        self.table.drawOn(self.canv, 0, self.height - self.actual_height)  # Placement at the top-left corner


class Hinweise(BaseReportFlowable):
    """
    This class generates the Allgemeine Hinweise section of the certificate.
    """

    def __init__(self, sections_to_include=None) -> None:
        super().__init__()
        self.style = self.get_style()
        self.width = None
        self.height = None
        self.padding = self.style.get_padding()

        # Sections that should be displayed by this Object (None = all)
        self.sections_to_include = sections_to_include

        # This dict contains the text that is displayed in the Hinweise section
        self.hinweise_content = self.translate("content_information_page")

        # Styling configuration
        self.styles = {
            'section_title': ParagraphStyle(
                'SectionTitle',
                fontName=self.style.get_font(bold=True),
                fontSize=self.style.get_font_size('highlighted'),
                alignment=0,  # -> left aligned
                leftIndent=0,  # no indent
                textColor=self.style.get_color('text')
            ),
            'item_definition': ParagraphStyle(
                'ItemDefinition',
                fontName=self.style.get_font(bold=False),
                fontSize=self.style.get_font_size('small'),
                alignment=0,  # -> left aligned
                leftIndent=self.style.get_font_size('small'),  # indent for the items
                firstLineIndent=-self.style.get_font_size('small'),  # hanging indent
                textColor=self.style.get_color('text')
            )
        }
        self.layout = {'distance_after_title': self.styles['section_title'].fontSize * 0.3,
                       # Distance after the section title
                       'distance_after_item': self.styles['item_definition'].fontSize * 0,  # No distance after an item
                       'distance_after_section': self.styles[
                                                     'section_title'].fontSize * 0.5}  # Distance after a section

    def get_filtered_content(self):
        """Returns the filtered hinweise_content based on sections_to_include."""
        if self.sections_to_include is None:
            return self.hinweise_content
        filtered_content = {section: content for section, content in self.hinweise_content.items() if
                            section in self.sections_to_include}
        return filtered_content

    def calculate_section_height(self, section_title, section_data, content_width):
        """Calculates the required height for a section of the hinweise_content. To determine if the remaining space is enough"""
        total_height = 0

        title_paragraph = Paragraph(f"<b>{section_title}:</b>", self.styles['section_title'])
        title_paragraph.wrap(content_width, 1000)
        total_height += title_paragraph.height + self.layout['distance_after_title']

        for item_name, item_description in section_data.items():
            item_text = f"<b>{item_name}:</b> {item_description}"
            item_paragraph = Paragraph(item_text, self.styles['item_definition'])
            item_paragraph.wrap(content_width, 1000)
            total_height += item_paragraph.height + self.layout['distance_after_item']

        total_height += self.layout['distance_after_section']
        return total_height

    def get_sections_that_fit(self, available_height):
        """Ermittelt welche der Sektionen alle auf die nächste Seite passen"""
        content_width = self.width - 2 * self.padding
        content = self.get_filtered_content()

        sections_that_fit = []
        sections_overflow = []
        current_height = self.padding  # Start-Padding

        for section_title, section_data in content.items():
            section_height = self.calculate_section_height(section_title, section_data, content_width)

            if current_height + section_height <= available_height - self.padding:
                sections_that_fit.append(section_title)
                current_height += section_height
            else:
                sections_overflow.append(section_title)

        return sections_that_fit, sections_overflow

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = availHeight
        return self.width, self.height

    def draw_content(self):
        """Only draws the sections that fit on the current page."""
        c = self.canv
        c.saveState()

        content_width = self.width - 2 * self.padding
        margin_left = self.padding

        # y- Start position (from top to bottom)
        y_current = self.height - self.padding

        content = self.get_filtered_content()

        for section_title, section_data in content.items():

            # 1. Sektion-Titel zeichnen
            title_paragraph = Paragraph(f"<b>{section_title}:</b>", self.styles['section_title'])
            title_paragraph.wrap(content_width, y_current)
            title_height = title_paragraph.height

            # Titel zeichnen
            y_current -= title_height  # Title height
            title_paragraph.drawOn(c, margin_left, y_current)
            y_current -= self.layout['distance_after_title']

            # 2. Items zeichnen
            for item_name, item_description in section_data.items():
                # Item-Text erstellen
                item_text = f"<b>{item_name}:</b> {item_description}"
                item_paragraph = Paragraph(item_text, self.styles['item_definition'])
                item_paragraph.wrap(content_width, y_current)
                item_height = item_paragraph.height

                # Move position downward
                y_current -= item_height

                # Draw item
                item_paragraph.drawOn(c, margin_left, y_current)
                y_current -= self.layout['distance_after_item']

            # Distance between sections
            y_current -= self.layout['distance_after_section']

        c.restoreState()

    @classmethod
    def create_all_hinweise(cls, availWidth, availHeight):
        """
        Creates all Hinweise flowables so that the whole content can be displayed.
        The flowables contain all sections that fit on one page.
        The overflow sections are placed in the next box.
        This continues until all sections are placed in a box.
        The list of flowables is then returned.
        """
        dummy_instance = cls()
        remaining_sections = list(dummy_instance.hinweise_content.keys())  # all sections that need to be placed

        hinweise = []

        while remaining_sections:
            # Create test instance with remaining sections
            test_hinweise = cls(sections_to_include=remaining_sections)
            test_hinweise.width = availWidth

            # Determine which sections fit into this box
            sections_that_fit, sections_overflow = test_hinweise.get_sections_that_fit(availHeight)

            # Ensure at least one section is processed
            if not sections_that_fit and remaining_sections:
                raise Exception(
                    "At least one section of the Hinweise content is too large to fit on one page. Please review the content.")

            # Create Hinweise-Flowable for matching sections
            if sections_that_fit:
                hinweise_flowable = cls(sections_to_include=sections_that_fit)
                hinweise.append(hinweise_flowable)

                # Update remaining sections for next iteration
                remaining_sections = sections_overflow

            else:
                # Safety break if no more sections available
                break

        return hinweise


class DistrictLayout(BaseReportFlowable):
    def __init__(self, data_district_layout, availWidth: float, availHeight: float) -> None:
        super().__init__()
        self.style = self.get_style()
        self.data_district_layout = data_district_layout

        self.width = availWidth
        self.height = availHeight

        self.legend_width = self.width * 0.3
        self.legend_height = 0
        self.map_width = self.width - self.legend_width
        self.scale = None

        self.legend_position = "left"
        if self.legend_position == "right":
            self.map_offset_x = 0
            self.legend_offset_x = self.map_width
        else:  # left
            self.legend_offset_x = 0
            self.map_offset_x = self.legend_width

        self.map = self._create_map()
        self.legend = self._create_legend()

    def _create_map(self):

        d = Drawing(self.map_width, self.height)

        # Draw the outer boundary box #! Maybe remove later
        border = Rect(0, 0, self.map_width, self.height)
        border.strokeColor = colors.Color(1, 1,
                                          1)  # 1,1,1 is white (not visible), 0,0,0 would be black. Maybe use a light grey for better visibility of the layout elements? colors.Color(0.8, 0.8, 0.8)
        border.strokeWidth = 1
        border.fillColor = None
        # border.fillColor = colors.Color(247/255, 232/255, 197/255)
        d.add(border)

        nodes = self.data_district_layout.get('network_nodes', {})
        edges = self.data_district_layout.get('network_edges', {})
        buildings = self.data_district_layout.get('buildings', [])
        pipeline_data = self.data_district_layout.get('pipeline_data', {})

        if not buildings:
            font_name = self.style.get_font(bold=False)
            font_size = self.style.get_font_size('subsection_title')
            text_color = colors.Color(*self.style.colors["text"])
            d.add(String(self.map_width / 2.0, self.height / 2.0, self.translate("msg_no_district_layout"),
                         fontName=font_name, fontSize=font_size, fillColor=text_color, textAnchor='middle'))
            return d

        # All positions of nodes and buildings
        all_x = []
        all_y = []
        for n in nodes.values():
            all_x.append(n['pos'][0])
            all_y.append(n['pos'][1])
        for b in buildings:
            all_x.append(b['x'])
            all_y.append(b['y'])

        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        range_x = max_x - min_x
        range_y = max_y - min_y

        distance_to_border = self.style.get_padding() + 2 * self.style.get_layout_size('label')

        avail_w = self.map_width - 2 * distance_to_border
        avail_h = self.height - 2 * distance_to_border

        scale_x = avail_w / range_x if range_x > 0 else float('inf')
        scale_y = avail_h / range_y if range_y > 0 else float('inf')

        self.scale = min(scale_x, scale_y)
        if self.scale == float('inf'):
            self.scale = 1.0

        def transform(x, y):
            """Translate the relative coordinates to the coordinates in the drawing based on the calculated scale and offsets."""
            tx = (self.map_width - (range_x * self.scale)) / 2.0 + (x - min_x) * self.scale
            ty = (self.height - (range_y * self.scale)) / 2.0 + (y - min_y) * self.scale
            return tx, ty

        # Draw elements, order determines which element is on top of which
        network_group = Group()

        self._draw_pipes(network_group, pipeline_data, transform)
        self._draw_buildings(network_group, buildings, transform)
        self._draw_energy_hub(network_group, nodes, transform)

        d.add(network_group)
        return d

    def _draw_pipes(self, group, pipeline_data, transform):
        """Draws the pipes between the nodes"""
        if not pipeline_data:
            return  # If no heat_grid is present, skip drawing pipes

        line_color = colors.Color(*self.style.get_layout_color("pipe"))
        max_pipe_width = self.style.get_layout_size('pipe')
        min_pipe_width = self.style.get_layout_size(
            'pipe') / 10  # Minimum line width for visibility, can be adjusted as needed
        label_size = self.style.get_layout_size('label')
        text_color = colors.Color(*self.style.get_color("text"))

        dn_values = [pipe_info["DN"] for pipe_info in pipeline_data.values()]

        max_dn = max(dn_values)

        for pipe in pipeline_data.values():
            x1, y1 = transform(*pipe["from_pos"])
            x2, y2 = transform(*pipe["to_pos"])

            dn = pipe["DN"]

            if max_dn > 0:
                ratio = dn / float(max_dn)
                lw = max_pipe_width * ratio

                if lw < min_pipe_width:
                    lw = min_pipe_width
            else:
                lw = max_pipe_width

            pipe_line = Line(x1, y1, x2, y2)
            pipe_line.strokeColor = line_color
            pipe_line.strokeWidth = lw
            group.add(pipe_line)

            if self.style.get_layout_options("show_pipe_labels"):
                # Label for the pipe diameter
                if x1 > x2 or (x1 == x2 and y1 > y2):
                    x1, x2, y1, y2 = x2, x1, y2, y1

                mid_x = (x1 + x2) / 2.0
                mid_y = (y1 + y2) / 2.0

                # Placement of the label based on the angle of the pipe
                pipe_angle = math.atan2(y2 - y1, x2 - x1)

                nx = -math.sin(pipe_angle)
                ny = math.cos(pipe_angle)
                offset_dist = (lw / 2.0) + 2

                label_x = mid_x + nx * offset_dist
                label_y = mid_y + ny * offset_dist

                if pipe_angle > math.pi / 6.0:
                    text_anchor = 'end'
                elif pipe_angle < -math.pi / 6.0:
                    text_anchor = 'start'
                else:
                    text_anchor = 'middle'

                dn_label = String(
                    label_x, label_y,
                    f"DN-{dn}",
                    fontName=self.style.get_font(bold=False),
                    fontSize=label_size,
                    fillColor=text_color,
                    textAnchor=text_anchor
                )
                group.add(dn_label)

    def _draw_energy_hub(self, group, nodes, transform):
        """Draws the energy hub"""
        eh_color = colors.Color(*self.style.get_layout_color("eh"))
        for node_id, node_data in nodes.items():
            if node_data.get('role') == 'EH':
                hx, hy = transform(*node_data['pos'])
                r = self.style.get_layout_size('eh')
                h_triangle = math.sqrt(3) * r
                y_top = hy + (h_triangle * (2.0 / 3.0))
                y_bottom = hy - (h_triangle * (1.0 / 3.0))

                eh_shape = Polygon([
                    hx, y_top,
                    hx - r, y_bottom,
                    hx + r, y_bottom
                ])
                eh_shape.fillColor = eh_color
                eh_shape.strokeColor = colors.black
                eh_shape.strokeWidth = 0.5
                group.add(eh_shape)

                if self.style.get_layout_options("show_building_labels"):
                    label = String(hx, hy + r + 4, node_id, fontName=self.style.get_font(bold=True),
                                   fontSize=self.style.get_layout_size('label') * 1.5, fillColor=eh_color,
                                   textAnchor='middle')
                    group.add(label)

    def _draw_buildings(self, group, buildings, transform):
        """Draws the buildings"""
        connected_color = colors.Color(*self.style.get_layout_color("building_connected"))
        disconnected_color = colors.Color(*self.style.get_layout_color("building_not_connected"))
        text_color = colors.Color(*self.style.colors["text"])

        for b in buildings:
            bx, by = transform(b['x'], b['y'])
            b_color = connected_color if b.get('is_connected', False) else disconnected_color

            radius = self.style.get_layout_size('building')
            b_circle = Circle(bx, by, r=radius)
            b_circle.fillColor = b_color
            b_circle.strokeColor = colors.black
            b_circle.strokeWidth = 0.5
            group.add(b_circle)

            if self.style.get_layout_options("show_building_labels"):
                type_text = f"{b['type']}"
                type_label = String(bx, by - radius - self.style.get_layout_size('label'), type_text,
                                    fontName=self.style.get_font(bold=True),
                                    fontSize=self.style.get_layout_size('label'), fillColor=text_color,
                                    textAnchor='middle')
                group.add(type_label)

                id_text = f"({b['id']})"
                id_label = String(bx, by - radius - 2 * self.style.get_layout_size('label'), id_text,
                                  fontName=self.style.get_font(bold=False),
                                  fontSize=self.style.get_layout_size('label'), fillColor=text_color,
                                  textAnchor='middle')
                group.add(id_label)

    def _create_legend(self):
        d = Drawing(self.legend_width, self.height)

        padding = self.style.get_padding()
        size_elements = 10

        # X- Starting points (from left to right)
        start_x = padding
        sym_x = start_x + size_elements  # Center of the symbols
        text_x = sym_x + size_elements + self.style.get_spacing(
            'medium')  # Start of the text, after symbol and some spacing

        text_color = colors.Color(*self.style.get_color("text"))
        legend_font_size = self.style.get_layout_size("legend_text")
        y_text_offset = legend_font_size / 3.0

        distance_entries = self.style.get_spacing('medium')

        # Y- Starting point (from top to bottom)
        current_y = self.height - padding

        # Scale:
        if self.scale is not None:
            max_scale_width = self.legend_width - 2 * padding

            allowed_real_meters = []
            for power in range(0, 4):
                allowed_real_meters.extend([1 * 10 ** power, 2.5 * 10 ** power, 5 * 10 ** power])

            # Find the best fitting scale value that is the closest to but smaller than the maximum width
            best_real_meters = 10
            for val in reversed(allowed_real_meters):
                if val * self.scale <= max_scale_width:
                    best_real_meters = val
                    break

            drawn_length = best_real_meters * self.scale

            scale_y = current_y - size_elements
            scale_start_x = start_x

            bar_height = 5  # Height of the scale bar
            num_segments = 4  # Number of blocks in the scale (e.g., 4 blocks for 0, 25%, 50%, 75%, 100%)
            seg_length = drawn_length / num_segments

            # Draw the scale segments
            for i in range(num_segments):
                seg_x = scale_start_x + i * seg_length
                is_black = (i % 2 == 0)

                seg_rect = Rect(seg_x, scale_y, seg_length, bar_height)
                seg_rect.strokeColor = colors.black
                seg_rect.strokeWidth = 0.5
                seg_rect.fillColor = colors.black if is_black else colors.white
                d.add(seg_rect)

            # Placement of the labels for the scale
            label_y = scale_y + bar_height + 2
            label_size = self.style.get_layout_size("label")

            # "0" at the beginning of the scale
            d.add(String(scale_start_x, label_y, "0",
                         fontName=self.style.get_font(bold=False), fontSize=label_size,
                         fillColor=text_color, textAnchor='middle'))

            # Halfway value in the middle
            half_meters = best_real_meters / 2.0
            d.add(String(scale_start_x + drawn_length / 2.0, label_y, f"{half_meters:g}",
                         fontName=self.style.get_font(bold=False), fontSize=label_size,
                         fillColor=text_color, textAnchor='middle'))

            # End value with unit ("m") at the end
            d.add(String(scale_start_x + drawn_length, label_y, f"{best_real_meters:g} m",
                         fontName=self.style.get_font(bold=False), fontSize=label_size,
                         fillColor=text_color, textAnchor='middle'))

            # Start of the legend, below the scale
            box_start_y = scale_y - padding

        else:
            box_start_y = current_y

        current_y = box_start_y - padding

        # Legend Title
        # font_size_title = self.style.get_font_size("subsection_title")
        # current_y -= font_size_title
        # d.add(String(start_x, current_y, "Legende", fontName=self.style.get_font(bold=True), fontSize=font_size_title, fillColor=text_color))
        # current_y -= distance_entries

        # Energy Hub
        current_y -= size_elements  # Move to center of the symbol
        eh_color = colors.Color(*self.style.get_layout_color("eh"))
        h_triangle = math.sqrt(3) * size_elements

        y_top = current_y + (h_triangle * (2.0 / 3.0))
        y_bottom = current_y - (h_triangle * (1.0 / 3.0))

        eh_shape = Polygon([
            sym_x, y_top,  # Top
            sym_x - size_elements, y_bottom,  # Bottom left
            sym_x + size_elements, y_bottom  # Bottom right
        ])
        eh_shape.fillColor = eh_color
        eh_shape.strokeColor = colors.black
        eh_shape.strokeWidth = 0.5
        d.add(eh_shape)

        d.add(String(text_x, current_y - y_text_offset, self.translate("legend_eh"),
                     fontName=self.style.get_font(bold=False),
                     fontSize=legend_font_size,
                     fillColor=text_color,
                     textAnchor='start'))

        current_y -= size_elements + distance_entries

        # Pipes
        current_y -= size_elements / 2.0
        pipe_color = colors.Color(*self.style.get_layout_color("pipe"))
        pipe_width = 2 * size_elements / 10

        if self.style.get_layout_options("show_pipe_labels"):
            y_text_line1 = current_y
            y_text_line2 = current_y - legend_font_size * 1.2
            y_center_of_texts = (y_text_line1 + y_text_line2) / 2.0

            # Draw line centered between the two text lines
            pipe_line = Line(sym_x - size_elements, y_center_of_texts, sym_x + size_elements, y_center_of_texts)
            pipe_line.strokeColor = pipe_color
            pipe_line.strokeWidth = pipe_width
            d.add(pipe_line)

            # Draw DN-X label above the line
            d.add(String(sym_x, y_center_of_texts + pipe_width / 2 + 2, "DN-X",
                         fontName=self.style.get_font(bold=False),
                         fontSize=legend_font_size * 0.8,
                         fillColor=text_color, textAnchor='middle'))

            # Draw main text
            d.add(String(text_x, y_text_line1, self.translate("legend_pipes"),
                         fontName=self.style.get_font(bold=False),
                         fontSize=legend_font_size,
                         fillColor=text_color,
                         textAnchor='start'))

            # Draw explanation text
            explanation_color = colors.Color(*self.style.get_color("text_light"))
            d.add(String(text_x, y_text_line2, self.translate("legend_pipe_dn"),
                         fontName=self.style.get_font(bold=False),
                         fontSize=legend_font_size * 0.85,
                         fillColor=explanation_color,
                         textAnchor='start'))

            current_y = y_text_line2 - distance_entries

        else:
            # Draw simple line without labels
            pipe_line = Line(sym_x - size_elements, current_y, sym_x + size_elements, current_y)
            pipe_line.strokeColor = pipe_color
            pipe_line.strokeWidth = pipe_width
            d.add(pipe_line)

            # Draw single main text
            d.add(String(text_x, current_y - y_text_offset, self.translate("legend_pipes"),
                         fontName=self.style.get_font(bold=False),
                         fontSize=legend_font_size,
                         fillColor=text_color,
                         textAnchor='start'))

            current_y -= size_elements + distance_entries

        # Buildings connected to the heat grid
        current_y -= size_elements  # Move to center of the symbol
        conn_color = colors.Color(*self.style.get_layout_color("building_connected"))
        b_conn = Circle(sym_x, current_y, r=size_elements)
        b_conn.fillColor = conn_color
        b_conn.strokeColor = colors.black
        b_conn.strokeWidth = 0.5
        d.add(b_conn)

        d.add(String(text_x, current_y - y_text_offset, self.translate("legend_bldg_conn"),
                     fontName=self.style.get_font(bold=False),
                     fontSize=legend_font_size,
                     fillColor=text_color,
                     textAnchor='start'))

        current_y -= size_elements + distance_entries

        # Buildings not connected to the heat grid
        current_y -= size_elements  # Move to center of the symbol
        not_conn_color = colors.Color(*self.style.get_layout_color("building_not_connected"))
        b_not_conn = Circle(sym_x, current_y, r=size_elements)
        b_not_conn.fillColor = not_conn_color
        b_not_conn.strokeColor = colors.black
        b_not_conn.strokeWidth = 0.5
        d.add(b_not_conn)

        d.add(String(text_x, current_y - y_text_offset, self.translate("legend_bldg_not_conn"),
                     fontName=self.style.get_font(bold=False),
                     fontSize=legend_font_size,
                     fillColor=text_color,
                     textAnchor='start'))

        current_y -= size_elements

        # Box around the legend entries
        current_y -= padding
        box_height = box_start_y - current_y
        legend_box = Rect(0, current_y, self.legend_width, box_height)
        legend_box.strokeColor = colors.Color(0.2, 0.2, 0.2)
        legend_box.strokeWidth = 1
        legend_box.fillColor = None

        d.add(legend_box)

        self.legend_height = self.height - current_y

        return d

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw_content(self):
        self.map.drawOn(self.canv, self.map_offset_x, 0)
        self.legend.drawOn(self.canv, self.legend_offset_x, self.legend_height - self.height)


################################################################################
# Layout generation as classes
################################################################################

class CertificateLayout(ReportComponent):
    """
    This class generates the layout for the certificate. Where which flowable is placed.
    """

    def __init__(self, certificate_builder) -> None:
        self.style = self.get_style()
        self.story = []
        self.certificate_builder = certificate_builder
        self.paragraph_styles = self.style.get_paragraph_styles()

    # Titlepage methods
    def create_header(self):
        """Creates Header and adds it to the story."""
        title = self.translate("ui_certificate_title")
        header = Header(title=title)
        self.story.append(header)
        self.add_standard_spacer('large')

    def create_energiekennwerte(self, data_energiekennwerte):
        """Creates the Energiekennwerte section and adds it to the story."""
        title = self.translate("title_kpis")
        box = FrameBox(title=title)
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='TitleContentFrame')
        avail_w, avail_h = FrameBox.get_available_space_content(frame_width, frame_height)

        energiekennwerte = Energiekennwerte(kpi_data=data_energiekennwerte, availWidth=avail_w)
        box.set_content(energiekennwerte)
        self.story.append(box)
        self.add_standard_spacer()

    def create_quartiersstruktur(self, data_quartiersstruktur):
        """Creates the Quartiersstruktur section and adds it to the story."""
        title = self.translate("title_district_structure")
        box = FrameBox(title=title)

        quartiersstruktur_flowable = Quartiersstruktur(
            summary_table_data=data_quartiersstruktur["summary_table"],
            general_info=data_quartiersstruktur["general_info"]
        )

        box.set_content(quartiersstruktur_flowable, full_width=False)
        self.story.append(box)
        self.add_standard_spacer()

    def create_footer(self, scenario_name):
        """Creates Footer and adds it to the story."""
        footer = Footer(scenario_name)
        self.story.append(footer)

    # Energyhub device capacity page
    def create_energyhub_data(self, data_energyhub):
        """Creates the Energyhub Data section and adds it to the story."""

        # 1. Get the available space from the template frame
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='EnergyhubDevicesFrame')
        eh_width, eh_height = FrameBox.get_available_space_content(frame_width, frame_height)

        # 2. Let the EnergyHub factory create all necessary, perfectly sized boxes
        boxes = EnergyHub.create_boxes(
            data_energyhub=data_energyhub,
            availWidth=eh_width,
            availHeight=eh_height
        )

        # 3. Add them to the document story
        self.story.extend(boxes)

    def create_decentral_systems(self, data_decentral):
        """Creates the Decentral Systems section and adds it to the story."""

        # 1. Get the available space from the template frame
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='EnergyhubDevicesFrame')

        # Calculate how much height is ALREADY consumed by the EnergyHub boxes currently in the story
        used_height = 0
        for item in self.story:
            # Give it a wide dummy width just to ask the Flowables for their height
            _, h = item.wrap(frame_width, frame_height)
            used_height += h

        # Available height is the total frame height minus what we've already used
        remaining_height = max(0, frame_height - used_height)

        # Get content dimensions
        dec_width, dec_height = FrameBox.get_available_space_content(frame_width, remaining_height)

        # 2. Let the DecentralSystems factory create all necessary boxes
        boxes = DecentralSystems.create_boxes(
            data_decentral=data_decentral,
            availWidth=dec_width,
            availHeight=dec_height
        )

        # Add spacing before the new section if there are boxes
        if boxes:
            self.add_standard_spacer()

        # 3. Add them to the document story
        self.story.extend(boxes)

    def create_energyhub_profiles(self, data_profiles, kpi_data, cluster_info):
        """Creates the Energyhub Profiles section and adds it to the story."""
        if not data_profiles:
            return

        title = self.translate("Energy Hub Profiles")
        max_clusters_per_box = 4

        sorted_years = sorted(data_profiles.keys())

        for index, year in enumerate(sorted_years):
            if index > 0:
                self.story.append(PageBreak())

            if index < len(sorted_years) - 1:
                # The end is the year before the next profile's year, to avoid overlap in the x-axis of the bar charts
                end_year = sorted_years[index + 1] - 1
            else:
                # The last time window uses the observation_time as the upper limit
                end_year = kpi_data["observation_time"] - 1

            year_title = f"{title} {year}-{end_year} (kW)"
            cluster_names = list(sorted(data_profiles[year].keys(), key=lambda value: str(value)))
            cluster_chunks = [
                cluster_names[i:i + max_clusters_per_box]
                for i in range(0, len(cluster_names), max_clusters_per_box)
            ]

            for chunk_index, cluster_chunk in enumerate(cluster_chunks):
                if chunk_index > 0:
                    self.story.append(PageBreak())

                chunk_profiles = {
                    cluster_name: data_profiles[year][cluster_name]
                    for cluster_name in cluster_chunk
                }
                chunk_title = year_title
                if len(cluster_chunks) > 1:
                    chunk_title = f"{year_title} ({chunk_index + 1}/{len(cluster_chunks)})"

                year_flowable = EnergyHubProfilesYear(year_profiles=chunk_profiles, cluster_info=cluster_info)
                box = FrameBox(title=chunk_title)
                box.set_content(year_flowable, full_width=False)
                self.story.append(box)

    def create_quartiersstruktur_details(self, data_quartiersstruktur):
        """Creates the detailed matrix on a landscape page."""
        df_details = data_quartiersstruktur["df_details"]

        if df_details.empty:
            return

        frame_width, frame_height = self.certificate_builder.get_Framesize(id='InputDataFrame')
        avail_w, avail_h = FrameBox.get_available_space_content(frame_width, frame_height)

        # Use universal pagination logic
        tables = PaginatedDataFrameTable.create_all_tables(
            availWidth=avail_w,
            availHeight=avail_h,
            input_data=df_details,
            style_name='input_data'
        )

        title = self.translate("title_district_structure_detailed")
        for i, tab in enumerate(tables, start=1):
            title = title if len(tables) == 1 else f"{title} ({i}/{len(tables)})"
            box = FrameBox(title=title)
            box.set_content(tab, full_width=True)
            self.story.append(box)

    def create_district_layout(self, data_district_layout):
        """Plots the district layout"""
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='InputDataFrame')
        map_width, map_height = FrameBox.get_available_space_content(frame_width, frame_height)

        district_map = DistrictLayout(
            data_district_layout=data_district_layout,
            availWidth=map_width,
            availHeight=map_height
        )

        name = self.translate("title_district_layout")
        box = FrameBox(title=name)
        box.set_content(district_map)
        self.story.append(box)

    # Input Data page
    def create_input_data_table(self, data_input):
        """Creates the Input Data Table section and adds it to the story."""
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='InputDataFrame')
        input_data_width, input_data_height = FrameBox.get_available_space_content(frame_width, frame_height)

        input_data_tables = PaginatedDataFrameTable.create_all_tables(
            availWidth=input_data_width,
            availHeight=input_data_height,
            input_data=data_input,
            style_name='input_data'
        )

        title = self.translate("title_bldg_list")
        for i, input_data_table in enumerate(input_data_tables, start=1):
            name = f"{title} ({i}/{len(input_data_tables)})" if len(input_data_tables) > 1 else title
            box = FrameBox(title=name)
            box.set_content(input_data_table)
            self.story.append(box)

    # Additional Information page
    def create_hinweise(self):
        """
        Creates the Hinweise section and adds it to the story.
        Uses the Hinweise class method to create all Hinweise boxes
        These are then all placed in a FrameBox
        and these are added to the story as seperate pages.
        """
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='AdditionalInformationFrame')
        hinweise_width, hinweise_height = FrameBox.get_available_space_content(frame_width, frame_height)

        hinweise = Hinweise.create_all_hinweise(availWidth=hinweise_width, availHeight=hinweise_height)
        pages_hinweise = len(hinweise)

        title = self.translate("title_information")
        for i, hinweis in enumerate(hinweise, start=1):
            name = f"{title} ({i}/{pages_hinweise})" if pages_hinweise > 1 else title
            box = FrameBox(title=name)
            box.set_content(hinweis)
            self.story.append(box)

    def create_yearly_bar_charts(self, kpi_data):
        """Creates the yearly stacked bar charts and adds them to the story."""
        costs_data = kpi_data.get("bar_costs_data", [])
        co2_data = kpi_data.get("bar_co2_data", [])
        obs_time = kpi_data.get("observation_time", None)

        if not costs_data or not co2_data:
            return

        title = self.translate("title_cost_emissions")
        box = FrameBox(title=title)
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='EnergyhubDevicesFrame')
        avail_w, avail_h = FrameBox.get_available_space_content(frame_width, frame_height)

        barcharts_flowable = YearlyStackedBarCharts(costs_data=costs_data, co2_data=co2_data, availWidth=avail_w,
                                                    availHeight=avail_h, observation_time=obs_time)
        box.set_content(barcharts_flowable)
        self.story.append(box)

    def add_standard_spacer(self, size: str = 'medium'):
        """Adds a standard spacer to the story."""
        spacing = self.style.get_spacing(size)
        spacer = Spacer(1, spacing)
        self.story.append(spacer)

    def get_story(self):
        """Returns the story for the certificate."""
        return self.story

    def reset_story(self):
        """Resets the story."""
        self.story = []


class CertificateTemplate(BaseDocTemplate, ReportComponent):
    """
    This class handles the pure PDF document structure, frames, and page templates.
    """

    def __init__(self, filename, page_margins, **kwargs):
        self.style = self.get_style()
        self.pagesize = self.style.get_pagesize()

        # Initialize BaseDocTemplate with 0 margins (margins handled in frames)
        super().__init__(filename, pagesize=self.pagesize, leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
                         **kwargs)

        self.page_margins = page_margins

        self.setup_templates()

    def setup_templates(self):
        """
        Sets up the page templates and defines the frames for the different sections of the certificate.
        """
        width, height = self.pagesize
        landscape_pagesize = landscape(self.pagesize)

        #  Title Page
        page_id = 'TitlePage'
        margins = self.page_margins
        margin_x, margin_y = self.page_margins[page_id]

        footer_height = Footer.get_required_height()
        footer_spacing = self.style.get_spacing('medium')

        title_content_frame = Frame(
            margin_x,
            margin_y + footer_height,  # Startet ÜBER dem Footer
            width - 2 * margin_x,
            height - 2 * margin_y - footer_height - footer_spacing,  # Reduzierte Höhe
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id='TitleContentFrame'
        )

        title_footer_frame = Frame(
            margin_x,
            margin_y,  # Footer ganz unten
            width - 2 * margin_x,
            footer_height,  # DYNAMISCHE Footer-Höhe
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id='TitleFooterFrame'
        )

        title_template = PageTemplate(
            id=page_id,
            frames=[title_content_frame, title_footer_frame],
            onPage=self.draw_title_page,
            pagesize=self.pagesize
        )

        # Energyhub Devices Page
        page_id = 'ContentPage'
        margin_x, margin_y = self.page_margins[page_id]

        energyhub_frame = Frame(
            margin_x, margin_y,
            width - 2 * margin_x, height - 2 * margin_y,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id='EnergyhubDevicesFrame'
        )
        energyhub_template = PageTemplate(id=page_id, frames=[energyhub_frame], onPage=self.draw_energyhub_devices_page,
                                          pagesize=self.pagesize)

        # Input Data Page (Landscape)
        page_id = 'InputDataPage'
        margin_x, margin_y = self.page_margins[page_id]

        input_data_frame = Frame(
            margin_x, margin_y,
            landscape_pagesize[0] - 2 * margin_x, landscape_pagesize[1] - 2 * margin_y,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id='InputDataFrame'
        )
        input_data_template = PageTemplate(id=page_id, frames=[input_data_frame], onPage=self.draw_input_data_page,
                                           pagesize=landscape_pagesize)

        # Additional Information Page
        page_id = 'AdditionalInformationPage'
        margin_x, margin_y = self.page_margins[page_id]

        additional_info_frame = Frame(
            margin_x, margin_y,
            width - 2 * margin_x, height - 2 * margin_y,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id='AdditionalInformationFrame'
        )
        additional_info_template = PageTemplate(id=page_id, frames=[additional_info_frame],
                                                onPage=self.draw_additional_information_page, pagesize=self.pagesize)

        self.addPageTemplates([title_template, energyhub_template, input_data_template, additional_info_template])

    # --- Functions to draw the different page templates adding page numbers, adding logos etc. ---
    def draw_title_page(self, canvas, doc):
        """Draws the title page elements."""
        canvas.saveState()
        canvas.restoreState()

    def draw_energyhub_devices_page(self, canvas, doc):
        """Draws the energyhub devices page elements."""
        canvas.saveState()
        self.add_page_number(canvas, doc)
        canvas.restoreState()

    def draw_input_data_page(self, canvas, doc):
        """Draws the input data page elements."""
        canvas.saveState()
        self.add_page_number(canvas, doc)
        canvas.restoreState()

    def draw_additional_information_page(self, canvas, doc):
        """Draws the additional information page elements."""
        canvas.saveState()
        self.add_page_number(canvas, doc)
        canvas.restoreState()

    def add_page_number(self, canvas, doc):
        """Adds page number to the canvas."""
        canvas.saveState()
        width, height = canvas._pagesize
        page_id = doc.pageTemplate.id

        margin_x, margin_y = self.page_margins[page_id]

        canvas.setFont(self.style.get_font(bold=False), self.style.get_font_size('page_number'))
        canvas.setFillColorRGB(*self.style.get_color('text_light'))

        canvas.drawRightString(width - margin_x, margin_y - 20, f"{self.translate('ui_page')} {doc.page}")
        canvas.restoreState()

    def get_Framesize(self, id: str):
        """Returns the size of the frame with the given id."""
        for template in self.pageTemplates:
            for frame in template.frames:
                if frame.id == id:
                    return frame._width, frame._height
        raise ValueError(f"No frame with id {id} found.")


class PaginatedDataFrameTable(BaseReportFlowable):
    """
    Generic class to generate and paginate tables from pandas DataFrames.
    """

    def __init__(self, input_data: pd.DataFrame, style_name: str) -> None:
        super().__init__()
        self.style = self.get_style()
        self.style_name = style_name
        self.table_style = self.style.get_table_styles()[self.style_name]

        self.width = None
        self.height = None
        self.actual_height = None

        if input_data is None or input_data.empty:
            self.input_data = pd.DataFrame()
            table_data = []
        else:
            self.input_data = input_data.copy()
            self.input_data = self.input_data.fillna("-").astype(str)

            header = self.input_data.columns.tolist()
            table_data = self._format_table_data(self.input_data, header)

        self.table = Table(table_data)

        # Apply the pre-configured TableStyle
        self.table.setStyle(self.table_style)

    def _format_table_data(self, df, header):
        """
        Converts all cells to Paragraphs to ensure uniform vertical alignment and subscript rendering.
        Dynamically extracts FONTNAME, FONTSIZE, ALIGN, and TEXTCOLOR directly from the TableStyle
        for each specific cell coordinate to make this class 100% style-agnostic.
        """
        num_cols = len(header)
        num_rows = len(df) + 1  # 1 for header row

        # Helper function to check if a cell (c, r) falls within a ReportLab TableStyle command coordinate range
        def in_range(c, r, start_coord, end_coord):
            sc, sr = start_coord
            ec, er = end_coord
            # Translate negative coordinates
            if sc < 0: sc += num_cols
            if ec < 0: ec += num_cols
            if sr < 0: sr += num_rows
            if er < 0: er += num_rows

            return (sc <= c <= ec) and (sr <= r <= er)

        base_style = self.style.get_paragraph_styles()['Normal']
        memoized_styles = {}  # Cache to avoid creating thousands of duplicate ParagraphStyle objects

        def get_cell_paragraph_style(c, r):
            necessary_attrs = {'f_name': 'FONTNAME', 'f_size': 'FONTSIZE', 'align': 'ALIGN', 't_color': 'TEXTCOLOR'}
            for var_name in necessary_attrs.keys():
                if var_name in locals():
                    del locals()[var_name]

                    # Extract specific styles for this exact cell from the TableStyle commands
            for cmd in self.table_style.getCommands():
                op = cmd[0]
                start_coord = cmd[1]
                end_coord = cmd[2]

                if in_range(c, r, start_coord, end_coord):
                    if op == 'FONTNAME':
                        f_name = cmd[3]
                    elif op == 'FONTSIZE':
                        f_size = cmd[3]
                    elif op == 'ALIGN':
                        val = cmd[3].upper()
                        if val == 'LEFT':
                            align = 0
                        elif val == 'CENTER':
                            align = 1
                        elif val == 'RIGHT':
                            align = 2
                    elif op == 'TEXTCOLOR':
                        t_color = cmd[3]

            # Check if any of the style attributes were not set by the TableStyle commands and raise exceptions if so as Style is not fully defined:
            for var_name, attr_name in necessary_attrs.items():
                if var_name not in locals():
                    raise ValueError(
                        f"TableStyle is missing necessary '{attr_name}' command for cell ({c}, {r}). All of FONTNAME, FONTSIZE, ALIGN, and TEXTCOLOR must be defined for every cell to ensure consistent styling. Please check the TableStyle configuration.")

            # Create or reuse a corrosponding ParagraphStyle for this unique combination
            style_key = (f_name, f_size, align, t_color)
            if style_key not in memoized_styles:
                memoized_styles[style_key] = ParagraphStyle(
                    f'DynamicStyle_{id(style_key)}',
                    parent=base_style,
                    fontName=f_name,
                    fontSize=f_size,
                    alignment=align,
                    textColor=t_color,
                    leading=f_size * 1.2,
                    leftIndent=0,
                    rightIndent=0,
                    spaceBefore=0,  # Padding defined by the TableStyle not here
                    spaceAfter=0,
                    splitLongWords=0  # prevent forced hyphenation
                )
            return memoized_styles[style_key]

        def prep(text, current_f_size):
            t = str(text)
            # Replace XML special characters
            t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            sub_size = round(current_f_size * 0.70, 1)
            sub_rise = round(current_f_size * 0.20, 1)
            super_rise = round(current_f_size * 0.40, 1)

            # Restore <sub> tags and specify size and rise for subscripts based on the current font size of the cell
            custom_sub = f'<sub size="{sub_size}" rise="{sub_rise}">'
            t = t.replace('&lt;sub&gt;', custom_sub).replace('&lt;/sub&gt;', '</sub>')

            # Restore <super> tags and specify size and rise for superscripts based on the current font size of the cell use sub_size and sub_rise
            custom_super = f'<super size="{sub_size}" rise="{super_rise}">'
            t = t.replace('&lt;super&gt;', custom_super).replace('&lt;/super&gt;', '</super>')

            return f"<nobr>{t}</nobr>"

        # Build Header
        formatted_header = []
        for c, col in enumerate(header):
            style = get_cell_paragraph_style(c, 0)
            formatted_header.append(Paragraph(prep(col, style.fontSize), style))

        # Build Body
        formatted_body = []
        for r, row in enumerate(df.values.tolist(), start=1):
            formatted_row = []
            for c, cell in enumerate(row):
                style = get_cell_paragraph_style(c, r)
                formatted_row.append(Paragraph(prep(cell, style.fontSize), style))
            formatted_body.append(formatted_row)

        return [formatted_header] + formatted_body

    def get_rows_that_fit(self, availWidth, availHeight):
        """
        Determines which rows of the data fit into the available height.
        Returns a tuple of two DataFrames: (fitting_rows, overspill_rows).
        """
        if self.input_data is None or self.input_data.empty:
            return pd.DataFrame(), pd.DataFrame()

        header = self.input_data.columns.tolist()
        num_cols = len(header)
        colWidths = [availWidth / num_cols] * num_cols

        num_data_rows_fit = len(self.input_data)

        # Iteratively reduce estimated number of rows until it fits
        while num_data_rows_fit > 0:
            fitting_rows_df = self.input_data.iloc[:num_data_rows_fit]

            table_data = self._format_table_data(fitting_rows_df, header)
            tmp_table = Table(table_data, colWidths=colWidths)
            tmp_table.setStyle(self.table_style)

            _, wrapped_height = tmp_table.wrap(availWidth, availHeight)

            if wrapped_height <= availHeight:
                break
            num_data_rows_fit -= 1

        fitting_rows = self.input_data.iloc[:num_data_rows_fit]
        overspill_rows = self.input_data.iloc[num_data_rows_fit:]

        return fitting_rows, overspill_rows

    def wrap(self, availWidth, availHeight):
        if self.input_data is None or self.input_data.empty:
            self.width = 0
            self.height = 0
            return self.width, self.height

        num_cols = len(self.input_data.columns)
        col_width = availWidth / num_cols
        self.table._argW = [col_width] * num_cols

        actual_width, self.actual_height = self.table.wrap(availWidth, availHeight)
        self.width = availWidth
        self.height = availHeight
        return self.width, self.height

    def draw_content(self):
        # Placement at the top-left corner
        self.table.drawOn(self.canv, 0, self.height - self.actual_height)

    @classmethod
    def create_all_tables(cls, availWidth, availHeight, input_data: pd.DataFrame, style_name: str):
        """
        Creates all tables so that the whole content can be displayed.
        """
        if input_data is None or input_data.empty:
            return []

        flowables = []
        remaining_data = input_data.copy()

        while not remaining_data.empty:
            test_input_data = cls(input_data=remaining_data, style_name=style_name)
            test_input_data.width = availWidth

            fitting_rows, overspill_rows = test_input_data.get_rows_that_fit(availWidth=availWidth,
                                                                             availHeight=availHeight)

            if fitting_rows.empty and not overspill_rows.empty:
                raise Exception(
                    f"A single row does not fit into the available height. Decrease the needed height. Current available height: {str(availHeight)} and current available width: {str(availWidth)}")
            elif not fitting_rows.empty:
                table_flowable = cls(input_data=fitting_rows, style_name=style_name)
                flowables.append(table_flowable)

                remaining_data = overspill_rows
            else:
                break

        return flowables


################################################################################
# Data Infrastructure for the certificate as a class to extract  and prepare relevant data for the certificate
################################################################################

class DataExtractor(ReportComponent):
    """
    This class extracts the data from the input data structure and prepares it for the certificate.
    """

    def __init__(self, data, kpis) -> None:
        """
        Args:
            data: Input data structure (Datahandler-Object from dataHandler.py)
            kpis: Key performance indicators (KPI-Object from KPIs.py)
        """
        self.data = data
        self.kpis = kpis
        self.building_stats = {}
        self.gebaude_df = None  # -> Replaced by a pd.DataFrame later
        self.kennwerte = None
        self.optimization_results = None
        self.district_structure = None
        self.energyhub_df = None
        self.cluster_info = None
        self.decentral_df = None
        self.energyhub_profiles = {}
        self.district_layout = None

        # Building features to be included in the gebaude_df and the keys to extract the data from buildingFeatures
        self.mapping_building_list = OrderedDict(
            [  # key: display name value: data key to extract value from buildingFeatures
                (self.translate("name_building_type"), "building"),
                (self.translate("name_building_year"), "year"),
                (self.translate("name_building_retrofit"), "retrofit"),
                (self.translate("name_sp_mass"), "construction_type"),
                (self.translate("name_night_setback"), "night_setback"),
                (self.translate("name_building_area"), "area"),
                (self.translate("name_heating_tech"), "heater"),
                (self.translate("name_ev_share"), "EV"),
                (self.translate("name_f_tes"), "f_TES"),
                (self.translate("name_f_bat"), "f_BAT"),
                (self.translate("name_f_pv1"), "f_PV1"),
                (self.translate("name_f_pv2"), "f_PV2"),
                (self.translate("name_f_stc"), "f_STC"),
                (self.translate("name_gamma_pv"), "gamma_PV"),
                (self.translate("name_ev_charging"), "ev_charging")
            ])

        self._extract_data()

    def _get_year_category(self, year: int) -> str:
        """
        Returns the building year category as a string based on the given year.
        Args:
            year: Building year as an integer
        Returns:
            Building year category as a string
        """
        if year < 1968: return self.translate("name_age_cat_before_1968")
        if 1968 <= year <= 1978: return self.translate("name_age_cat_1968_1978")
        if 1979 <= year <= 1983: return self.translate("name_age_cat_1979_1983")
        if 1984 <= year <= 1994: return self.translate("name_age_cat_1984_1994")
        if 1995 <= year <= 2001: return self.translate("name_age_cat_1995_2001")
        if 2002 <= year <= 2009: return self.translate("name_age_cat_2002_2009")
        if 2010 <= year <= 2015: return self.translate("name_age_cat_2010_2015")
        return self.translate("name_age_cat_after_2016")

    def _process_buildings(self):
        """
        Processes the building data and populates the building_stats and list_of_buildings attributes.
        """
        template_dict = OrderedDict([
            (self.translate("name_number_bldgs"), 0), (self.translate("name_total_area"), 0),
            (self.translate("name_age_cat_before_1968"), 0),
            (self.translate("name_age_cat_1968_1978"), 0), (self.translate("name_age_cat_1979_1983"), 0),
            (self.translate("name_age_cat_1984_1994"), 0),
            (self.translate("name_age_cat_1995_2001"), 0), (self.translate("name_age_cat_2002_2009"), 0),
            (self.translate("name_age_cat_2010_2015"), 0),
            (self.translate("name_age_cat_after_2016"), 0)
        ])

        building_types = ['SFH', 'TH', 'MFH', 'AB', 'OB', 'SC', 'GS', 'RE', "UNI", "HOSPITAL", "CULTURE", "SPORT",
                          "RETAIL", "WORKSHOP", "MIXED"]

        self.building_stats = {b_type: template_dict.copy() for b_type in building_types}
        building_data_list = []
        for idx, building in enumerate(self.data.district):
            features = building["buildingFeatures"]
            b_type = features["building"]
            stat_type = "MIXED" if "+" in b_type else b_type

            if stat_type in self.building_stats:
                # Update building statistics by this building
                self.building_stats[stat_type][self.translate("name_number_bldgs")] += 1
                self.building_stats[stat_type][self.translate("name_total_area")] += features["area"]
                year_category = self._get_year_category(features["year"])
                self.building_stats[stat_type][year_category] += features["area"]

            building_dict = {}
            building_dict[self.translate("name_building_id")] = features["id"]

            # Add to the dictionary from the mapping
            building_dict.update({
                display_name: features.get(data_key)
                for display_name, data_key in self.mapping_building_list.items()
            })

            # manual adjustments:
            if features.get("heater") == "heat_grid":
                building_dict[
                    "fTES"] = 0  # if building is connected to heat grid, no local TES even if otherwise specified

            # Add dictionary to the list
            building_data_list.append(building_dict)

        self.gebaude_df = pd.DataFrame(building_data_list)

        # TODO: Maybe add here dtype casting e.g. ensure area is integer not float ....

    def _extract_kennwerte(self):
        """Extracts the general key performance indicators."""
        years = self.kpis.inputData["simulated_years"]
        obs_time = self.data.ecoData["observation_time"]
        to_kW = 1000  # Convert W to kW for power values
        to_MWh = 1000000  # Convert W to MWh for energy values

        # Prepare Data -> # TODO: Move to KPIs class
        avg_autonomy = sum(self.kpis.energy_autonomy_year[y] for y in years) / len(years)
        avg_scf = sum(self.kpis.scf_year[y] for y in years) / len(years)
        avg_dcf = sum(self.kpis.dcf_year[y] for y in years) / len(years)

        # Overall_summary
        self.district_key_kpis = [
            [self.translate("kpi_net_energy_demand"),
             f"{round((self.kpis.total_heating_demand + self.kpis.total_cooling_demand + self.kpis.total_electricity_demand + self.kpis.total_dhw_demand + self.kpis.total_EV_demand) / to_MWh, 1)} MWh/a"],
            [self.translate("kpi_standard_heat_load"), f"{round(self.kpis.totalheatload / to_kW, 1)} kW"],
            [self.translate("kpi_project_time"), f"{obs_time} {self.translate('name_years')}"]
        ]

        self.district_operation_kpis = [
            [self.translate("kpi_avg_co2_emissions"), f"{round(self.kpis.avg_co2_emissions, 2)} t/a"],
            [self.translate("kpi_avg_energy_costs"), f"{round(self.kpis.avg_operationCosts, 0)} €/a"],
            [self.translate("kpi_sys_costs_central"), f"{round(self.kpis.annual_fixed_costs_central, 0)} €/a"],
            [self.translate("kpi_sys_costs_decentral"), f"{round(self.kpis.annual_fixed_costs_decentral, 0)} €/a"],
            [self.translate("kpi_peak_load_el"), f"{round(max(self.kpis.peakDemand.values()), 1)} kW"],
            [self.translate("kpi_max_feed_in"), f"{round(max(self.kpis.peakInjection.values()), 1)} kW"],
            [self.translate("kpi_autonomy_rate"), f"{round(avg_autonomy * 100, 1)} %"],
            [self.translate("kpi_supply_cover_ratio"), f"{round(avg_scf * 100, 1)} %"],
            [self.translate("kpi_demand_cover_ratio"), f"{round(avg_dcf * 100, 1)} %"],
        ]

        # max loads in kW
        self.max_loads_table = [
            [f"{self.translate('name_heat')}:", f"{int(round(self.kpis.total_heat_peak / to_kW))} kW"],
            [f"{self.translate('name_el')}:", f"{int(round(self.kpis.total_electricity_peak / to_kW))} kW"],
            [f"{self.translate('name_dhw')}:", f"{int(round(self.kpis.total_dhw_peak / to_kW))} kW"],
            [f"{self.translate('name_cool')}:", f"{int(round(self.kpis.total_cooling_peak / to_kW))} kW"]
        ]

        # energy demand in MWh/a
        self.pie_chart_energy = {
            self.translate("name_el"): round(self.kpis.total_electricity_demand / to_MWh, 2),
            self.translate("name_heat"): round(self.kpis.total_heating_demand / to_MWh, 2),
            self.translate("name_dhw"): round(self.kpis.total_dhw_demand / to_MWh, 2),
            self.translate("name_cool"): round(self.kpis.total_cooling_demand / to_MWh, 2),
            self.translate("name_ev"): round(self.kpis.total_EV_demand / to_MWh, 2)
        }

        # Bar charts:
        self.bar_costs_data = []
        self.bar_co2_data = []

        for y in years:
            # Fetch cost breakdown
            costs = self.kpis.detailed_costs_year[y]
            self.bar_costs_data.append({
                "Year": y,
                self.translate("name_central_costs"): round(costs["eh_fixed"], 0),
                self.translate("name_decentral_costs"): round(costs["decentral_fixed"], 0),
                self.translate("name_el"): round(costs["electricity"], 0),
                self.translate("name_gas"): round(costs["gas"], 0),
                self.translate("name_biomethane"): round(costs.get("biomethane", 0), 0),
                self.translate("name_oil"): round(costs["oil"], 0),
                self.translate("name_waste"): round(costs["waste"], 0),
                self.translate("name_biomass"): round(costs["biomass"], 0),
                self.translate("name_district_heat"): round(costs["district_heat"], 0),
                self.translate("name_hydrogen"): round(costs["hydrogen"], 0),
                self.translate("name_feed_in_revenue"): round(costs["revenue_feed_in_el"], 0)
            })

            # Fetch CO2 breakdown
            em = self.kpis.co2emissions[y]
            self.bar_co2_data.append({
                "Year": y,
                self.translate("name_el"): round(em["co2_dem_grid"], 2),
                self.translate("name_gas"): round(em["co2_gas"], 2),
                self.translate("name_biomethane"): round(em.get("co2_biomethane", 0), 2),
                self.translate("name_oil"): round(em["co2_oil"], 2),
                self.translate("name_waste"): round(em["co2_waste"], 2),
                self.translate("name_biomass"): round(em["co2_biom"], 2),
                self.translate("name_district_heat"): round(em["co2_district_heat"], 2),
                self.translate("name_hydrogen"): round(em["co2_hydrogen"], 2),
            })

            # Maybe later add also the development of the energy demand over the years as a stacked bar if renovation measures or other changes are implemented in the multi-year simulation.

            self.kennwerte = {
                "district_key_kpis": self.district_key_kpis,
                "district_operation_kpis": self.district_operation_kpis,
                "max_loads_table": self.max_loads_table,
                "pie_chart_energy": self.pie_chart_energy,
                "bar_costs_data": self.bar_costs_data,
                "bar_co2_data": self.bar_co2_data,
                "observation_time": obs_time
            }

    def _extract_district_structure(self):
        """Extracts the structural information of the district and prepares tables."""
        res_types = {'SFH', 'TH', 'MFH', 'AB'}
        mixed_types = {'MIXED'}

        ghd_types = {'OB', 'SC', 'GS', 'RE', 'UNI', 'HOSPITAL', 'CULTURE', 'SPORT', 'RETAIL',
                     'WORKSHOP'}  # DO not use  -> Use all that are not residential or mixed as GHD

        first_b_type = list(self.building_stats.keys())[0]
        all_keys = list(self.building_stats[first_b_type].keys())
        age_classes = all_keys[2:]  # Change to actively exclude Anzahl and Gesamtfläche instead of relying on the order

        agg_stats = {
            self.translate("name_res_bldg"): {self.translate("name_number_bldgs"): 0,
                                              self.translate("name_total_area"): 0},
            self.translate("name_mixed_bldg"): {self.translate("name_number_bldgs"): 0,
                                                self.translate("name_total_area"): 0},
            self.translate("name_com_bldg"): {self.translate("name_number_bldgs"): 0,
                                              self.translate("name_total_area"): 0}
        }
        for cat in agg_stats:
            for age in age_classes:
                agg_stats[cat][age] = 0

        details_rows = []

        # Build the aggregated stats and the details rows at the same time by iterating through the building types only once
        for b_type, stats in self.building_stats.items():

            # Map to main category
            if b_type in res_types:
                cat = self.translate("name_res_bldg")
            elif b_type in mixed_types:
                cat = self.translate("name_mixed_bldg")
            else:
                cat = self.translate("name_com_bldg")

            # Sum up for the compact table
            agg_stats[cat][self.translate("name_number_bldgs")] += stats[self.translate("name_number_bldgs")]
            agg_stats[cat][self.translate("name_total_area")] += stats[self.translate("name_total_area")]
            for age in age_classes:
                agg_stats[cat][age] += stats[age]

            # Detailed row for the landscape page - ALWAYS appended
            translated_name = self._translate_building_type(b_type)
            detail_row = {
                self.translate("name_building_type"): translated_name,
                self.translate("name_number_bldgs"): stats[self.translate("name_number_bldgs")] if stats[self.translate(
                    "name_number_bldgs")] > 0 else "-"
            }
            for age in age_classes:
                detail_row[age] = f"{round(stats[age])} m²" if stats[age] > 0 else "-"
            details_rows.append(detail_row)

        # Summary Table displayed on the first page
        summary_table_data = [
            ["", self.translate("name_res_bldg"), self.translate("name_mixed_bldg"), self.translate("name_com_bldg")],
            [self.translate("name_number_bldgs"),
             str(agg_stats[self.translate("name_res_bldg")][self.translate("name_number_bldgs")]) if
             agg_stats[self.translate("name_res_bldg")][self.translate("name_number_bldgs")] > 0 else "-",
             str(agg_stats[self.translate("name_mixed_bldg")][self.translate("name_number_bldgs")]) if
             agg_stats[self.translate("name_mixed_bldg")][self.translate("name_number_bldgs")] > 0 else "-",
             str(agg_stats[self.translate("name_com_bldg")][self.translate("name_number_bldgs")]) if
             agg_stats[self.translate("name_com_bldg")][self.translate("name_number_bldgs")] > 0 else "-"],
            [self.translate("name_total_area"),
             f"{round(agg_stats[self.translate("name_res_bldg")][self.translate("name_total_area")])} m²" if
             agg_stats[self.translate("name_res_bldg")][self.translate("name_total_area")] > 0 else "-",
             f"{round(agg_stats[self.translate("name_mixed_bldg")][self.translate("name_total_area")])} m²" if
             agg_stats[self.translate("name_mixed_bldg")][self.translate("name_total_area")] > 0 else "-",
             f"{round(agg_stats[self.translate("name_com_bldg")][self.translate("name_total_area")])} m²" if
             agg_stats[self.translate("name_com_bldg")][self.translate("name_total_area")] > 0 else "-"]
        ]
        for age in age_classes:
            w_area = agg_stats[self.translate("name_res_bldg")][age]
            m_area = agg_stats[self.translate("name_mixed_bldg")][age]
            g_area = agg_stats[self.translate("name_com_bldg")][age]

            summary_table_data.append([
                age,
                f"{round(w_area)} m²" if w_area > 0 else "-",
                f"{round(m_area)} m²" if m_area > 0 else "-",
                f"{round(g_area)} m²" if g_area > 0 else "-"
            ])

        # General info to be displayed below the summary table on the first page
        general_info = [
            [self.translate("gen_info_nb_dwellings"), str(self.kpis.totalnumberflats)],
            [self.translate("gen_info_nb_residents"), str(self.kpis.totalnumberocc)],
            [self.translate("gen_info_postal_code_loc"), f"{str(self.data.site['zip'])}"],
            # ["Quartiersfläche", f"{round(self.data.site['district_area'], 2)} ha"],
            [self.translate("gen_info_ref_year"), f"{str(self.data.site['TRYYear'])[3:]} / {self.data.site['TRYType']}"]
        ]

        # 4. Pack everything into the final structure
        self.district_structure = {
            "summary_table": summary_table_data,
            "general_info": general_info,
            "df_details": pd.DataFrame(details_rows)
        }

    def _translate_building_type(self, b_type: str) -> str:
        """Translates the building type from the data to the display name."""
        return self.translate(f"bldg_{b_type}")

    def _extract_energyhub_data(self):
        """Extracts the energyhub data for central devices."""
        try:
            capacities = self.data.centralDevices["capacities"]
            central_configs = self.data.central_device_data

            col_device = self.translate("table_device_colname")
            col_capacity = self.translate("table_capacity_colname")
            col_cost = self.translate("table_cost_sub_colname")
            not_selected_text = self.translate("msg_not_selected")

            device_list = []

            def append_energyhub_row(device_name, capacity, annual_cost):
                device_list.append({
                    col_device: device_name,
                    col_capacity: capacity,
                    col_cost: annual_cost
                })

            all_cost_devices = set(self.kpis.central_individual_devices_annualized_cost.keys())

            # Iterate through all feasible devices
            for dev, config in central_configs.items():
                if not isinstance(config, dict):
                    continue
                if not config.get("feasible", False):
                    continue

                cap = 0
                annual_cost_sub = "-"
                annual_cost_unsub = "-"
                cost_unit = ""

                if dev in capacities:
                    spec = capacities[dev]
                    # Strict access: if spec is a dict, it MUST have 'cap'
                    cap = round(spec["cap"], 2)

                    if dev in self.kpis.central_individual_devices_annualized_cost:
                        device_cost_info = self.kpis.central_individual_devices_annualized_cost[dev]
                        annual_cost_sub = round(device_cost_info["subsidized_annual_cost"], 2)
                        annual_cost_unsub = round(device_cost_info["unsubsidized_annual_cost"], 2)
                        all_cost_devices.discard(dev) # Remove this device from the set of devices as it has been processed
                        cost_unit = " €/a"

                # Get the device name and unit
                name, base_unit = self.get_central_device_name(dev)

                display_cap, display_unit = self._determine_unit(cap=cap * 1000, base_unit=base_unit)

                if cap <= 0:
                    display_cap = not_selected_text

                # Append dict to the device list
                append_energyhub_row(
                    device_name=name,
                    capacity=f"{display_cap} {display_unit}".strip(),
                    annual_cost=f"{annual_cost_sub}{cost_unit}"
                )

            # Add all devices that are in the cost breakdown but not in the feasible central device data
            for dev in all_cost_devices:
                cost = round(self.kpis.central_individual_devices_annualized_cost[dev]['subsidized_annual_cost'], 2)
                if cost == 0:
                    continue  # Skip devices that have zero cost
                elif cost > 0:
                    cost_unit = " €/a"

                name, base_unit = self.get_central_device_name(dev)
                cap = 0
                display_cap, display_unit = self._determine_unit(cap=cap * 1000,
                                                                 base_unit=base_unit)  # Convert kW to W for unit determination

                if display_cap <= 0:
                    display_cap = "-"

                append_energyhub_row(
                    device_name=name,
                    capacity=f"{display_cap} {display_unit}".strip(),
                    annual_cost=f"{cost}{cost_unit}"
                )

            # Create the DataFrame only if devices are present
            if device_list:
                self.energyhub_df = pd.DataFrame(device_list)
            else:
                self.energyhub_df = None


        except (KeyError, AttributeError) as e:
            # If no central devices are defined, set energyhub_df to None
            if "capacities" not in self.data.centralDevices:  # if truly no central devices are defined
                self.energyhub_df = None
            else:
                raise Exception(
                    f"Error extracting energyhub data. Please check the structure of centralDevices and central_device_data in the input data.\n Caused error: {e}")

    def _extract_decentral_data(self):
        """Extracts and aggregates decentral device capacities and counts across all buildings, excluding EV."""
        try:
            aggregated_data = {}

            # 1. Iterate over all buildings and their decentral devices
            for b_index, devices in self.kpis.decentral_individual_devices_annualized_cost.items():
                for dev_name, info in devices.items():
                    # Skip Electric Vehicles and virtual measures
                    if dev_name in ["T_reduction_measures"]:
                        continue

                    # Direct access to enforce crash on missing keys
                    cap = info["cap"]
                    cost = info["subsidized_annual_cost"]

                    if cap == '' or cap is None:
                        cap = 0

                    cap_float = float(cap)
                    cost_float = float(cost)

                    # Initialize dictionary structure for new devices
                    if dev_name not in aggregated_data:
                        aggregated_data[dev_name] = {"count": 0, "total_cap": 0.0, "total_cost": 0.0}

                    # Add to aggregate sum and increment the count
                    if dev_name == "EV":
                        ev_caps = self.data.district[int(b_index)]["user"].ev_capacity
                        if ev_caps is None:
                            ev_caps = []
                        elif isinstance(ev_caps, (int, float)):
                            ev_caps = [ev_caps]

                        ev_count = sum(1 for x in ev_caps if float(x) > 0)
                        aggregated_data[dev_name]["count"] += ev_count
                    else:
                        aggregated_data[dev_name]["count"] += 1

                    aggregated_data[dev_name]["total_cap"] += cap_float
                    aggregated_data[dev_name]["total_cost"] += cost_float

            device_list = []

            # 2. Format the aggregated data into a list of dictionaries for the DataFrame
            for dev_name, data in aggregated_data.items():
                name, base_unit = self.get_decentral_device_name(dev_name)

                if "W" in base_unit:
                    cap_for_determination = data[
                                                'total_cap'] * 1000  # For devices with power or energy units the conversion requires W or Wh as input
                else:
                    cap_for_determination = data['total_cap']

                total_cap_adjusted, total_unit_adjusted = self._determine_unit(cap=cap_for_determination,
                                                                               base_unit=base_unit)
                total_power = f"{total_cap_adjusted} {total_unit_adjusted}".strip()

                cost = round(data['total_cost'], 2)
                if cost == 0:
                    ann_cost = f"-"
                elif cost > 0:
                    ann_cost = f"{cost} €/a"
                else:
                    raise ValueError(
                        f"Negative cost value encountered for device {dev_name}: {cost}. Please check the input data for inconsistencies.")

                device_list.append({
                    self.translate("table_device_colname"): name,
                    self.translate("table_count_colname"): data["count"],
                    self.translate("table_total_cap_colname"): total_power,
                    self.translate("table_cost_colname"): ann_cost
                })

            # 3. Create the DataFrame
            if device_list:
                self.decentral_df = pd.DataFrame(device_list)
            else:
                self.decentral_df = None

        except AttributeError as e:
            print(f"Warning: Decentral device data could not be extracted. {e}")
            self.decentral_df = None

    def _extract_energyhub_profiles(self):
        self.energyhub_profiles = {}
        for year, clusters in self.data.resultsOptimization.items():
            self.energyhub_profiles[year] = {}
            for cluster, result in clusters.items():
                self.energyhub_profiles[year][cluster] = opti_central.get_profiles_eh(result, data=self.data)

    def _extract_district_layout(self):
        """Extracts district layout information including building positions, network topology, and installed devices."""
        layout_data = {
            "buildings": [],
            "network_nodes": {},
            "network_edges": {},
            "pipeline_data": {}
        }

        # Extract building positions, connectivity status, and devices
        for building in self.data.district:
            features = building["buildingFeatures"]

            # Safely get position
            if "position" in features and isinstance(features["position"], (tuple, list)) and len(
                    features["position"]) >= 2:
                pos = features["position"]

                # Check for installed devices (capacity > 0)
                installed_devices = []
                if "capacities" in building:
                    for device_name, cap in building["capacities"].items():
                        # Capacities can be either a dict {"cap": X} or a direct number
                        if isinstance(cap, dict) and "cap" in cap and float(cap["cap"]) > 0:
                            installed_devices.append(device_name)
                        elif isinstance(cap, (int, float)) and float(cap) > 0:
                            installed_devices.append(device_name)

                # If the heater is defined in features and not in capacities, add it
                main_heater = features["heater"]
                if main_heater not in installed_devices:
                    installed_devices.append(main_heater)

                layout_data["buildings"].append({
                    "id": features["original_bldg_id"],
                    "name": building["unique_name"],
                    "x": float(pos[0]),
                    "y": float(pos[1]),
                    "type": features["building"],
                    "is_connected": main_heater == "heat_grid",
                    "devices": installed_devices
                })

        # Extract network topology if central heating network was generated
        if hasattr(self.data, 'pipeline_nodes') and self.data.pipeline_nodes:
            layout_data["network_nodes"] = self.data.pipeline_nodes

        if hasattr(self.data, 'pipeline_topology') and self.data.pipeline_topology:
            layout_data["network_edges"] = self.data.pipeline_topology

        if hasattr(self.data, 'pipeline') and self.data.pipeline:
            layout_data["pipeline_data"] = self.data.pipeline

        self.district_layout = layout_data

    def _extract_cluster_info(self):
        self.cluster_info = {}
        cluster_length_sec = self.data.time["clusterLength"]
        self.cluster_info["cluster_length_sec"] = cluster_length_sec

        start_of_year = datetime(2025, 1, 1, 0, 0, 0)
        total_periods = sum(self.data.clusterWeights.values())
        cluster_meta = getattr(self.data, "cluster_meta", {}) or {}
        typedays = cluster_meta.get("typedays")

        for k in range(len(self.data.clusters)):  #
            orig_idx = self.data.clusters[k]
            period_idx = int(typedays[k]) if typedays is not None and k < len(typedays) else int(orig_idx)
            start_date = start_of_year + timedelta(seconds=int(period_idx * cluster_length_sec))
            end_date = start_of_year + timedelta(seconds=int((period_idx + 1) * cluster_length_sec))
            start_str = start_date.strftime("%d.%m. %H:%M")
            end_str = end_date.strftime("%d.%m. %H:%M")
            weight_count = self.data.clusterWeights[orig_idx]

            self.cluster_info[k] = {
                "span": f"{start_str} - {end_str}",
                "weight": weight_count
            }

    def _extract_data(self):
        """Extracts and processes all necessary data for the certificate."""
        self._process_buildings()
        self._extract_kennwerte()
        self._extract_district_structure()
        self._extract_energyhub_data()
        self._extract_decentral_data()
        self._extract_energyhub_profiles()
        self._extract_district_layout()
        self._extract_cluster_info()
        # Additional data extraction methods can be added here

    def get_central_device_name(self, dev: str) -> tuple[str, str]:
        """
        Returns the central device name and unit based on the device key.

        Args:
            dev (str): device key (e.g. "HP", "PV").
            data (object): The data object containing central device data.

        Returns:
            tuple[str, str]: A tuple consisting of the full name and the unit.
        """

        device_unit_map = {  # if not specified, default is "W"
            "H2S": "Wh",
            "TES": "Wh<sub>th</sub>",
            "CTES": "Wh<sub>th</sub>",
            "BAT": "Wh<sub>el</sub>",
            "GS": "Wh",
            "PV": "W<sub>el</sub>",
            "WT": "W<sub>el</sub>",
            "WAT": "W<sub>el</sub>",
            "CHP": "W<sub>el</sub>",
            "BCHP": "W<sub>el</sub>",
            "WCHP": "W<sub>el</sub>",
            "ELYZ": "W<sub>el</sub>",
            "FC": "W<sub>el</sub>",
            "STC": "W<sub>th</sub>",
            "HP": "W<sub>th</sub>",
            "WaterHP": "W<sub>th</sub>",
            "EB": "W<sub>th</sub>",
            "BOI": "W<sub>th</sub>",
            "GHP": "W<sub>th</sub>",
            "BBOI": "W<sub>th</sub>",
            "WBOI": "W<sub>th</sub>",
            "CC": "W<sub>th</sub>",
            "AirCC": "W<sub>th</sub>",
            "AC": "W<sub>th</sub>",
            "Heat_Grid": "W<sub>th</sub>"
        }

        name = self.translate(f"device_{dev}")
        unit = device_unit_map.get(dev, "W")

        return name, unit

    def get_decentral_device_name(self, dev: str) -> tuple[str, str]:
        """
        Returns the decentral device name and unit based on the device key.
        Args:
            dev (str): device key (e.g. "HP", "PV", "OBOI").
        Returns:
            tuple[str, str]: A tuple consisting of the full name and the base unit (W or Wh) without any prefixes.
        """

        device_unit_map = {
            "BAT": "Wh<sub>el</sub>",
            "TES": "l",
            "TES_DHW": "l",
            "EV": "Wh<sub>el</sub>",
            "STC": "m²",
            "PV": "m²",
            "HP": "W<sub>th</sub>",
            "HP35": "W<sub>th</sub>",
            "HP55": "W<sub>th</sub>",
            "EH": "W<sub>th</sub>",
            "EWH": "W<sub>th</sub>",
            "CHP": "W<sub>th</sub>",
            "BOI": "W<sub>th</sub>",
            "BBOI": "W<sub>th</sub>",
            "OBOI": "W<sub>th</sub>",
            "H2BOI": "W<sub>th</sub>",
            "FC": "W<sub>th</sub>",
            "DH": "W<sub>th</sub>",
            "heat_grid": "W<sub>th</sub>",
            "CC": "W<sub>th</sub>"
        }

        # All devices
        name = self.translate(f"device_{dev}")
        base_unit = device_unit_map.get(dev, "W")
        return name, base_unit

    @staticmethod
    def _determine_unit(cap: float, base_unit: str) -> tuple[float, str]:
        """
        Determines the appropriate unit (kW, MW, GW) based on the capacity value and the base unit.
        Input cap is expected to be in W/Wh/m²/l.

        Args:
            cap (float): The capacity value in W/Wh/m²/l.
            base_unit (str): The base unit (e.g., "W", "Wh", "m²", "l"). Does allow suffixes like "W<sub>th</sub>".

        Returns:
            tuple[float, str]: A tuple containing the adjusted capacity and the appropriate unit.
        """

        if base_unit == "m²":
            if cap <= 0:
                adjusted_cap = cap
                adjusted_unit = ""  # No prefix for zero or negative values
            else:
                adjusted_cap = round(cap, 2)
                adjusted_unit = base_unit

        elif base_unit == "l":
            if cap >= 1000:
                adjusted_cap = round(cap / 1000, 2)
                adjusted_unit = "m³"  # Cubic meters for large volumes
            else:
                adjusted_cap = int(round(cap, 0))
                adjusted_unit = "l"

        elif cap <= 0:
            adjusted_cap = cap
            adjusted_unit = base_unit

        elif cap >= 1000000000:
            adjusted_cap = round(cap / 1000000000, 2)
            adjusted_unit = "G" + base_unit  # Giga
        elif cap >= 1000000:
            adjusted_cap = round(cap / 1000000, 2)
            adjusted_unit = "M" + base_unit  # Mega
        elif cap >= 1000:
            adjusted_cap = round(cap / 1000, 2)
            adjusted_unit = "k" + base_unit  # Kilo
        else:
            adjusted_cap = round(cap, 2)
            adjusted_unit = base_unit

        return adjusted_cap, adjusted_unit

    def get_kennwerte(self):
        return self.kennwerte

    def get_optimization_results(self):
        return self.optimization_results

    def get_district_structure(self):
        return self.district_structure

    def get_building_df(self):
        return self.gebaude_df

    def get_energyhub_df(self):
        return self.energyhub_df

    def get_decentral_df(self):
        return self.decentral_df

    def get_energyhub_profiles(self):
        return self.energyhub_profiles

    def get_district_layout(self):
        return self.district_layout

    def get_scenario_name(self):
        return getattr(self.data, "output_scenario_name", self.data.scenario_name)

    def get_cluster_info(self):
        return self.cluster_info


################################################################################
# Certificate Builder
################################################################################

class CertificateBuilder(ReportComponent):
    """
    This class orchestrates the certificate creation by setting up data, theme, initializing the PDF template, and building the story.
    """

    def __init__(self, data, kpis, result_path) -> None:
        # Initialize and apply theme globally and load the translations dict

        self.report_config = data.report_config
        self.language = data.report_config["language"]
        report_theme = ThemeManager(self.report_config)
        ReportComponent.apply_style(theme_manager=report_theme, language=self.language)

        self.data_object = DataExtractor(data=data, kpis=kpis)
        self.scenario_name = self.data_object.get_scenario_name()

        self.style = self.get_style()
        self.result_path = result_path

        if self.result_path is not None:
            os.makedirs(self.result_path, exist_ok=True)
            self.outputpath = os.path.join(result_path, f"Quartiersenergieausweis_{self.scenario_name}.pdf")
        else:
            src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.outputpath = os.path.join(src_path, "results", f"Quartiersenergieausweis_{self.scenario_name}.pdf")

        margins = self.style.get_page_margins()
        self.page_margins = {
            "TitlePage": (margins['x'], margins['y']),
            "ContentPage": (margins['x'], margins['y']),
            "InputDataPage": (margins['small_x'], margins['small_y']),
            "AdditionalInformationPage": (margins['small_x'], margins['small_y']),
        }

        self.doc = CertificateTemplate(self.outputpath, self.page_margins)
        self.layout = CertificateLayout(certificate_builder=self)

    def get_Framesize(self, id: str):
        return self.doc.get_Framesize(id)

    def generate_certificate(self):
        """
        Generates the certificate by creating the story of the individual pages.
        """
        story = []

        story.append(NextPageTemplate('TitlePage'))
        self.layout.create_header()
        self.layout.create_energiekennwerte(data_energiekennwerte=self.data_object.get_kennwerte())
        self.layout.create_quartiersstruktur(data_quartiersstruktur=self.data_object.get_district_structure())

        story.extend(self.layout.get_story())
        self.layout.reset_story()
        story.append(FrameBreak())

        self.layout.create_footer(str(self.scenario_name))
        story.extend(self.layout.get_story())
        self.layout.reset_story()

        story.append(NextPageTemplate('ContentPage'))
        story.append(PageBreak())

        self.layout.create_yearly_bar_charts(self.data_object.get_kennwerte())
        story.extend(self.layout.get_story())
        self.layout.reset_story()
        story.append(PageBreak())

        self.layout.create_energyhub_data(data_energyhub=self.data_object.get_energyhub_df())
        self.layout.create_decentral_systems(data_decentral=self.data_object.get_decentral_df())
        story.extend(self.layout.get_story())
        self.layout.reset_story()
        story.append(PageBreak())

        self.layout.create_energyhub_profiles(data_profiles=self.data_object.get_energyhub_profiles(),
                                              kpi_data=self.data_object.get_kennwerte(),
                                              cluster_info=self.data_object.get_cluster_info())
        story.extend(self.layout.get_story())
        self.layout.reset_story()

        story.append(NextPageTemplate('InputDataPage'))
        story.append(PageBreak())
        self.layout.create_district_layout(data_district_layout=self.data_object.get_district_layout())
        story.extend(self.layout.get_story())
        self.layout.reset_story()

        story.append(PageBreak())
        self.layout.create_quartiersstruktur_details(data_quartiersstruktur=self.data_object.get_district_structure())
        story.extend(self.layout.get_story())
        self.layout.reset_story()

        story.append(PageBreak())
        self.layout.create_input_data_table(data_input=self.data_object.get_building_df())
        story.extend(self.layout.get_story())
        self.layout.reset_story()

        story.append(NextPageTemplate('AdditionalInformationPage'))
        story.append(PageBreak())

        self.layout.create_hinweise()
        story.extend(self.layout.get_story())
        self.layout.reset_story()

        story.append(PageBreak())

        self.doc.build(story)
        print(f"Certificate saved to {self.outputpath}")


if __name__ == "__main__":
    print("All imports successful.")
