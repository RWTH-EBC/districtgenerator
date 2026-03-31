# -*- coding: utf-8 -*-

"""
This module contains the classes that are used to generate the certificate layout.

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


"""
Info:

Color Names:
- primary_color
- secondary_color
- background
- text
- text_light
- energy["electricity"], energy["heating"], energy["dhw"], energy["cooling"], energy["ev"]

Font size names:
- title
- section_title
- subsection_title
- highlighted
- body
- small
- table
- dense
- page_number
"""
    
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
                'large': 20,
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

        print(f"Report Config: {self.report_config}") #! DEBUG:

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
        return self.colors[color_type]
    
    def get_font_size(self, font_type:str):
        """Returns the font size for the specified font type."""
        return self.fonts["sizes"][font_type]
    
    def get_font(self, bold:bool=False):
        """Returns the font name based on whether bold is True or False."""
        return self.fonts["bold"] if bold else self.fonts["regular"]
    
    def get_line_width(self, line_type:str):
        """Returns the line width for the specified line type."""
        return self.layout['line_width'][line_type]
    
    def get_spacing(self, spacing_type:str):
        """Returns the spacing for the specified spacing type."""
        return self.layout['spacing'][spacing_type]
    
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
            
            # header row
            ('BACKGROUND', (0, 0), (-1, 0), self.colors["background"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors["text"]),
            ('FONTNAME', (0, 0), (-1, 0), self.fonts["bold"]),
            ('FONTSIZE', (0, 0), (-1, 0), self.fonts["sizes"]["table"]),
            
            # data rows
            ('TEXTCOLOR', (0, 1), (-1, -1), self.colors["text"]),
            ('FONTNAME', (0, 1), (-1, -1), self.fonts["regular"]),
            ('FONTSIZE', (0, 1), (-1, -1), self.fonts["sizes"]["table"]),
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


################################################################################
# Basic Layout is a Framebox around the content
################################################################################

class FrameBox(Flowable, ReportComponent):
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

    def draw(self):
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

class Header(Flowable, ReportComponent):
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
    
    def draw(self):
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

class Energiekennwerte(Flowable, ReportComponent):
    """
    This class generates the Energiekennwerte section of the certificate.
    """
    pass

class Quartiersstruktur(Flowable, ReportComponent):
    """
    This class generates the Quartiersstruktur section of the certificate.
    """
    pass

class Footer(Flowable, ReportComponent):
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

    def draw(self):
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

class InputDataTable(Flowable, ReportComponent):
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

    def get_rows_that_fit(self, availWidth, availHeight):
        """
        Determines which rows of the input data table fit into the available height.
        Returns a tuple of two DataFrames: (fitting_rows, overspill_rows)
        """

        if self.input_data is None or self.input_data.empty:
            return pd.DataFrame(), pd.DataFrame()

        header = self.input_data.columns.tolist()
        num_cols = len(header)
        colWidths = [availWidth / num_cols] * num_cols

        num_data_rows_fit = len(self.input_data)
        # Iteratively reduce estimated number of rows until the real wrapped table
        while num_data_rows_fit > 0:
            # Rows for this iteration
            fitting_rows_df = self.input_data.iloc[:num_data_rows_fit]

            # Create a temporary table to check the wrapped height
            table_data = [header] + fitting_rows_df.values.tolist()
            tmp_table = Table(table_data, colWidths=colWidths)
            tmp_table.setStyle(self.table_style)

            _, wrapped_height = tmp_table.wrap(availWidth, availHeight)

            if wrapped_height <= availHeight:
                break  # Fits within available height
            num_data_rows_fit -= 1

        fitting_rows = self.input_data.iloc[:num_data_rows_fit]
        overspill_rows = self.input_data.iloc[num_data_rows_fit:]

        return fitting_rows, overspill_rows
    
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
    
    def draw(self):
        self.table.drawOn(self.canv, 0, self.height - self.actual_height) #Placement at the top-left corner

    @classmethod
    def create_all_tables(cls, availWidth, availHeight, input_data:pd.DataFrame):
        """
        Creates all input data tables so that the whole content can be displayed.
        The flowables contain all table rows that fit into the available height.
        The overflow rows are placed into the next flowable.
        returns a list of InputDataTable flowables.
        """
        if input_data is None or input_data.empty:
            return []

        flowables = []
        remaining_data = input_data.copy()

        while not remaining_data.empty:
            # Create a new InputDataTable with the remaining data
            test_input_data = cls(input_data=remaining_data)
            test_input_data.width = availWidth # -> Use the whole available width

            # get the rows that fit into the available height and the overspill rows
            fitting_rows, overspill_rows = test_input_data.get_rows_that_fit(availWidth=availWidth, availHeight=availHeight)

            if fitting_rows.empty and not overspill_rows.empty:
                # If no rows fit, but there are overspill rows
                raise Exception(f"A single row does not fit into the available height. Decrease the needed height. Current available height: {str(availHeight)} and current available width: {str(availWidth)}")
            elif not fitting_rows.empty:
                # Create a new InputDataTable with the fitting rows
                table_flowable = cls(input_data=fitting_rows)
                flowables.append(table_flowable)

                # Update the remaining data
                remaining_data = overspill_rows
            else:
                break # No more rows to process

        return flowables

class Hinweise(Flowable, ReportComponent):
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
            "Bezeichnungen in der Liste der Gebäude": 
                {
                    "Gebäude ID": "Gebäudenummer zur Identifizierung",
                    "Gebäudetyp": "SFH = Einfamilienhaus, MFH = Mehrfamilienhaus, TH = Reihenhaus, AB = Wohnblock, OB = Bürogebäude, SC = Schule, GS = Lebensmittelgeschäft, RE = Restaurant, MFH+GR = Mehrfamilienhaus+Lebensmittelgeschäft, AB+GR = Wohnblock+Lebensmittelgeschäft, MFH+RE = Mehrfamilienhaus+Restaurant, AB+RE = Wohnblock+Restaurant",
                    "Baujahr": "Baualtersklasse (vor 1969, 1968-1978, 1979-1983, 1984-1994, 1995-2001, 2002-2009, 2010-2015, ab 2016)",
                    "Sanierung für Wohngebäude": "0 = Bestand, 1 = Sanierung nach EnEV 2016, 2 = Sanierung nach KfW 55",
                    "Sanierung für Nichtwohngebäude": "0 = Nichtsaniert, 1 = Teilsaniert (nur Fenster und Wände), 2 = Vollsaniert (Decke, Fenster, Dach und Wände)",
                    "Sp-Masse": "Gebäudespeichermasse: 0 = Leichtbau, 1 = Mittelbau, 2 = Massivbau",
                    "N-Absenkung": "Nachtabsenkung: 0 = keine Nachtabsenkung, 1 = mit Nachtabsenkung",
                    "Wohnfläche": "Nettoraumfläche in m²",
                    "Heizung": "ausgewählter Wärmeerzeuger",
                    "EV": "Zwischen 0 und 1; Anteil der Elektroautos am Gesamtfahrzeugbestand im Gebäude",
                    "fTES": "Größe des Pufferspeichers in Liter pro kW Heizleistung der Wärmeerzeugungsanlage",
                    "fBAT": "Größe des Batteriespeichers in abhängigkeit der Leistung der PV-Anlage in Wh/W_PV",
                    "fPV1": "Anteil der gesamten Dachfläche, der auf Dachseite 1 mit Photovoltaik belegt ist. Dachseite 1 ist dabei die Seite, für die der Azimutwinkel gammaPV vergegeben wird (Informationen zu Dachflächen sind den Typgebäuden nach Tabula zu entnehmen)",
                    "fPV2": 'Anteil der gesamten Dachfläche, der auf Dachseite 2 mit Photovoltaik belegt ist. Der Azimutwinkel von Dachseite 2 wird als 180° zu gammaPV gedreht ("gegenüberliegend") berechnet.',
                    "fSTC": "Anteil der Dachfläche, die mit Solarthermie ausgestattet ist (Informationen zu Dachflächen sind den Typgebäuden nach Tabula zu entnehmen)",
                    "gammaPV": "Azimut = Himmelsausrichtung von Dachseite 1, Ausrichtung nach Süden entspricht 0°",
                    "EV Charging": "Ladeverhalten des Elektroautos (bi-direktional: Be- und Entladung, Nutzung als Stromspeicher, on-demand: Beladung nach Bedarf, intelligent: optimierte Beladung)"
                },
            
            "Energetische Kennwerte":{
                    "Nutzenergiebedarf": "Über alle Gebäude aufsummierter Nutzenergiebedarf (Haushaltsstrom, Wärme, Trinkwarmwasser, Kälte und EV-Strom)",
                    "Norm-Heizlast": "Über alle Gebäude aufsummierte Norm-Heizlast nach DIN EN ISO 13790",
                    "Energiebedarfe (MWh)": "Über alle Gebäude aufsummierten Jahresenergiebedarfe auf Basis der generierten Bedarfsprofile (für Wärme, Kälte, Haushaltsstrom, Trinkwarmwasser und Elektroautos)",
                    "Maximale Leistungen": "Maximale Leistungen in kW im Quartier auf Basis der aufsummierten Bedarfsprofile aller Gebäude (ohne Betriebsoptimierung)"
                },
            "Optimierter Anlagenbetrieb":{
                    "CO2-äqui. Emissionen": "Im Quartier emittierte CO2-Äquivalente in t/a durch den optimierten Betrieb (Gasbedarf und Strombedarf)",
                    "Energiekosten": "Spezifische Betriebskosten des gesamten Quartiers in €/kWh auf Basis der Betriebsoptimierung",
                    "Fixed Costs": "total fixed, annualized cost of all installed energy assets, including capital expenditures (CAPEX) and fixed operation & maintenance (O&M) costs",
                    "Spitzenlast (el.)": "Maximaler Strombezug des gesamten Quartiers aus übergeordnetem Stromnetz auf Basis der Betriebsoptimierung",
                    "Max. Einspeiseleistung": "Maximale Stromeinspeisung des gesamten Quartiers in übergeordnetes Stromnetz auf Basis der Betriebsoptimierung",
                    "Supply-Cover-Faktor": "Anteil des aus den Gebäuden des Quartiers ins lokale Netz eingespeisten Stroms, der für den Eigenverbrauch innerhalb des Quartiers durch andere Gebäude genutzt wird (Werte zwischen 0 % und 100 %)",
                    "Demand-Cover-Faktor": "Anteil des residualen Strombedarfs im Quartier, der durch den von den Gebäuden im Quartier erzeugten und ins lokale Netz eingespeisten Stroms gedeckt wird (Werte zwischen 0 % und 100 %)",
                    "El-Autonomy-Faktor": "Anteil der Betriebszeit, in der der lokale Strombedarf vollständig durch die Stromerzeugung im Quartier gedeckt wird (Werte zwischen 0 % und 100 %)"
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
                textColor=self.style.get_color('text_light')
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
    
    def draw(self):
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

################################################################################
# Layout generation as a class
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
        # energiekennwerte = Energiekennwerte()
        energiekennwerte = Paragraph("Dies ist ein Platzhalter für die energetischen Kennwerte.", self.paragraph_styles['Normal']) 
        box.set_content(energiekennwerte)
        self.story.append(box)
        self.add_standard_spacer()

    def create_quartiersstruktur(self, data_quartiersstruktur):
        """Creates the Quartiersstruktur section and adds it to the story."""
        box = FrameBox(title="Quartiersstruktur")
        # quartiersstruktur = Quartiersstruktur()
        quartiersstruktur = Paragraph("Dies ist ein Platzhalter für die Quartiersstruktur.", self.paragraph_styles['Normal']) 
        box.set_content(quartiersstruktur)
        self.story.append(box)
        self.add_standard_spacer()

    def create_footer(self, scenario_name):
        """Creates Footer and adds it to the story."""
        footer = Footer(scenario_name)
        self.story.append(footer)

    # Energyhub device capacity page
    def create_energyhub_data(self, data_energyhub):
        """Creates the Energyhub Data section and adds it to the story."""
        # TODO: LOGIC Wise this should move into a seperate class like the Energiekennwerte and Quartiersstruktur!
        box = FrameBox(title="Energyhub-Daten")

        if data_energyhub is None or data_energyhub.empty:
            energyhub_data = Paragraph("Es wurden keine zentralen Energieanlagen ausgelegt", self.paragraph_styles['Normal'])
        else:
            header = data_energyhub.columns.to_list()
            body = data_energyhub.values.tolist()
            table_data = [header] + body

            energyhub_data = Table(table_data)
            table_style = self.style.get_table_styles()['standard']
            energyhub_data.setStyle(table_style)
        
        # Put the content in the FrameBox
        box.set_content(energyhub_data, full_width=True)
        self.story.append(box)
    
    # Input Data page
    def create_input_data_table(self, data_input):
        """Creates the Input Data Table section and adds it to the story."""
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='InputDataFrame')
        input_data_width, input_data_height = FrameBox.get_available_space_content(frame_width, frame_height)
        
        input_data_tables = InputDataTable.create_all_tables(
            availWidth=input_data_width, 
            availHeight=input_data_height, 
            input_data=data_input
        )
        
        for i, input_data_table in enumerate(input_data_tables, start=1):
            box = FrameBox(title=f"Liste der Gebäude ({i}/{len(input_data_tables)})")
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
            box = FrameBox(title=f"Allgemeine Hinweise ({i}/{pages_hinweise})")
            box.set_content(hinweis)
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
            margin_y + footer_height + footer_spacing,  # Startet ÜBER dem Footer
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
        page_id = 'EnergyhubDevicesPage'
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

        

        # Building features to be included in the gebaude_df and the keys to extract the data from buildingFeatures
        self.mapping_building_list = OrderedDict([ # key: display name value: data key to extract value from buildingFeatures
            ("Gebäudetyp", "building"),
            ("Baujahr", "year"),
            ("Sanierung", "retrofit"),
            ("Sp-Masse", "construction_type"),
            ("N-Absenkung", "night_setback"),
            ("Wohnfläche", "area"),
            ("Heizung", "heater"),
            ("EV", "EV"),
            ("fTES", "f_TES"),
            ("fBAT", "f_BAT"),
            ("fPV", "f_PV"),
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

        building_types = ['SFH', 'TH', 'MFH', 'AB', 'OB', 'SC', 'GS', 'RE', 'MFH+GR', 'AB+GR', 'MFH+RE', 'AB+RE']
        
        self.building_stats = {b_type: template_dict.copy() for b_type in building_types}
        building_data_list = []
        for idx, building in enumerate(self.data.district):
            features = building["buildingFeatures"]
            b_type = features["building"]

            if b_type in self.building_stats:
                # Update building statistics by this building
                self.building_stats[b_type]["Anzahl"] += 1
                self.building_stats[b_type]["Gesamtfläche"] += features["area"]
                year_category = self._get_year_category(features["year"])
                self.building_stats[b_type][year_category] += features["area"]

            building_dict = {}
            building_dict["Gebäude ID"] = idx

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
    
    def _extract_kennwerte(self):
        """Extracts the general key performance indicators."""
        self.kennwerte = {
            "Nutzenergiebedarf": f"{round((self.kpis.total_electricity_demand + self.kpis.total_heating_demand + self.kpis.total_cooling_demand + self.kpis.total_dhw_demand + self.kpis.total_EV_demand) / 1000000, 1)} MWh/a",
            "Norm-Heizlast": f"{round(self.kpis.totalheatload / 1000)} kW",
            "Bedarfe": (
                round(self.kpis.total_electricity_demand / 1000000, 2),
                round(self.kpis.total_heating_demand / 1000000, 2),
                round(self.kpis.total_dhw_demand / 1000000, 2),
                round(self.kpis.total_cooling_demand / 1000000, 2),
                round(self.kpis.total_EV_demand / 1000000, 2)
            ),
            "Max. Leistungen": (
                round(self.kpis.total_electricity_peak / 1000),
                round(self.kpis.total_heat_peak / 1000),
                round(self.kpis.total_dhw_peak / 1000),
                round(self.kpis.total_cooling_peak / 1000)
            )
        }

    def _extract_optimization_results(self):
        """Extracts the results from the operational optimization."""
        years = self.kpis.inputData["simulated_years"]

        self.optimization_results = {
            "CO2-äqui. Emissionen": {year: f"{round(self.kpis.co2emissions[year]['total_co2'])} t/a" for year in years},
            "Energiekosten": {year: f"{round(self.kpis.operationCosts[year])} €/a" for year in years},
            "Decentral Fixed Costs": f"{round(self.kpis.annual_fixed_costs_decentral)} €/a",
            "Central Fixed Costs": f"{round(self.kpis.annual_fixed_costs_central)} €/a",
            "Spitzenlast (el.)": {year: f"{round(self.kpis.peakDemand[year], 2)} kW" for year in years},
            "Max. Einspeiseleistung": {year: f"{round(self.kpis.peakInjection[year], 2)} kW" for year in years},
            "Supply-Cover-Faktor": {year: f"{round(self.kpis.scf_year[year] * 100, 0)} %" for year in years},
            "Demand-Cover-Faktor": {year: f"{round(self.kpis.dcf_year[year] * 100, 0)} %" for year in years},
            "El-Autonomy-Faktor": {year: f"{round(self.kpis.energy_autonomy_year[year] * 100, 0)} %" for year in years}
        }

    def _extract_district_structure(self):
        """Extracts the structural information of the district."""
        self.district_structure = {
            "EFH": self.building_stats['SFH'],
            "MFH": self.building_stats['MFH'],
            "Reihenhaus": self.building_stats['TH'],
            "Block": self.building_stats['AB'],
            "Wohneinheiten gesamt": self.kpis.totalnumberflats,
            "Bewohner gesamt": self.kpis.totalnumberocc,
            "Nettowohnfläche gesamt": f"{self.kpis.totalarea_residential} m²",
            "Nettofläche GHD gesamt": f"{self.kpis.totalarea_non_residential} m²",
            "Standort (PLZ)": str(self.data.site["zip"]),
            "Testreferenzjahr": f"{str(self.data.site['TRYYear'])[3:]} / {self.data.site['TRYType']}",
            "Quartiersname": str(self.data.scenario_name)
        }

    def _extract_energyhub_data(self): # TODO: Add here that all feasible devices are included
        """Extracts the energyhub data for central devices."""
        try:
            capacities = self.data.centralDevices["capacities"]
            central_configs = self.data.central_device_data
            
            device_list = []

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
                
                cap = 0.0
                annual_cost_sub = "-"
                annual_cost_unsub = "-"

                if opt_key in capacities:
                    spec = capacities[opt_key]
                    # Strict access: if spec is a dict, it MUST have 'cap'
                    cap = spec["cap"]
                
                    if opt_key in self.kpis.central_individual_devices_annualized_cost:
                        device_cost_info = self.kpis.central_individual_devices_annualized_cost[opt_key]
                        # Direct access: crash if cost keys are missing
                        annual_cost_sub = round(device_cost_info["subsidized_annual_cost"], 2)
                        annual_cost_unsub = round(device_cost_info["unsubsidized_annual_cost"], 2)

                # Get the device name and unit
                name, unit = self.get_central_device_name(dev)
                # Append dict to the device list
                device_list.append({
                    "Device": name, 
                    "Capacity": f"{cap:.2f} {unit}",
                    "Ann. Cost (Sub.)": f"{annual_cost_sub} €/a"#,
                    # "Ann. Cost (Unsub.)": f"{annual_cost_unsub} €/a"
                })

            # Create the DataFrame only if devices are present
            if device_list:
                self.energyhub_df = pd.DataFrame(device_list)
            else:
                self.energyhub_df = None


        except (KeyError, AttributeError) as e:
            # If no central devices are defined, set energyhub_df to None
            if self.data.centralDevices is None: # if truly no central devices are defined
                self.energyhub_df = None
            else: 
                raise Exception(f"Error extracting energyhub data. Please check the structure of centralDevices and central_device_data in the input data.\n Caused error: {e}")

    def _extract_data(self):
        """Extracts and processes all necessary data for the certificate."""
        self._process_buildings()
        self._extract_kennwerte()
        self._extract_optimization_results()
        self._extract_district_structure()
        self._extract_energyhub_data()
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
            "CC": "Cooling Chiller"
        }

        device_unit_map = { # If not specified, default is "kW"
            "H2S": "kWh",
            "TES": "kWh",
            "CTES": "kWh",
            "BAT": "kWh",
            "GS": "kWh"
        }

        name = device_name_map[dev]
        unit = device_unit_map.get(dev, "kW")

        return name, unit
    
    def get_decentral_device_name(self, dev: str) -> tuple[str, str]:
        """
        Returns the decentral device name and unit based on the device key.
        Args:
            dev (str): device key (e.g. "HP", "PV", "OBOI").
        Returns:
            tuple[str, str]: A tuple consisting of the full name and the unit.
        """

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
            "heat_grid": "Local District Heating",
            "PV": "Solar Panels (PV)",
            "STC": "Solar Thermal Collector",

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

        device_unit_map = {  # If not specified, default is "kW"
            "BAT": "kWh",
            "TES": "kWh",
            "EV": "kWh",
        }

        # All devices
        name = device_name_map.get(dev, dev)
        unit = device_unit_map.get(dev, "kW")
        return name, unit

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

    def get_scenario_name(self):
        return self.data.scenario_name

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
            "EnergyhubDevicesPage": (margins['x'], margins['y']),
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
        
        story.append(NextPageTemplate('EnergyhubDevicesPage'))
        story.append(PageBreak()) 

        self.layout.create_energyhub_data(data_energyhub=self.data_object.get_energyhub_df())
        story.extend(self.layout.get_story())
        self.layout.reset_story()        

        story.append(NextPageTemplate('InputDataPage'))
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