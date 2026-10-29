"""Charts of the certificate."""
from reportlab.lib import colors
import math
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle, Polygon, Group
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.barcharts import VerticalBarChart
from districtgenerator.analysis.certificate.components import BaseReportFlowable
from districtgenerator.analysis.certificate.theme import DEBUG, debug_line_width


class EnergyPieChart(BaseReportFlowable):
    """
    Standalone Flowable that generates a pie chart for annual energy demands,
    using the configured colors.
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

        
        d.add(String(width / 2.0, title_y, self.translate("title_pie_chart_energy"), 
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


class YearlyStackedBarCharts(BaseReportFlowable):
    """
    Generates stacked bar charts for each simulated year, with a shared legend below.
    """
    def __init__(self, costs_data: list, co2_data: list, availWidth: float, availHeight: float, observation_time: int = None):
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
            raise ValueError(f"Mismatch in years between costs_data and co2_data ({years} vs {years_co2}). Ensure both datasets cover the same years as Simulations are linked.")
        
        year_labels = []
        for i in range(len(years)):
            start_year = years[i]
            
            if i < len(years) - 1:
                # Das Ende ist das Folgejahr minus 1
                end_year = years[i+1] - 1
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
        max_co2 = max([max(series) for series in co2_series]) if co2_series else 0 # Unit in t/a
        if max_co2 < 5:
            co2_series = [tuple(val * 1000 for val in series) for series in co2_series]
            charts_config[0]["title"] = f"{self.translate('title_emissions_graph')} (kg/a)"
            charts_config[0]["series"] = co2_series

        # Costs in t€/a or €/a
        max_costs = max([max(series) for series in cost_series]) if cost_series else 0 # Unit in €/a
        if max_costs > 5000:
            cost_series = [tuple(val / 1000 for val in series) for series in cost_series]
            charts_config[1]["title"] = f"{self.translate('title_cost_graph')} ({self.translate('name_for_thousand')} €/a)"
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
                mapping = {
                    self.translate("name_central_costs"): "eh_fixed",
                    self.translate("name_decentral_costs"): "decentral_fixed",
                    self.translate("name_el"): "electricity",
                    self.translate("name_gas"): "gas",
                    self.translate("name_oil"): "oil",
                    self.translate("name_waste"): "waste",
                    self.translate("name_biomass"): "biomass",
                    self.translate("name_district_heat"): "district_heat",
                    self.translate("name_hydrogen"): "hydrogen",
                    self.translate("name_feed_in_revenue"): "revenue_feed_in_el"
                }
                
                # Check if the exact string exists in mapping
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
            d.add(String(bc.x + chart_width/2, current_y, self.translate("axis_title_simulated_year"), fontName=axis_label_font, fontSize=axis_label_size, textAnchor='middle'))

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
