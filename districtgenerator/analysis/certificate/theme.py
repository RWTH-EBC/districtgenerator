"""Colors, fonts, sizes and paragraph and table styles of the certificate."""
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.styles import StyleSheet1, ParagraphStyle
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, Spacer


DEBUG = False # If set to True boxes are drawn around the different components to visualize the layout and available space
debug_line_width = 0.1 # Line width for the debug boxes

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
