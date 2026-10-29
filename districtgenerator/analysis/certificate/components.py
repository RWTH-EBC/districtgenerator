"""Base classes for all certificate elements."""
import json
from reportlab.lib import colors
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, Spacer
import os
from reportlab.platypus import Flowable
from districtgenerator.utilities.paths import PACKAGE_DIR
from districtgenerator.analysis.certificate.theme import DEBUG, ThemeManager, debug_line_width


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
        srcPath = PACKAGE_DIR
        translations_path = os.path.join(srcPath, "data", "report_translations.json")
        cls.__load_translations(translations_path, language)
    
    @classmethod
    def get_style(cls):
        """
        Returns the theme manager to access the styles. Can be used in all components after the theme has been set.
        """
        if cls.style is None:
            raise Exception("Theme not set. Please call ReportComponent.apply_style(theme_manager) before creating any components.")
        return cls.style
    
    @classmethod
    def translate(cls, text_key: str) -> str|dict:
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
        gap = 5             # small gap between line and text

        # --- Title centered between lines ---
        x_title = int(self.padding + gap)
        # --- Lines ---
        # Side frame
        c.line(0, y_topframe, 0, y_bottomframe) # left line
        c.line(0, y_bottomframe, w, y_bottomframe) # bottom line
        c.line(w, y_bottomframe, w, y_topframe) # right line
        
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
