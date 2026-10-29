"""Entry point that builds the certificate PDF."""
from reportlab.platypus import NextPageTemplate, PageBreak, FrameBreak
import os
from districtgenerator.utilities.paths import PACKAGE_DIR
from districtgenerator.analysis.certificate.components import ReportComponent
from districtgenerator.analysis.certificate.data_extractor import DataExtractor
from districtgenerator.analysis.certificate.layout import CertificateLayout, CertificateTemplate
from districtgenerator.analysis.certificate.theme import ThemeManager


class CertificateBuilder(ReportComponent):
    """
    This class orchestrates the certificate creation by setting up data, theme, initializing the PDF template, and building the story.
    """

    def __init__(self, data, kpis, result_path, file_name=None) -> None:
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
            if file_name:
                self.outputpath = os.path.join(result_path, f"{file_name}.pdf")
            else:
                self.outputpath = os.path.join(result_path, f"Quartiersenergieausweis_{self.scenario_name}.pdf")


        else:
            src_path = PACKAGE_DIR
            if file_name:
                self.outputpath = os.path.join(src_path, "results", f"{file_name}.pdf")
            else:
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
        self.layout.create_key_performance_indicator(data_key_performance_indicator=self.data_object.get_key_performance_indicator())
        self.layout.create_data_district_structure(data_district_structure=self.data_object.get_district_structure())
        
        story.extend(self.layout.get_story())
        self.layout.reset_story()
        story.append(FrameBreak()) 

        self.layout.create_footer(str(self.scenario_name)) 
        story.extend(self.layout.get_story())
        self.layout.reset_story()
        
        story.append(NextPageTemplate('ContentPage'))
        story.append(PageBreak()) 

        self.layout.create_yearly_bar_charts(self.data_object.get_key_performance_indicator())
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
        self.layout.create_district_structure_details(data_district_structure=self.data_object.get_district_structure())
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
