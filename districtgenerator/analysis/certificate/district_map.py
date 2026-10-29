"""Map of buildings, pipes and the energy hub."""
from reportlab.lib import colors
import math
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle, Polygon, Group
from districtgenerator.analysis.certificate.components import BaseReportFlowable


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
        if self.scale is not None:
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

        else:
            box_start_y = current_y

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

        
        d.add(String(text_x, current_y- y_text_offset, self.translate("legend_eh"), 
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
        current_y -= size_elements # Move to center of the symbol
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
        current_y -= size_elements # Move to center of the symbol
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
