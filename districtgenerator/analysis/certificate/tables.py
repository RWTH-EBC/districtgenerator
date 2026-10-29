"""Tables and notes of the certificate."""
from reportlab.lib.styles import StyleSheet1, ParagraphStyle
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, Spacer
import pandas as pd
from districtgenerator.analysis.certificate.components import BaseReportFlowable


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
        self.hinweise_content = self.translate("content_information_page")
        
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
        remaining_sections = list(dummy_instance.hinweise_content.keys()) # all sections that need to be placed

        hinweise = []
        
        while remaining_sections:
            # Create test instance with remaining sections
            test_hinweise = cls(sections_to_include=remaining_sections)
            test_hinweise.width = availWidth
            
            # Determine which sections fit into this box
            sections_that_fit, sections_overflow = test_hinweise.get_sections_that_fit(availHeight)
            
            # Ensure at least one section is processed
            if not sections_that_fit and remaining_sections:
                raise Exception("At least one section of the Hinweise content is too large to fit on one page. Please review the content.")
            
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
        memoized_styles = {} # Cache to avoid creating thousands of duplicate ParagraphStyle objects

        def get_cell_paragraph_style(c, r):
            necessary_attrs = {'f_name': 'FONTNAME', 'f_size': 'FONTSIZE', 'align': 'ALIGN', 't_color': 'TEXTCOLOR'}
            f_name = f_size = align = t_color = None

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
                        if val == 'LEFT': align = 0
                        elif val == 'CENTER': align = 1
                        elif val == 'RIGHT': align = 2
                    elif op == 'TEXTCOLOR':
                        t_color = cmd[3]

            # Check if any of the style attributes were not set by the TableStyle commands and raise exceptions if so as Style is not fully defined:
            for var_name, attr_name in necessary_attrs.items():
                if var_name not in locals():
                    raise ValueError(f"TableStyle is missing necessary '{attr_name}' command for cell ({c}, {r}). All of FONTNAME, FONTSIZE, ALIGN, and TEXTCOLOR must be defined for every cell to ensure consistent styling. Please check the TableStyle configuration.")


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
                    leading=f_size*1.2,
                    leftIndent=0,
                    rightIndent=0,
                    spaceBefore=0,        # Padding defined by the TableStyle not here
                    spaceAfter=0,
                    splitLongWords=0      # prevent forced hyphenation
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
