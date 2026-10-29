"""Page templates and the order of all certificate elements."""
from reportlab.platypus  import BaseDocTemplate, PageTemplate, Frame
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, Spacer
from districtgenerator.analysis.certificate.charts import YearlyStackedBarCharts
from districtgenerator.analysis.certificate.components import FrameBox, ReportComponent
from districtgenerator.analysis.certificate.district_map import DistrictLayout
from districtgenerator.analysis.certificate.sections import DecentralSystems, EnergyHub, Footer, Header, district_structure, key_performance_indicator
from districtgenerator.analysis.certificate.tables import Hinweise, PaginatedDataFrameTable


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

    def create_key_performance_indicator(self, data_key_performance_indicator):
        """Creates the key performance indicator section and adds it to the story."""
        title = self.translate("title_kpis")
        box = FrameBox(title=title)
        frame_width, frame_height = self.certificate_builder.get_Framesize(id='TitleContentFrame')
        avail_w, avail_h = FrameBox.get_available_space_content(frame_width, frame_height)
        
        class_key_performance_indicator = key_performance_indicator(kpi_data=data_key_performance_indicator, availWidth=avail_w)
        box.set_content(class_key_performance_indicator)
        self.story.append(box)
        self.add_standard_spacer()

    def create_data_district_structure(self, data_district_structure):
        """Creates the district structure section and adds it to the story."""
        title = self.translate("title_district_structure")
        box = FrameBox(title=title)
        
        district_structure_flowable = district_structure(
            summary_table_data=data_district_structure["summary_table"],
            general_info=data_district_structure["general_info"]
        )
        
        box.set_content(district_structure_flowable, full_width=False)
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

    def create_district_structure_details(self, data_district_structure):
        """Creates the detailed matrix on a landscape page."""
        df_details = data_district_structure["df_details"]
        
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

        name= self.translate("title_district_layout")
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
        
        barcharts_flowable = YearlyStackedBarCharts(costs_data=costs_data, co2_data=co2_data, availWidth=avail_w, availHeight=avail_h, observation_time=obs_time)
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

        # Title Page
        page_id = 'TitlePage'
        margins = self.page_margins
        margin_x, margin_y = self.page_margins[page_id]

        footer_height = Footer.get_required_height()
        footer_spacing = self.style.get_spacing('medium')

        title_content_frame = Frame(
            margin_x, 
            margin_y + footer_height,
            width - 2*margin_x, 
            height - 2*margin_y - footer_height - footer_spacing,  
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, 
            id='TitleContentFrame'
        )
        
        title_footer_frame = Frame(
            margin_x, 
            margin_y,  
            width - 2*margin_x, 
            footer_height,  
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

        margin_x, margin_y = self.page_margins[page_id]
        
        canvas.setFont(self.style.get_font(bold=False), self.style.get_font_size('page_number'))
        canvas.setFillColorRGB(*self.style.get_color('text_light'))
        
        canvas.drawRightString(width - margin_x, margin_y - 20, f"{self.translate('ui_page')} {doc.page}")
        canvas.restoreState()

    def get_Framesize(self, id:str):
        """Returns the size of the frame with the given id."""
        for template in self.pageTemplates:
            for frame in template.frames:
                if frame.id == id:
                    return frame._width, frame._height
        raise ValueError(f"No frame with id {id} found.")
