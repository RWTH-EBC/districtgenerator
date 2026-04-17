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

Version Date: 31.03.2026
"""

import sys
from districtgenerator.classes import *
from reportlab.platypus  import SimpleDocTemplate, BaseDocTemplate, PageTemplate, Frame
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, StyleSheet1, ParagraphStyle
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, Spacer
from reportlab.platypus import NextPageTemplate, PageBreak, FrameBreak
from datetime import datetime
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


DEBUG = False # If set to true boxes are drawn around the different components to visualize the layout and available space
debug_line_width = 0.1 # Line width for the debug boxes
    
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
        'A3': { # Overwrites for A3. If a parameter is not specified here, the A4 value is used.
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
        self.report_config = report_config # Contains info about sizing, fonts and colors
        self.pagesize = self.report_config["pagesize"]
        self.colors = self.report_config["colors"]
        self.fonts = self.report_config["fonts"]

        available_pagesizes = {"A3", "A4"}
        if self.pagesize not in available_pagesizes:
            print(f"Warning: Pagesize '{self.pagesize}' not recognized. Available options are: {available_pagesizes}. Defaulting to 'A4'.")
            self.pagesize = "A4"

        self.layout = self.FILE_LAYOUT["A4"].copy()

        # overwrite the A4 baseline with pagesize specific values
        if self.pagesize != 'A4':
            self.layout.update(self.FILE_LAYOUT[self.pagesize])

    # --- Getters for Styles ---
    def get_color(self, color_type:str):
        """Returns the colors defined in the report configuration."""
        try:
            return self.colors[color_type]
        except KeyError:
            raise KeyError(f"Color type '{color_type}' not found. Available options: {list(self.colors.keys())}")
    
    def get_energy_color(self, energy_type:str):
        """Returns the color for the specified energy type."""
        try:
            return self.colors["energy"][energy_type]
        except KeyError:
            raise KeyError(f"Energy type '{energy_type}' not found. Available options: {list(self.colors['energy'].keys())}")
    
    def get_source_color(self, source_type:str):
        """Returns the color for the specified energy source type."""
        try:
            return self.colors["source"][source_type]
        except KeyError:
            raise KeyError(f"Source type '{source_type}' not found. Available options: {list(self.colors['source'].keys())}")
    
    def get_layout_color(self, layout_type: str):
        """Returns the color for district layout elements (connected, eh, etc.)."""
        try:
            return self.colors["layout"][layout_type]
        except KeyError:
            raise KeyError(f"Layout type '{layout_type}' not found. Available options: {list(self.colors['layout'].keys())}")

    def get_layout_size(self, size_type: str):
        """Returns the size for layout elements."""
        try:
            return self.report_config["sizes"][size_type]
        except KeyError:
            raise KeyError(f"Size type '{size_type}' not found. Available options: {list(self.report_config['sizes'].keys())}")
    
    def get_layout_options(self, option_type: str):
        """Returns the boolean value for the specified layout option."""
        try:
            return self.report_config["layout_options"][option_type]
        except KeyError:
            raise KeyError(f"Layout option type '{option_type}' not found. Available options: {list(self.report_config['layout_options'].keys())}")
    
    def get_font_size(self, font_type:str):
        """Returns the font size for the specified font type."""
        try:
            return self.fonts["sizes"][font_type]
        except KeyError:
            raise KeyError(f"Font type '{font_type}' not found. Available options: {list(self.fonts['sizes'].keys())}")
    
    def get_font(self, bold:bool=False):
        """Returns the font name based on whether bold is True or False."""
        return self.fonts["bold"] if bold else self.fonts["regular"]
    
    def get_line_width(self, line_type:str):
        """Returns the line width for the specified line type."""
        try:
            return self.layout['line_width'][line_type]
        except KeyError:
            raise KeyError(f"Line type '{line_type}' not found. Available options: {list(self.layout['line_width'].keys())}")
    
    def get_spacing(self, spacing_type:str):
        """Returns the spacing for the specified spacing type."""
        try:
            return self.layout['spacing'][spacing_type]
        except KeyError:
            raise KeyError(f"Spacing type '{spacing_type}' not found. Available options: {list(self.layout['spacing'].keys())}")
    
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
            raise ValueError(f"Pagesize '{self.pagesize}' not recognized. Available options are: {list(PAGESIZE_MAP.keys())}.")

        
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
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
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
    style = None # Shared static variable to hold the theme manager

    @classmethod
    def apply_style(cls, theme_manager: ThemeManager):
        """
        Sets the theme once for all components.
        """
        cls.style = theme_manager
    
    @classmethod
    def get_style(cls):
        """
        Returns the theme manager to access the styles. Can be used in all components after the theme has been set.
        """
        if cls.style is None:
            raise Exception("Theme not set. Please call ReportComponent.apply_style(theme_manager) before creating any components.")
        return cls.style
    

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
            raise NotImplementedError("Subclasses of BaseReportFlowable must implement the draw_content() method to draw their content.")

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
        self.title = title #str
        self.style = self.get_style() # Get the ThemeManager instance to access the styles and design parameters

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
        self.table_full_width = False # If True, table columns are adjusted to full width

    def set_content(self, content_flowable: Flowable, full_width:bool=False):
        """Allows placing of the content after initialization."""
        self.content_flowable = content_flowable
        self.table_full_width = full_width

    def get_available_height(self, availHeight=None):
        """Returns the available height for the content within the frame."""
        if self.height is None:
            if availHeight is not None:
                return availHeight - self.fontsize - 2*self.padding - self.line_width
            else:
                raise ValueError("FrameBox height is not set and no availHeight is given. Call wrap() first or give <availHeight>.")
        return self.height - self.fontsize - 2*self.padding - self.line_width

    def get_available_width(self, availWidth=None):
        """Returns the available width for the content within the frame."""
        if self.width is None:
            if availWidth is not None:
                return availWidth - 2*self.padding - 2*self.line_width
            else: raise ValueError("FrameBox width is not set and no availWidth is given. Call wrap() first or give <availWidth>.")
        return self.width - 2*self.padding - 2*self.line_width

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
                col_width = (self.width - 2*self.padding) / n_cols
                # Set the column widths
                self.content_flowable._argW = [col_width] * n_cols

            # content_height is height of the content
            content_width, content_height = self.content_flowable.wrap(availContentWidth, availContentHeight)
        else:
            content_height = 0

        # Needed Total height = title + content + padding above and below content + bottom line
        self.height = self.fontsize + content_height + 2*self.padding + self.line_width

        return self.width, self.height

    def draw_content(self):
        """Draw the frame with title and content."""
        c = self.canv # Canvas for frame
        c.saveState()

        w = self.width

        y_topframe = int(self.height - 2*self.fontsize/3 + self.line_width/2) # Position of the middle of the top line
        y_bottomframe = 0 # no padding below

        # Linestyle of the frame
        c.setStrokeColorRGB(*self.line_color)
        c.setLineWidth(self.line_width)
        c.setLineCap(2) # 

        title_text = str(self.title) # Title should be a string

        title_w = c.stringWidth(title_text, self.fontstyle, self.fontsize)

        y_title = int(y_topframe - self.line_width/2 - self.fontsize/3)
        gap = 5             # kleiner Abstand zwischen Linie und Text

        # --- Titel mittig zwischen Linien ---
        x_title = int(self.padding + gap)
        # --- Linien ---
        # Seitenrahmen
        c.line(0, y_topframe, 0, y_bottomframe) # linke Linie
        c.line(0, y_bottomframe, w, y_bottomframe) # untere Linie
        c.line(w, y_bottomframe, w, y_topframe) # rechte Linie
        
        # links
        c.line(0, y_topframe, x_title - gap, y_topframe)
        # rechts
        c.line(x_title + title_w + gap, y_topframe, w, y_topframe)

        # --- Titel ---
        c.setFont(self.fontstyle, self.fontsize)
        c.setFillColorRGB(*self.font_color)
        c.drawString(x_title, y_title, title_text)
        
        

        # Platzierung des Inhalts
        if self.content_flowable is not None:
            y = int(y_topframe - self.line_width/2 - self.fontsize/3 - self.padding) # Position of the top of the content area
            x = self.padding + self.line_width
            w_f, h_f = self.content_flowable.wrap(w - 2*x, y - y_bottomframe - self.padding - self.line_width)
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

        content_width = availWidth - 2*padding - 2*line_width
        content_height = availHeight - 2*padding - title_height - line_width

        return content_width, content_height

################################################################################
# Base elements (Flowables) that can be used in the layout
################################################################################

class Header(BaseReportFlowable):
    """
    This class generates the header section of the certificate.
    """
    def __init__(self, title="Quartiersenergieausweis") -> None:
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
        col_w_left = self.width *0.6
        col_w_right = self.width *0.4

        self.t_summary = self._build_listed_table(self.district_key_kpis)
        self.t_operation = self._build_listed_table(self.district_operation_kpis)
        self.pie_chart_flowable = EnergyPieChart(pie_data=self.energy_pie_data, availWidth=col_w_right)
        self.max_loads_flowable = MaxLoadsBarChart(max_loads_data=self.max_loads_data, availWidth=col_w_right)

        left_column_content = [Spacer(1, self.style.get_padding()),self.t_summary, Spacer(1, 3*self.style.get_padding()), Title("Optimierter Anlagenbetrieb"), Spacer(1, self.style.get_padding()), self.t_operation]
        right_column_content = [self.pie_chart_flowable, Spacer(1, self.style.get_padding()), self.max_loads_flowable]

        layout_data = [
            [left_column_content, right_column_content]
        ]
        
        self.layout_table = Table(layout_data, colWidths=[col_w_left, col_w_right])
        self.layout_table.setStyle(self.style.get_table_styles()['layout']) # No visible styling, just for layout
    
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
            "Strom": self.style.get_energy_color("electricity"),
            "Wärme": self.style.get_energy_color("heating"),
            "TWW": self.style.get_energy_color("dhw"),
            "Kälte": self.style.get_energy_color("cooling"),
            "EV": self.style.get_energy_color("ev")
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
        legend.y = -bounds[1] # Ensures the true bottom rests exactly at the lower bound
        
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

        
        d.add(String(width / 2.0, title_y, "Energiebedarfe in MWh/a", 
                     fontName=title_font, 
                     fontSize=title_size, 
                     textAnchor='middle',
                     fillColor=title_color))

        # Draw debug boxes for internal components
        if DEBUG:
            # Pie bounding box
            d.add(Rect(pie.x, pie.y, pie.width, pie.height, strokeColor=colors.red, strokeWidth=debug_line_width, fillColor=None))
            
            # Legend bounding box using exact final bounds
            final_bounds = legend.getBounds()
            l_x = final_bounds[0]
            l_y = final_bounds[1]
            l_w = final_bounds[2] - final_bounds[0]
            l_h = final_bounds[3] - final_bounds[1]
            d.add(Rect(l_x, l_y, l_w, l_h, strokeColor=colors.red, strokeWidth=debug_line_width, fillColor=None))

            # Title
            d.add(Rect(0, title_y, width, title_size, strokeColor=colors.red, strokeWidth=debug_line_width, fillColor=None))

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
        self.height = len(self.max_loads_data) * self.row_height + self.style.get_spacing('small') + self.title_font[1] # rows + spacing + title
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
        c.drawCentredString(self.width / 2.0, self.height - self.title_font[1], "Maximale Leistungen")
        
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
            y_pos = self.height - self.title_font[1] - self.style.get_spacing('small') - self.text_font[1] - (self.row_height * i)
            
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
        self.table._argW = [col_w, col_w, col_w, col_w] # All columns same width
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
        self.height = max(self.normal_fontsize, self.highlight_fontsize) + 2*self.padding + 2*self.line_width
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
        available_height = h - 2*self.padding - 2*self.line_width
        text_height = max(self.normal_fontsize, self.highlight_fontsize)
        y = self.padding + self.line_width + available_height / 2 - text_height/3
        
        x1 = self.padding + self.line_width
        string1 = "Quartiersname:"
        length1 = c.stringWidth(string1, self.highlight_fontstyle, self.highlight_fontsize) 
        gap = 3
        string2 = str(self.scenario_name)
        string3 = "Erstellt am: " + datetime.now().strftime('%d.%m.%Y %H:%M')

        c.setFont(self.highlight_fontstyle, self.highlight_fontsize)
        c.setFillColorRGB(*self.highlight_fontcolor)
        c.drawString(x1, y, string1)

        c.setFont(self.normal_fontstyle, self.normal_fontsize)
        c.setFillColorRGB(*self.normal_fontcolor)
        c.drawString(x1 + length1 + gap, y, string2)

        c.drawRightString(w - self.padding - self.line_width, y, string3)
        c.restoreState()

    @classmethod
    def get_required_height(cls,pagesize:tuple=A4):
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
        required_height = max(normal_fontsize, highlight_fontsize) + 2*padding + 2*line_width
        
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

        # Handle empty data
        if data_energyhub is None or data_energyhub.empty:
            box = FrameBox(title="Zentrale Energiesysteme")
            p = Paragraph("Es wurden keine zentralen Energiesysteme ausgelegt", style.get_paragraph_styles()['Normal'])
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
            box = FrameBox(title="Zentrale Energiesysteme")
            header = data_energyhub.columns.tolist()
            body = data_energyhub.values.tolist()
            standard_table = Table([header] + body)
            standard_table.setStyle(style.get_table_styles()['standard'])
            
            box.set_content(cls(content_flowable=standard_table))
            boxes.append(box)
            
        else:
            for i, eh_table in enumerate(eh_tables, start=1):
                title = f"Zentrale Energiesysteme ({i}/{len(eh_tables)})"
                box = FrameBox(title=title)
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

        # Handle empty data
        if data_decentral is None or data_decentral.empty:
            box = FrameBox(title="Dezentrale Energiesysteme")
            p = Paragraph("Es wurden keine dezentralen Energiesysteme ausgelegt", style.get_paragraph_styles()['Normal'])
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
            box = FrameBox(title="Dezentrale Energiesysteme")
            header = data_decentral.columns.tolist()
            body = data_decentral.values.tolist()
            standard_table = Table([header] + body)
            standard_table.setStyle(style.get_table_styles()['standard'])
            
            box.set_content(cls(content_flowable=standard_table))
            boxes.append(box)
            
        else:
            for i, dec_table in enumerate(dec_tables, start=1):
                title = f"Dezentrale Energiesysteme ({i}/{len(dec_tables)})"
                box = FrameBox(title=title)
                box.set_content(cls(content_flowable=dec_table))
                boxes.append(box)
        
        return boxes
    
class YearlyStackedBarCharts(BaseReportFlowable):
    """
    Generates stacked bar charts for each simulated year, with a shared legend below.
    """
    def __init__(self, costs_data: list, co2_data: list, availWidth: float, availHeight: float):
        super().__init__()
        self.style = self.get_style()
        self.costs_data = costs_data
        self.co2_data = co2_data
        self.availWidth = availWidth
        self.availHeight = availHeight
        
        self.drawing = self._create_drawing()
        self.width = self.drawing.width
        self.height = self.drawing.height

    def _create_drawing(self) -> Drawing:
        # Interpolation points (years) and categories for both charts
        years = sorted([item["Year"] for item in self.costs_data])
        years_co2 = sorted([item["Year"] for item in self.co2_data])
        if years != years_co2:
            raise ValueError(f"Mismatch in years between costs_data and co2_data ({years} vs {years_co2}). Ensure both datasets cover the same years as Simulations are linked.")
        year_labels = [str(y) for y in years]
        
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
                "title": "CO2-Emissionen (t/a)",
                "series": co2_series,
                "categories": co2_categories
            },
            {
                "title": "Kosten (€/a)",
                "series": cost_series,
                "categories": cost_categories
            }
        ]

        # CO2 Emissions in t/a or kg/a
        max_co2 = max([max(series) for series in co2_series]) if co2_series else 0 # Unit in t/a
        if max_co2 < 5:
            co2_series = [tuple(val * 1000 for val in series) for series in co2_series]
            charts_config[0]["title"] = "CO2-Emissionen (kg/a)"
            charts_config[0]["series"] = co2_series

        # Costs in t€/a or €/a
        max_costs = max([max(series) for series in cost_series]) if cost_series else 0 # Unit in €/a
        if max_costs > 5000:
            cost_series = [tuple(val / 1000 for val in series) for series in cost_series]
            charts_config[1]["title"] = "Kosten (Tsd. €/a)"
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
                    "Anlagenkosten zentral": "eh_fixed",
                    "Anlagenkosten dezentral": "decentral_fixed",
                    "Strom": "electricity",
                    "Gas": "gas",
                    "Öl": "oil",
                    "Abfall": "waste",
                    "Biomasse": "biomass",
                    "Fernwärme": "district_heat",
                    "Wasserstoff": "hydrogen",
                    "Einspeiseerlöse (el.)": "revenue_feed_in_el"
                }
                
                # Check if the exact string exists in our mapping
                if category in mapping:
                    color_key = mapping[category]
                    return self.style.get_source_color(color_key)
                
                # Fallback if the string is not in the explicit list
                print(f"Warning: Category '{category}' not found in color mapping. Using secondary color as fallback. Check if color {mapping[category]} is defined in the config.")
                return self.style.get_color("secondary_color")
                
            except KeyError:
                # Fallback if the color key itself is missing in the theme config
                print(f"Warning: Category '{category}' not defined in color mapping. Using secondary color as fallback.")
                return self.style.get_color("secondary_color")
 
        # --- Placement Calculations ---
        padding = self.style.get_padding()
        drawing_width = self.availWidth
        x_align = 3 * self.style.get_padding()
        chart_width = drawing_width - 2*x_align # Leave padding on the sides

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
            d.add(Rect(legend.x, padding, actual_legend_width, actual_legend_height, strokeColor=colors.red, strokeWidth=debug_line_width, fillColor=None))
        
        current_y = legend.y + padding # LOWER LIMIT NO element should extend below this!

        # --- Dynamic Height Calculation --
        num_charts = len(charts_config)
        remaining_space = self.availHeight - current_y
        remaining_space -= padding * (num_charts - 1) # Account for padding between charts

        max_block_height = 200 
        total_chart_height = min(remaining_space / num_charts, max_block_height)

        # Iterate through the charts to draw them according to the defined charts_config
        for chart in charts_config:            
            setoff_chart_start = (axis_label_size) + self.style.get_spacing("small") + (axis_size * 1.2)
            title_height = title_size * 1.2
            chart_height = total_chart_height - setoff_chart_start - title_height - padding # Leave space for title and axis labels

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
            d.add(String(bc.x + chart_width/2, title_y, chart["title"], fontName=title_font, fontSize=title_size, textAnchor='middle'))
            d.add(String(bc.x + chart_width/2, current_y, "Stützjahr", fontName=axis_label_font, fontSize=axis_label_size, textAnchor='middle'))

            total_chart_height = title_y - current_y + title_size 

            # For debug purposes: Draw bounding boxes around the charts
            if DEBUG:
                d.add(Rect(bc.x, current_y, bc.width, total_chart_height, strokeColor=colors.red, strokeWidth=debug_line_width, fillColor=None))
            
            
            current_y += total_chart_height + padding # Next chart starts after the chart height including the title and all text. 

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
    def __init__(self, input_data:pd.DataFrame=None) -> None:
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
        return self.width, self.height # Takes the whole available space
    
    def draw_content(self):
        self.table.drawOn(self.canv, 0, self.height - self.actual_height) #Placement at the top-left corner

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
        self.hinweise_content = {
            "Energetische Kennwerte":{
                    "Nutzenergiebedarf": "Über alle Gebäude aufsummierter Nutzenergiebedarf (Haushaltsstrom, Wärme, Trinkwarmwasser, Kälte und EV-Strom)",
                    "Norm-Heizlast": "Über alle Gebäude aufsummierte Norm-Heizlast nach DIN EN ISO 13790",
                    "Energiebedarfe (MWh)": "Über alle Gebäude aufsummierten Jahresenergiebedarfe auf Basis der generierten Bedarfsprofile (für Wärme, Kälte, Haushaltsstrom, Trinkwarmwasser (TWW) und Elektroautos (EV))",
                    "Maximale Leistungen": "Maximale Leistungen in kW im Quartier auf Basis der aufsummierten Bedarfsprofile aller Gebäude (ohne Betriebsoptimierung)"
                },
            "Optimierter Anlagenbetrieb":{
                    "Ø CO2-Emissionen": "Im Quartier emittierte CO2-Äquivalente in t/a durch den optimierten Betrieb (Gasbedarf und Strombedarf)",
                    "Ø Energiekosten": "Spezifische Betriebskosten des gesamten Quartiers in €/kWh auf Basis der Betriebsoptimierung",
                    "Anlagenkosten": "Annuitätische Fixkosten aller installierten Energieanlagen. Dies beinhaltet die umgelegten Investitionskosten (CAPEX) abzüglich Subventionen sowie feste Betriebs- und Wartungskosten (O&M).",
                    "Spitzenlast (el.)": "Maximaler Strombezug des gesamten Quartiers aus übergeordnetem Stromnetz auf Basis der Betriebsoptimierung",
                    "Max. Einspeiseleistung": "Maximale Stromeinspeisung des gesamten Quartiers in übergeordnetes Stromnetz auf Basis der Betriebsoptimierung",
                    "Einspeiseerlöse (el.)": "Erlöse durch die Einspeisung von lokal erzeugtem Strom in das übergeordnete Stromnetz auf Basis der Betriebsoptimierung in €/a",
                    "Autarkiegrad": "Anteil der Betriebszeit, in der der lokale Strombedarf vollständig durch die Stromerzeugung im Quartier gedeckt wird (Werte zwischen 0 % und 100 %)",
                    "Supply-Cover-Faktor": "Anteil des aus den Gebäuden des Quartiers ins lokale Netz eingespeisten Stroms, der für den Eigenverbrauch innerhalb des Quartiers durch andere Gebäude genutzt wird (Werte zwischen 0 % und 100 %)",
                    "Demand-Cover-Faktor": "Anteil des residualen Strombedarfs im Quartier, der durch den von den Gebäuden im Quartier erzeugten und ins lokale Netz eingespeisten Stroms gedeckt wird (Werte zwischen 0 % und 100 %)"
                },
            "Bezeichnungen für die Quartierstruktur und das Quartierslayout":
                {
                    "GHD-Gebäude": "Gewerbe-, Handels- und Dienstleistungsgebäude",
                    "Mischgebäude": "Gebäude mit einer gemischten Nutzung aus Wohnen und GHD",
                    "Testreferenzjahr": "Verwendetes Referenzjahr für die Bedarfsermittlung sowie die Erzeugung von Erneuerbaren Energiequellen anhand von Wetterdaten",
                    "Energiezentrale": "Zentrale Energieerzeugungsanlage, die das Wärmenetz des Quartiers speist",
                    "DN (Nenndurchmesser)": "Innendurchmesser der verlegten Rohrleitungen des Wärmenetzes in Millimetern"
                },
            "Bezeichnungen in der Liste der Gebäude": 
                {
                    "Gebäude ID": "ID des Gebäudes zur eindeutigen Identifizierung",
                    "Gebäudetyp": "SFH = Einfamilienhaus, MFH = Mehrfamilienhaus, TH = Reihenhaus, AB = Wohnblock, OB = Bürogebäude, SC = Schule, GS = Lebensmittelgeschäft, RE = Restaurant, UNI = Universitätsgebäude, HOSPITAL = Krankenhaus, CULTURE = Kulturgebäude, SPORT = Sportgebäude, RETAIL = Handelsgebäude, WORKSHOP = Werkstattgebäude. Ein '+' (z. B. MFH+RETAIL) kennzeichnet ein Mischgebäude",
                    "Baujahr": "Baualtersklasse (vor 1969, 1968-1978, 1979-1983, 1984-1994, 1995-2001, 2002-2009, 2010-2015, ab 2016)",
                    "Sanierung für Wohngebäude": "0 = Bestand, 1 = Sanierung nach EnEV 2016, 2 = Sanierung nach KfW 55",
                    "Sanierung für Nichtwohngebäude": "0 = Nichtsaniert, 1 = Teilsaniert (nur Fenster und Wände), 2 = Vollsaniert (Decke, Fenster, Dach und Wände)",
                    "Sp-Masse": "Gebäudespeichermasse: 0 = Leichtbau, 1 = Mittelbau, 2 = Massivbau",
                    "N-Absenkung": "Nachtabsenkung: 0 = keine Nachtabsenkung, 1 = mit Nachtabsenkung",
                    "NRF": "Nettoraumfläche in m²",
                    "Heizung": "ausgewählter Wärmeerzeuger",
                    "EV": "Zwischen 0 und 1; Anteil der Elektroautos am Gesamtfahrzeugbestand im Gebäude",
                    "fTES": "Größe des Pufferspeichers in Liter pro kW Heizleistung der Wärmeerzeugungsanlage",
                    "fBAT": "Größe des Batteriespeichers in Abhängigkeit der Leistung der PV-Anlage in Wh/W_PV",
                    "fPV1": "Anteil der gesamten Dachfläche, der auf Dachseite 1 mit Photovoltaik belegt ist. Dachseite 1 ist dabei die Seite, für die der Azimutwinkel gammaPV vergeben wird (Informationen zu Dachflächen sind den Typgebäuden nach Tabula zu entnehmen)",
                    "fPV2": 'Anteil der gesamten Dachfläche, der auf Dachseite 2 mit Photovoltaik belegt ist. Der Azimutwinkel von Dachseite 2 wird als 180° zu gammaPV gedreht ("gegenüberliegend") berechnet.',
                    "fSTC": "Anteil der Dachfläche, die mit Solarthermie ausgestattet ist (Informationen zu Dachflächen sind den Typgebäuden nach Tabula zu entnehmen)",
                    "gammaPV": "Azimut = Himmelsausrichtung von Dachseite 1, Ausrichtung nach Süden entspricht 0°",
                    "EV Charging": "Ladeverhalten des Elektroautos (bi-direktional: Be- und Entladung, Nutzung als Stromspeicher, on-demand: Beladung nach Bedarf, intelligent: optimierte Beladung)"
                }
            }
        
        # Styling configuration
        self.styles = {
            'section_title': ParagraphStyle(
                'SectionTitle',
                fontName=self.style.get_font(bold=True),
                fontSize=self.style.get_font_size('highlighted'),
                alignment=0, #-> left aligned
                leftIndent=0, # no indent
                textColor=self.style.get_color('text')
            ),
            'item_definition': ParagraphStyle(
                'ItemDefinition',
                fontName=self.style.get_font(bold=False),
                fontSize=self.style.get_font_size('small'),
                alignment=0,# -> left aligned
                leftIndent=self.style.get_font_size('small'), # indent for the items
                firstLineIndent=-self.style.get_font_size('small'), # hanging indent
                textColor=self.style.get_color('text')
            )
        }
        self.layout = {'distance_after_title': self.styles['section_title'].fontSize * 0.3, # Distance after the section title
                       'distance_after_item': self.styles['item_definition'].fontSize * 0, # No distance after an item
                       'distance_after_section': self.styles['section_title'].fontSize * 0.5} # Distance after a section

    def get_filtered_content(self):
        """Returns the filtered hinweise_content based on sections_to_include."""
        if self.sections_to_include is None:
            return self.hinweise_content
        filtered_content = {section: content for section, content in self.hinweise_content.items() if section in self.sections_to_include}
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

        content_width = self.width - 2*self.padding
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
                
                # Position nach unten verschieben
                y_current -= item_height
                
                # Item zeichnen
                item_paragraph.drawOn(c, margin_left, y_current)
                y_current -= self.layout['distance_after_item']

            
            # Abstand zwischen Sektionen
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
        remaining_sections = list(dummy_instance.hinweise_content.keys()) # all sections that need to be placed

        hinweise = []
        
        while remaining_sections:
            # Test-Instanz erstellen mit den verbleibenden Sektionen
            test_hinweise = cls(sections_to_include=remaining_sections)
            test_hinweise.width = availWidth
            
            # Ermitteln welche Sektionen in diese Box passen
            sections_that_fit, sections_overflow = test_hinweise.get_sections_that_fit(availHeight)
            
            # Sicherstellen, dass mindestens eine Sektion verarbeitet wird
            if not sections_that_fit and remaining_sections:
                raise Exception("At least one section of the Hinweise content is too large to fit on one page. Please review the content.")
            
            # Hinweise-Flowable für die passenden Sektionen erstellen
            if sections_that_fit:
                hinweise_flowable = cls(sections_to_include=sections_that_fit)
                hinweise.append(hinweise_flowable)
            
                # Remaining sections für die nächste Iteration aktualisieren
                remaining_sections = sections_overflow

            else:
                # Sicherheitsabbruch falls keine Sektionen mehr vorhanden
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
        else: # left
            self.legend_offset_x = 0
            self.map_offset_x = self.legend_width

        self.map = self._create_map()
        self.legend = self._create_legend()

    def _create_map(self):

        d = Drawing(self.map_width, self.height)

        # Draw the outer boundary box #! Maybe remove later
        border = Rect(0, 0, self.map_width, self.height)
        border.strokeColor = colors.Color(1, 1, 1) # 1,1,1 is white (not visible), 0,0,0 would be black. Maybe use a light grey for better visibility of the layout elements? colors.Color(0.8, 0.8, 0.8)
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
            d.add(String(self.map_width / 2.0, self.height / 2.0, "Kein Quartierslayout verfügbar", 
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
            return # If no heat_grid is present, skip drawing pipes
        
        line_color = colors.Color(*self.style.get_layout_color("pipe"))
        max_pipe_width = self.style.get_layout_size('pipe')
        min_pipe_width = self.style.get_layout_size('pipe')/10 # Minimum line width for visibility, can be adjusted as needed
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
                y_top = hy + (h_triangle * (2.0/3.0))
                y_bottom = hy - (h_triangle * (1.0/3.0))
                
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
                                   fontSize=self.style.get_layout_size('label')*1.5, fillColor=eh_color, textAnchor='middle')
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
                type_label = String(bx, by - radius - self.style.get_layout_size('label'), type_text, fontName=self.style.get_font(bold=True), 
                               fontSize=self.style.get_layout_size('label'), fillColor=text_color, textAnchor='middle')
                group.add(type_label)

                id_text = f"({b['id']})"
                id_label = String(bx, by - radius - 2* self.style.get_layout_size('label'), id_text, fontName=self.style.get_font(bold=False),
                            fontSize=self.style.get_layout_size('label'), fillColor=text_color, textAnchor='middle')
                group.add(id_label)

    def _create_legend(self):
        d = Drawing(self.legend_width, self.height)

        padding = self.style.get_padding()
        size_elements = 10

        # X- Starting points (from left to right)
        start_x = padding
        sym_x = start_x + size_elements # Center of the symbols
        text_x = sym_x + size_elements + self.style.get_spacing('medium') # Start of the text, after symbol and some spacing
        



        text_color = colors.Color(*self.style.get_color("text"))
        legend_font_size = self.style.get_layout_size("legend_text")
        y_text_offset = legend_font_size / 3.0

        distance_entries = self.style.get_spacing('medium')

        # Y- Starting point (from top to bottom)
        current_y = self.height - padding

        # Scale:
        max_scale_width = self.legend_width - 2 * padding

        allowed_real_meters = []
        for power in range(0, 4): 
            allowed_real_meters.extend([1 * 10**power, 2.5 * 10**power, 5 * 10**power])
        
        # Find the best fitting scale value that is the closest to but smaller than the maximum width
        best_real_meters = 10 
        for val in reversed(allowed_real_meters):
            if val * self.scale <= max_scale_width:
                best_real_meters = val
                break
                
        drawn_length = best_real_meters * self.scale 

        scale_y = current_y - size_elements
        scale_start_x = start_x
        
        bar_height = 5            # Height of the scale bar
        num_segments = 4          # Number of blocks in the scale (e.g., 4 blocks for 0, 25%, 50%, 75%, 100%)
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

        #Start of the legend, below the scale
        box_start_y = scale_y - padding

        current_y = box_start_y - padding

        # Legend Title
        # font_size_title = self.style.get_font_size("subsection_title")
        # current_y -= font_size_title
        # d.add(String(start_x, current_y, "Legende", fontName=self.style.get_font(bold=True), fontSize=font_size_title, fillColor=text_color))
        # current_y -= distance_entries

        # Energy Hub
        current_y -= size_elements # Move to center of the symbol
        eh_color = colors.Color(*self.style.get_layout_color("eh"))
        h_triangle = math.sqrt(3) * size_elements
        
        y_top = current_y + (h_triangle * (2.0/3.0))
        y_bottom = current_y - (h_triangle * (1.0/3.0))
        
        eh_shape = Polygon([
            sym_x, y_top,                                 # Top
            sym_x - size_elements, y_bottom,              # Bottom left
            sym_x + size_elements, y_bottom               # Bottom right
        ])
        eh_shape.fillColor = eh_color
        eh_shape.strokeColor = colors.black
        eh_shape.strokeWidth = 0.5
        d.add(eh_shape)

        
        d.add(String(text_x, current_y- y_text_offset, "Energiezentrale",
                     fontName=self.style.get_font(bold=False), 
                     fontSize=legend_font_size, 
                     fillColor=text_color,
                     textAnchor = 'start'))

        current_y -= size_elements + distance_entries

        # Pipes
        current_y -= size_elements / 2.0 
        pipe_color = colors.Color(*self.style.get_layout_color("pipe"))
        pipe_width = 2*size_elements/10 

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
            d.add(String(sym_x, y_center_of_texts + pipe_width/2 + 2, "DN-X", 
                         fontName=self.style.get_font(bold=False), 
                         fontSize=legend_font_size * 0.8, 
                         fillColor=text_color, textAnchor='middle'))

            # Draw main text
            d.add(String(text_x, y_text_line1, "Rohre des Wärmenetzes", 
                         fontName=self.style.get_font(bold=False), 
                         fontSize=legend_font_size, 
                         fillColor=text_color,
                         textAnchor='start'))

            # Draw explanation text
            explanation_color = colors.Color(*self.style.get_color("text_light"))
            d.add(String(text_x, y_text_line2, "(DN-X = Nenndurchmesser in mm)", 
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
            d.add(String(text_x, current_y - y_text_offset, "Rohre des Wärmenetzes", 
                         fontName=self.style.get_font(bold=False), 
                         fontSize=legend_font_size, 
                         fillColor=text_color,
                         textAnchor='start'))

            current_y -= size_elements + distance_entries


        # Buildings connected to the heat grid
        current_y -= size_elements # Move to center of the symbol
        conn_color = colors.Color(*self.style.get_layout_color("building_connected"))
        b_conn = Circle(sym_x, current_y, r=size_elements)
        b_conn.fillColor = conn_color
        b_conn.strokeColor = colors.black
        b_conn.strokeWidth = 0.5
        d.add(b_conn)

        d.add(String(text_x, current_y - y_text_offset, "angeschlossene Gebäude", 
                     fontName=self.style.get_font(bold=False), 
                     fontSize=legend_font_size, 
                     fillColor=text_color,
                     textAnchor='start'))

        current_y -= size_elements + distance_entries


        # Buildings not connected to the heat grid
        current_y -= size_elements # Move to center of the symbol
        not_conn_color = colors.Color(*self.style.get_layout_color("building_not_connected"))
        b_not_conn = Circle(sym_x, current_y, r=size_elements)
        b_not_conn.fillColor = not_conn_color
        b_not_conn.strokeColor = colors.black
        b_not_conn.strokeWidth = 0.5
        d.add(b_not_conn)

        d.add(String(text_x, current_y - y_text_offset, "nicht angeschlossene Gebäude", 
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

        # Reduce the drawing height to the actual used height for the legend

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
    def create_header(self, title="Quartiersenergieausweis"):
        """Creates Header and adds it to the story."""
        header = Header(title=title)
        self.story.append(header)
        self.add_standard_spacer('large')

    def create_energiekennwerte(self, data_energiekennwerte):
        """Creates the Energiekennwerte section and adds it to the story."""
        box = FrameBox(title="Energetische Kennwerte")
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='TitleContentFrame')
        avail_w, avail_h = FrameBox.get_available_space_content(frame_width, frame_height)
        
        energiekennwerte = Energiekennwerte(kpi_data=data_energiekennwerte, availWidth=avail_w)
        box.set_content(energiekennwerte)
        self.story.append(box)
        self.add_standard_spacer()

    def create_quartiersstruktur(self, data_quartiersstruktur):
        """Creates the Quartiersstruktur section and adds it to the story."""
        box = FrameBox(title="Quartiersstruktur")
        
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
        
        for i, tab in enumerate(tables, start=1):
            title = "Netto Raumfläche nach Gebäudetyp und Altersklasse" if len(tables) == 1 else f"Netto Raumfläche nach Gebäudetyp und Altersklasse ({i}/{len(tables)})"
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

        name= "Quartierslayout"
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
        
        for i, input_data_table in enumerate(input_data_tables, start=1):
            name = f"Liste der Gebäude ({i}/{len(input_data_tables)})" if len(input_data_tables) > 1 else "Liste der Gebäude"
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
        
        for i, hinweis in enumerate(hinweise, start=1):
            name = f"Allgemeine Hinweise ({i}/{pages_hinweise})" if pages_hinweise > 1 else "Allgemeine Hinweise"
            box = FrameBox(title=name)
            box.set_content(hinweis)
            self.story.append(box)
    
    def create_yearly_bar_charts(self, kpi_data):
        """Creates the yearly stacked bar charts and adds them to the story."""
        costs_data = kpi_data.get("bar_costs_data", [])
        co2_data = kpi_data.get("bar_co2_data", [])
        
        if not costs_data or not co2_data:
            return

        box = FrameBox(title="Jährliche Entwicklung (Kosten & Emissionen)")
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='EnergyhubDevicesFrame')
        avail_w, avail_h = FrameBox.get_available_space_content(frame_width, frame_height)
        
        barcharts_flowable = YearlyStackedBarCharts(costs_data=costs_data, co2_data=co2_data, availWidth=avail_w, availHeight=avail_h)
        box.set_content(barcharts_flowable)
        self.story.append(box)

    def add_standard_spacer(self, size:str='medium'):
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
        super().__init__(filename, pagesize=self.pagesize, leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0, **kwargs)
        
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
            width - 2*margin_x, 
            height - 2*margin_y - footer_height - footer_spacing,  # Reduzierte Höhe
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, 
            id='TitleContentFrame'
        )
        
        title_footer_frame = Frame(
            margin_x, 
            margin_y,  # Footer ganz unten
            width - 2*margin_x, 
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
            width - 2*margin_x, height - 2*margin_y, 
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, 
            id='EnergyhubDevicesFrame'
        )
        energyhub_template = PageTemplate(id=page_id, frames=[energyhub_frame], onPage=self.draw_energyhub_devices_page, pagesize=self.pagesize)

        # Input Data Page (Landscape)
        page_id = 'InputDataPage'
        margin_x, margin_y = self.page_margins[page_id]

        input_data_frame = Frame(
            margin_x, margin_y, 
            landscape_pagesize[0] - 2*margin_x, landscape_pagesize[1] - 2*margin_y, 
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, 
            id='InputDataFrame'
        )
        input_data_template = PageTemplate(id=page_id, frames=[input_data_frame], onPage=self.draw_input_data_page, pagesize=landscape_pagesize)

        # Additional Information Page
        page_id = 'AdditionalInformationPage'
        margin_x, margin_y = self.page_margins[page_id]

        additional_info_frame = Frame(
            margin_x, margin_y, 
            width - 2*margin_x, height - 2*margin_y, 
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, 
            id='AdditionalInformationFrame'
        )
        additional_info_template = PageTemplate(id=page_id, frames=[additional_info_frame], onPage=self.draw_additional_information_page, pagesize=self.pagesize)

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

        margins = self.style.get_page_margins()
        margin_x, margin_y = self.page_margins[page_id]
        
        canvas.setFont(self.style.get_font(bold=False), self.style.get_font_size('page_number'))
        canvas.setFillColorRGB(*self.style.get_color('text_light'))
        
        canvas.drawRightString(width - margin_x, margin_y - 20, f"Seite {doc.page}")
        canvas.restoreState()

    def get_Framesize(self, id:str):
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

        # Apply the pre-configured TableStyle directly
        self.table_style = self.style.get_table_styles()[self.style_name]
        self.table.setStyle(self.table_style)

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

            table_data = [header] + fitting_rows_df.values.tolist()
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

            fitting_rows, overspill_rows = test_input_data.get_rows_that_fit(availWidth=availWidth, availHeight=availHeight)

            if fitting_rows.empty and not overspill_rows.empty:
                raise Exception(f"A single row does not fit into the available height. Decrease the needed height. Current available height: {str(availHeight)} and current available width: {str(availWidth)}")
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

class DataExtractor:
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
        self.report_config = data.report_config
        self.kpis = kpis
        self.building_stats = {}
        self.gebaude_df = None # -> Replaced by a pd.DataFrame later
        self.kennwerte = None
        self.optimization_results = None
        self.district_structure = None
        self.energyhub_df = None
        self.decentral_df = None
        self.district_layout = None

        

        # Building features to be included in the gebaude_df and the keys to extract the data from buildingFeatures
        self.mapping_building_list = OrderedDict([ # key: display name value: data key to extract value from buildingFeatures
            ("Gebäudetyp", "building"),
            ("Baujahr", "year"),
            ("Sanierung", "retrofit"),
            ("Sp-Masse", "construction_type"),
            ("N-Absenkung", "night_setback"),
            ("NRF", "area"),
            ("Heizung", "heater"),
            ("EV", "EV"),
            ("fTES", "f_TES"),
            ("fBAT", "f_BAT"),
            ("fPV1", "f_PV1"),
            ("fPV2", "f_PV2"),
            ("fSTC", "f_STC"),
            ("gammaPV", "gamma_PV"),
            ("EV Charging", "ev_charging")
        ])

        self._extract_data()

    def _get_year_category(self, year:int) -> str:
        """
        Returns the building year category as a string based on the given year.
        Args:
            year: Building year as an integer
        Returns:
            Building year category as a string
        """
        if year < 1968: return "vor 1968"
        if 1968 <= year <= 1978: return "1968-1978"
        if 1979 <= year <= 1983: return "1979-1983"
        if 1984 <= year <= 1994: return "1984-1994"
        if 1995 <= year <= 2001: return "1995-2001"
        if 2002 <= year <= 2009: return "2002-2009"
        if 2010 <= year <= 2015: return "2010-2015"
        return "ab 2016"
    
    def _process_buildings(self):
        """
        Processes the building data and populates the building_stats and list_of_buildings attributes.
        """
        template_dict = OrderedDict([
            ("Anzahl", 0), ("Gesamtfläche", 0), ("vor 1968", 0),
            ("1968-1978", 0), ("1979-1983", 0), ("1984-1994", 0),
            ("1995-2001", 0), ("2002-2009", 0), ("2010-2015", 0),
            ("ab 2016", 0)
        ])

        building_types = ['SFH', 'TH', 'MFH', 'AB', 'OB', 'SC', 'GS', 'RE', "UNI", "HOSPITAL", "CULTURE", "SPORT", "RETAIL", "WORKSHOP", "MIXED"]
        
        self.building_stats = {b_type: template_dict.copy() for b_type in building_types}
        building_data_list = []
        for idx, building in enumerate(self.data.district):
            features = building["buildingFeatures"]
            b_type = features["building"]
            stat_type = "MIXED" if "+" in b_type else b_type

            if stat_type in self.building_stats:
                # Update building statistics by this building
                self.building_stats[stat_type]["Anzahl"] += 1
                self.building_stats[stat_type]["Gesamtfläche"] += features["area"]
                year_category = self._get_year_category(features["year"])
                self.building_stats[stat_type][year_category] += features["area"]

            building_dict = {}
            building_dict["Gebäude ID"] = features["id"]

            # Add to the dictionary from the mapping
            building_dict.update({
                display_name: features.get(data_key)
                for display_name, data_key in self.mapping_building_list.items()
            })

            # manual adjustments: 
            if features.get("heater") == "heat_grid":
                building_dict["fTES"] = 0 # if building is connected to heat grid, no local TES even if otherwise specified

            # Add dictionary to the list
            building_data_list.append(building_dict)

        self.gebaude_df = pd.DataFrame(building_data_list)

        # TODO: Maybe add here dtype casting e.g. ensure area is integer not float ....
    
    def _extract_kennwerte(self):
        """Extracts the general key performance indicators."""
        years = self.kpis.inputData["simulated_years"]
        obs_time = self.data.ecoData["observation_time"]
        to_kW = 1000 # Convert W to kW for power values
        to_MWh = 1000000 # Convert W to MWh for energy values

        # Prepare Data -> # TODO: Move to KPIs class
        avg_autonomy = sum(self.kpis.energy_autonomy_year[y] for y in years) / len(years)
        avg_scf = sum(self.kpis.scf_year[y] for y in years) / len(years)
        avg_dcf = sum(self.kpis.dcf_year[y] for y in years) / len(years)

        

        # Overall_summary
        self.district_key_kpis = [
            ["Nutzenergiebedarf:", f"{round((self.kpis.total_heating_demand + self.kpis.total_cooling_demand + self.kpis.total_electricity_demand + self.kpis.total_dhw_demand + self.kpis.total_EV_demand) / to_MWh, 1)} MWh/a"],
            ["Norm-Heizlast", f"{round(self.kpis.totalheatload / to_kW, 1)} kW"],
        ]

        self.district_operation_kpis = [
            ["Ø CO2-Emissionen:", f"{round(self.kpis.avg_co2_emissions, 2)} t/a"],
            ["Ø Energiekosten:", f"{round(self.kpis.avg_operationCosts, 0)} €/a"],
            ["Anlagenkosten Zentral:", f"{round(self.kpis.annual_fixed_costs_central, 0)} €/a"],
            ["Anlagenkosten Dezentral:", f"{round(self.kpis.annual_fixed_costs_decentral, 0)} €/a"],
            ["Spitzenlast (el.):", f"{round(max(self.kpis.peakDemand.values()), 1)} kW"],
            ["Max. Einspeiseleistung:", f"{round(max(self.kpis.peakInjection.values()), 1)} kW"],
            ["Autarkiegrad:", f"{round(avg_autonomy * 100, 1)} %"],
            ["Supply-Cover Ratio:", f"{round(avg_scf * 100, 1)} %"],
            ["Demand-Cover Ratio:", f"{round(avg_dcf * 100, 1)} %"],
            # ["Elektifizierungsquote Wärme", f"{round(self.kpis.elec_quote_heat * 100, 1)} %"], # Not currently implemented -> Maybe add later
            # ["Elektrifizierungsquote Fahrzeuge:", f"{round(self.kpis.elec_quote_vehicles * 100, 1)} %"]  # Not currently implemented -> Maybe add later
        ]

        # max loads in kW
        self.max_loads_table = [
            ["Wärme:", f"{int(round(self.kpis.total_heat_peak / to_kW))} kW"],
            ["Strom:", f"{int(round(self.kpis.total_electricity_peak / to_kW))} kW"],
            ["TWW:", f"{int(round(self.kpis.total_dhw_peak / to_kW))} kW"],
            ["Kälte:", f"{int(round(self.kpis.total_cooling_peak / to_kW))} kW"]
        ]

        # energy demand in MWh/a
        self.pie_chart_energy = {
            "Strom": round(self.kpis.total_electricity_demand / to_MWh, 2),
            "Wärme": round(self.kpis.total_heating_demand / to_MWh, 2),
            "TWW": round(self.kpis.total_dhw_demand / to_MWh, 2),
            "Kälte": round(self.kpis.total_cooling_demand / to_MWh, 2),
            "EV": round(self.kpis.total_EV_demand / to_MWh, 2)
        }
        
        # Bar charts:
        self.bar_costs_data = []
        self.bar_co2_data = []
        
        for y in years:
            # Fetch cost breakdown
            costs = self.kpis.detailed_costs_year[y]
            self.bar_costs_data.append({
                "Year": y,
                "Anlagenkosten zentral": round(costs["eh_fixed"], 0),
                "Anlagenkosten dezentral": round(costs["decentral_fixed"], 0),
                "Strom": round(costs["electricity"], 0),
                "Gas": round(costs["gas"], 0),
                "Öl": round(costs["oil"], 0),
                "Abfall": round(costs["waste"], 0),
                "Biomasse": round(costs["biomass"], 0),
                "Fernwärme": round(costs["district_heat"], 0),
                "Wasserstoff": round(costs["hydrogen"], 0),
                "Einspeiseerlöse (el.)": round(costs["revenue_feed_in_el"], 0)
            })

            # Fetch CO2 breakdown
            em = self.kpis.co2emissions[y]
            self.bar_co2_data.append({
                "Year": y,
                "Strom": round(em["co2_dem_grid"], 2),
                "Gas": round(em["co2_gas"], 2),
                "Öl": round(em["co2_oil"], 2),
                "Abfall": round(em["co2_waste"], 2),
                "Biomasse": round(em["co2_biom"], 2),
                "Fernwärme": round(em["co2_district_heat"], 2),
                "Wasserstoff": round(em["co2_hydrogen"], 2)
            })

            # Maybe later add also the development of the energy demand over the years as a stacked bar if renovation measures or other changes are implemented in the multi-year simulation.

            self.kennwerte = {
            "district_key_kpis": self.district_key_kpis,
            "district_operation_kpis": self.district_operation_kpis,
            "max_loads_table": self.max_loads_table,
            "pie_chart_energy": self.pie_chart_energy,
            "bar_costs_data": self.bar_costs_data,
            "bar_co2_data": self.bar_co2_data
            }

    def _extract_district_structure(self):
        """Extracts the structural information of the district and prepares tables."""
        res_types = {'SFH', 'TH', 'MFH', 'AB'}
        mixed_types = {'MIXED'}

        ghd_types = {'OB', 'SC', 'GS', 'RE', 'UNI', 'HOSPITAL', 'CULTURE', 'SPORT', 'RETAIL', 'WORKSHOP'} # DO not use  -> Use all that are not residential or mixed as GHD

        first_b_type = list(self.building_stats.keys())[0]
        all_keys = list(self.building_stats[first_b_type].keys())
        age_classes = all_keys[2:] # Change to actively exclude Anzahl and Gesamtfläche instead of relying on the order

        agg_stats = {
            "Wohngebäude": {"Anzahl": 0, "Gesamtfläche": 0},
            "Mischgebäude": {"Anzahl": 0, "Gesamtfläche": 0},
            "GHD-Gebäude": {"Anzahl": 0, "Gesamtfläche": 0}
        }
        for cat in agg_stats:
            for age in age_classes:
                agg_stats[cat][age] = 0

        details_rows = []

        # Build the aggregated stats and the details rows at the same time by iterating through the building types only once
        for b_type, stats in self.building_stats.items():
            
            # Map to main category
            if b_type in res_types:
                cat = "Wohngebäude"
            elif b_type in mixed_types:
                cat = "Mischgebäude"
            else:
                cat = "GHD-Gebäude"

            # Sum up for the compact table
            agg_stats[cat]["Anzahl"] += stats["Anzahl"]
            agg_stats[cat]["Gesamtfläche"] += stats["Gesamtfläche"]
            for age in age_classes:
                agg_stats[cat][age] += stats[age]

            # Detailed row for the landscape page - ALWAYS appended
            translated_name = self._translate_building_type(b_type)
            detail_row = {
                "Gebäudetyp": translated_name,
                "Anzahl": stats["Anzahl"] if stats["Anzahl"] > 0 else "-"            
                }
            for age in age_classes:
                detail_row[age] = f"{round(stats[age])} m²" if stats[age] > 0 else "-"
            details_rows.append(detail_row)

        # Summary Table displayed on the first page
        summary_table_data = [
            ["", "Wohngebäude", "Mischgebäude", "GHD-Gebäude"],
            ["Anzahl", 
             str(agg_stats["Wohngebäude"]["Anzahl"]) if agg_stats["Wohngebäude"]["Anzahl"] > 0 else "-", 
             str(agg_stats["Mischgebäude"]["Anzahl"]) if agg_stats["Mischgebäude"]["Anzahl"] > 0 else "-", 
             str(agg_stats["GHD-Gebäude"]["Anzahl"]) if agg_stats["GHD-Gebäude"]["Anzahl"] > 0 else "-"],
            ["Gesamtfläche", 
             f"{round(agg_stats['Wohngebäude']['Gesamtfläche'])} m²" if agg_stats["Wohngebäude"]["Gesamtfläche"] > 0 else "-", 
             f"{round(agg_stats['Mischgebäude']['Gesamtfläche'])} m²" if agg_stats["Mischgebäude"]["Gesamtfläche"] > 0 else "-", 
             f"{round(agg_stats['GHD-Gebäude']['Gesamtfläche'])} m²" if agg_stats["GHD-Gebäude"]["Gesamtfläche"] > 0 else "-"]
        ]
        for age in age_classes:
            w_area = agg_stats["Wohngebäude"][age]
            m_area = agg_stats["Mischgebäude"][age]
            g_area = agg_stats["GHD-Gebäude"][age]
            
            summary_table_data.append([
                age,
                f"{round(w_area)} m²" if w_area > 0 else "-",
                f"{round(m_area)} m²" if m_area > 0 else "-",
                f"{round(g_area)} m²" if g_area > 0 else "-"
            ])

        # General info to be displayed below the summary table on the first page
        general_info = [
            ["Wohneinheiten im Quartier", str(self.kpis.totalnumberflats)],
            ["Bewohner des Quartiers", str(self.kpis.totalnumberocc)],
            ["Standort (PLZ)", str(self.data.site["zip"])],
            ["Testreferenzjahr", f"{str(self.data.site['TRYYear'])[3:]} / {self.data.site['TRYType']}"]
        ]

        # 4. Pack everything into the final structure
        self.district_structure = {
            "summary_table": summary_table_data,
            "general_info": general_info,
            "df_details": pd.DataFrame(details_rows)
        }
        
    def _translate_building_type(self, b_type:str) -> str:
        """Translates the building type from the data to the display name."""

        if self.get_language() == "en":
            raise NotImplementedError(f"Language {self.get_language()} not supported for building type translation.")

        elif self.get_language() == "de":
            translation_map = {
                "SFH": "Einfamilienhaus",
                "TH": "Reihenhaus",
                "MFH": "Mehrfamilienhaus",
                "AB": "Apartmentblock",
                "OB": "Bürogebäude",
                "SC": "Schulgebäude",
                "GS": "Lebensmittelgeschäft",
                "RE": "Restaurantgebäude",
                "UNI": "Universitätsgebäude",
                "HOSPITAL": "Krankenhausgebäude",
                "CULTURE": "Kulturgebäude",
                "SPORT": "Sportgebäude",
                "RETAIL": "Handelsgebäude",
                "WORKSHOP": "Werkstattgebäude",
                "MIXED": "Mischgebäude"
            }
        
        else: raise NotImplementedError(f"Language {self.get_language()} not supported for building type translation.")
        
        return translation_map.get(b_type, b_type) # if no translation is found, return the original type

    def _extract_energyhub_data(self):
        """Extracts the energyhub data for central devices."""
        try:
            capacities = self.data.centralDevices["capacities"]
            central_configs = self.data.central_device_data
            lang = self.get_language()

            if lang == "en":
                col_device = "Device"
                col_capacity = "Capacity"
                col_cost = "Ann. Cost (Sub.)"
                not_selected_text = "not selected"
            elif lang == "de":
                col_device = "Anlage"
                col_capacity = "Kapazität"
                col_cost = "Anlagenkosten (subv.)"
                not_selected_text = "nicht ausgewählt"
            else:
                raise NotImplementedError(f"Language {lang} not supported for energy hub device table.")

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

                if dev == "AirHP" or dev == "GroundHP":
                    opt_key = "HP"
                elif dev == "AirCC":
                    opt_key = "CC"
                else:
                    opt_key = dev
                
                cap = 0
                annual_cost_sub = "-"
                annual_cost_unsub = "-"

                if opt_key in capacities:
                    spec = capacities[opt_key]
                    # Strict access: if spec is a dict, it MUST have 'cap'
                    cap = round(spec["cap"], 2)
                
                    if opt_key in self.kpis.central_individual_devices_annualized_cost:
                        device_cost_info = self.kpis.central_individual_devices_annualized_cost[opt_key]
                        annual_cost_sub = round(device_cost_info["subsidized_annual_cost"], 2)
                        annual_cost_unsub = round(device_cost_info["unsubsidized_annual_cost"], 2)
                        all_cost_devices.discard(opt_key) # Remove this device from the set of devices as it has been processed


                # Get the device name and unit
                name, base_unit = self.get_central_device_name(dev)

                display_cap, display_unit = self._determine_unit(cap=cap,base_unit= base_unit)

                if cap <= 0:
                    display_cap = not_selected_text

                # Append dict to the device list
                append_energyhub_row(
                    device_name=name,
                    capacity=f"{display_cap} {display_unit}".strip(),
                    annual_cost=f"{annual_cost_sub} €/a"
                )

            # Add all devices that are in the cost breakdown but not in the feasible central device data
            for dev in all_cost_devices:
                cost = round(self.kpis.central_individual_devices_annualized_cost[dev]['subsidized_annual_cost'], 2)
                if cost == 0:
                    continue # Skip devices that have zero cost

                name, base_unit = self.get_central_device_name(dev)
                cap = 0
                display_cap, display_unit = self._determine_unit(cap=cap, base_unit=base_unit)

                if display_cap <= 0:
                    display_cap = "-"

                append_energyhub_row(
                    device_name=name,
                    capacity=f"{display_cap} {display_unit}".strip(),
                    annual_cost=f"{cost} €/a"
                )

            # Create the DataFrame only if devices are present
            if device_list:
                self.energyhub_df = pd.DataFrame(device_list)
            else:
                self.energyhub_df = None


        except (KeyError, AttributeError) as e:
            # If no central devices are defined, set energyhub_df to None
            if "capacities" not in self.data.centralDevices: # if truly no central devices are defined
                self.energyhub_df = None
            else: 
                raise Exception(f"Error extracting energyhub data. Please check the structure of centralDevices and central_device_data in the input data.\n Caused error: {e}")

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

                total_cap_adjusted, total_unit_adjusted = self._determine_unit(cap=data['total_cap'], base_unit=base_unit)
                total_power = f"{total_cap_adjusted} {total_unit_adjusted}".strip()
                ann_cost = f"{round(data['total_cost'], 2)} €/a"    
                    
                if self.get_language() == "en":
                    device_list.append({
                        "Device": name,
                        "Count": data["count"],
                        "Total Capacity": total_power,
                        "Annual Costs": ann_cost
                    })
                elif self.get_language() == "de":
                    device_list.append({
                        "Anlage": name,
                        "Anzahl": data["count"],
                        "Gesamtkapazität": total_power,
                        "Anlagenkosten": ann_cost
                    })
                else:
                    raise NotImplementedError(f"Language {self.get_language()} not supported for decentral device table.")

            # 3. Create the DataFrame
            if device_list:
                self.decentral_df = pd.DataFrame(device_list)
            else:
                self.decentral_df = None

        except AttributeError as e:
            print(f"Warning: Decentral device data could not be extracted. {e}")
            self.decentral_df = None

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
            if "position" in features and isinstance(features["position"], (tuple, list)) and len(features["position"]) >= 2:
                pos = features["position"]
                
                # Check for installed devices (capacity > 0)
                installed_devices = []
                if "capacities" in building:
                    for device_name, cap in building["capacities"].items():
                        # Kapazitäten können als Dict {"cap": X} oder direkt als Zahl vorliegen
                        if isinstance(cap, dict) and "cap" in cap and float(cap["cap"]) > 0:
                            installed_devices.append(device_name)
                        elif isinstance(cap, (int, float)) and float(cap) > 0:
                            installed_devices.append(device_name)
                
                # Wenn der heater fest in den Features definiert ist und nicht in capacities steht, fügen wir ihn hinzu
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

    def _extract_data(self):
        """Extracts and processes all necessary data for the certificate."""
        self._process_buildings()
        self._extract_kennwerte()
        self._extract_district_structure()
        self._extract_energyhub_data()
        self._extract_decentral_data()
        self._extract_district_layout()
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
        # TODO: Check translations and full names (en & de)
        if self.get_language() == "en":
            device_name_map = {
                "PV": "Solar Panels",
                "WT": "Wind Turbine",
                "WAT": "Water Turbine",
                "STC": "Solar Thermal Collector",
                "CHP": "Combined Heat & Power",
                "AirHP": "Air-source Heat Pump",
                "GroundHP": "Ground-source Heat Pump",
                "HP": "Heat Pump",
                "BOI": "Boiler",
                "GHP": "Gas Heat Pump",
                "EB": "Electric Boiler",
                "AC": "Absorption Chiller",
                "BCHP": "Biogas CHP",
                "BBOI": "Biogas Boiler",
                "WCHP": "Waste Heat CHP",
                "WBOI": "Waste Heat Boiler",
                "ELYZ": "Electrolyzer",
                "FC": "Fuel Cell",
                "H2S": "Hydrogen Storage",
                "SAB": "Sabatier Reactor",
                "TES": "Heat Storage",
                "CTES": "Cold Storage",
                "BAT": "Battery",
                "GS": "Gas Storage",
                "AirCC": "Air-cooled Chiller",
                "CC": "Cooling Chiller",
                "Heat_Grid": "Local Heat Grid"
            }
        elif self.get_language() == "de":
            device_name_map = {
                "PV": "Photovoltaik",
                "WT": "Windkraftanlage",
                "WAT": "Wasserkraftanlage",
                "STC": "Solarthermie",
                "CHP": "Blockheizkraftwerk",
                "AirHP": "Luftwärmepumpe",
                "GroundHP": "Erdwärmepumpe",
                "HP": "Wärmepumpe",
                "BOI": "Heizkessel",
                "GHP": "Gaswärmepumpe",
                "EB": "Elektrokessel",
                "AC": "Absorpt.-Kältemaschine",
                "BCHP": "Biogas-BHKW",
                "BBOI": "Biogaskessel",
                "WCHP": "Abfall-BHKW",
                "WBOI": "Abfall-Wärmekessel",
                "ELYZ": "Elektrolyseur",
                "FC": "Brennstoffzelle",
                "H2S": "Wasserstoffspeicher",
                "SAB": "Sabatier-Reaktor",
                "TES": "Wärmespeicher",
                "CTES": "Kältespeicher",
                "BAT": "Batteriespeicher",
                "GS": "Gasspeicher",
                "AirCC": "Luftgekühlte Kältemaschine",
                "CC": "Kompr.-Kältemaschine",
                "Heat_Grid": "Nahwärmenetz"
            }
        
        else: raise NotImplementedError(f"Language {self.get_language()} not supported for device name translation.")


        device_unit_map = { # If not specified, default is "W"
            "H2S": "Wh",
            "TES": "Wh",
            "CTES": "Wh",
            "BAT": "Wh",
            "GS": "Wh"
        }

        name = device_name_map[dev]
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
        # TODO: Check translations and full names (en & de)
        if self.get_language() == "en":

            device_name_map = {
                # Heat & Power
                "HP": "Heat Pump",
                "EH": "Electric Heater",
                "CHP": "Combined Heat & Power",
                "BOI": "Boiler",
                "BBOI": "Biogas Boiler",
                "OBOI": "Oil Boiler",
                "H2BOI": "Hydrogen Boiler",
                "FC": "Fuel Cell",
                "heat_grid": "Local Heat Grid",
                "PV": "Photovoltaic",
                "STC": "Solar Thermal Collector",
                "EV": "Electric Vehicle",

                # Cooling
                "CC": "Compression Chiller",

                # Storage
                "BAT": "Battery Storage",
                "TES": "Heat Storage",
                "EV": "Electric Vehicle",

                # Special Modes of the Heat Pump supply temperature
                "HP35": "Heat Pump (35°C)",
                "HP55": "Heat Pump (55°C)",
            }
        
        elif self.get_language() == "de":
            device_name_map = {
                # Heat & Power
                "HP": "Wärmepumpe",
                "EH": "Heizstab",
                "CHP": "Blockheizkraftwerk",
                "BOI": "Heizkessel",
                "BBOI": "Biogas-Heizkessel",
                "OBOI": "Öl-Heizkessel",
                "H2BOI": "Wasserstoff-Heizkessel",
                "FC": "Brennstoffzelle",
                "heat_grid": "Nahwärmenetz",
                "PV": "Photovoltaik",
                "STC": "Solarthermie",
                "EV": "Elektrofahrzeug",

                # Cooling
                "CC": "Kompr.-Kältemaschine",

                # Storage
                 "BAT": "Batteriespeicher",
                "TES": "Wärmespeicher",
                "EV": "Elektrofahrzeug",

                # Special Modes of the Heat Pump supply temperature
                "HP35": "Wärmepumpe (35°C)",
                "HP55": "Wärmepumpe (55°C)",
            }
        else: raise NotImplementedError(f"Language {self.get_language()} not supported for device name translation.")

        device_unit_map = {  # If not specified, default is "W"
            "BAT": "Wh",
            "TES": "Wh",
            "EV": "Wh",
            "STC": "m²",
            "PV": "m²"
        }

        # All devices
        name = device_name_map.get(dev, dev)
        base_unit = device_unit_map.get(dev, "W")
        return name, base_unit

    @staticmethod
    def _determine_unit(cap: float, base_unit: str) -> tuple[float, str]:
        """
        Determines the appropriate unit (kW, MW, kWh, MWh) based on the capacity value and the base unit. Input cap is expected to be in kW or kWh.

        Args:
            cap (float): The capacity value.
            base_unit (str): The base unit ("W" or "Wh", "kW", "kWh"). Can deal with "m²" as well for area devices

        Returns:
            tuple[float, str]: A tuple containing the adjusted capacity and the appropriate unit.
        """

        if base_unit == "m²":
            if cap <= 0:
                adjusted_cap = cap
                adjusted_unit = ""  # No prefix for zero or negative values
            elif cap >= 10000:
                adjusted_cap = round(cap / 10000, 2)
                adjusted_unit = "ha"  # Hektar for large areas
            else:
                adjusted_cap = round(cap, 2)
                adjusted_unit = base_unit
        elif cap <= 0:
            adjusted_cap = cap
            adjusted_unit = ""  # No prefix for zero or negative values
        elif cap >= 1000000:
            adjusted_cap = round(cap / 1000000, 2)
            adjusted_unit = "G" + base_unit  # Giga
        elif cap >= 1000:
            adjusted_cap = round(cap / 1000, 2)
            adjusted_unit = "M" + base_unit  # Mega
        elif cap >= 1:
            adjusted_cap = round(cap, 2)
            adjusted_unit = "k" + base_unit  # Kilo
        else:
            adjusted_cap = round(cap * 1000, 2)
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
    
    def get_district_layout(self):
        return self.district_layout

    def get_scenario_name(self):
        return self.data.scenario_name
    
    def get_language(self):
        return self.data.report_config["language"]

################################################################################
# Certificate Builder
################################################################################

class CertificateBuilder(ReportComponent):
    """
    This class orchestrates the certificate creation by setting up data, theme, initializing the PDF template, and building the story.
    """

    def __init__(self, data, kpis, result_path) -> None:
        self.data_object = DataExtractor(data=data, kpis=kpis)
        self.scenario_name = self.data_object.get_scenario_name()
        self.report_config = self.data_object.report_config
        self.language = self.data_object.get_language()

        # Initialize and apply theme globally
        report_theme = ThemeManager(self.report_config)
        ReportComponent.apply_style(report_theme)
        
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

    def get_Framesize(self, id:str):
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