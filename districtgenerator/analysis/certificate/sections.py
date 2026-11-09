"""Text sections of the certificate pages."""
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib import colors
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, Spacer
from datetime import datetime
import pandas as pd
from reportlab.platypus import Flowable
from districtgenerator.analysis.certificate.charts import EnergyPieChart, MaxLoadsBarChart
from districtgenerator.analysis.certificate.components import BaseReportFlowable, FrameBox
from districtgenerator.analysis.certificate.tables import PaginatedDataFrameTable
from districtgenerator.analysis.certificate.theme import DEBUG, debug_line_width


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


class key_performance_indicator(BaseReportFlowable):
    """
    Generates the key performance indicator section of the certificate.
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

        left_column_content = [Spacer(1, self.style.get_padding()),self.t_summary, Spacer(1, 3*self.style.get_padding()), Title(self.translate("title_optimized_operation_kpis")), Spacer(1, self.style.get_padding()), self.t_operation]
        right_column_content = [self.pie_chart_flowable, Spacer(1, self.style.get_padding()), self.max_loads_flowable]

        layout_data = [
            [left_column_content, right_column_content]
        ]
        
        self.layout_table = Table(layout_data, colWidths=[col_w_left, col_w_right])
        self.layout_table.setStyle(self.style.get_table_styles()['layout'])
    
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


class district_structure(BaseReportFlowable):
    """
    This class generates the district structure section of the certificate providing a summary of the building stock and the neighborhood characteristics.
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
