import tkinter
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .map_widget import TkinterMapView

from .utility_functions import decimal_to_osm, osm_to_decimal


class CanvasPath:
    def __init__(self,
                 map_widget: "TkinterMapView",
                 position_list: list,
                 color: str = "#3E69CB",
                 command=None,
                 name: str = None,
                 signal_strength: str = None,
                 width: int = 9,
                 data: any = None):

        self.map_widget = map_widget
        self.position_list = position_list
        self.canvas_lines = []  # Store multiple lines
        self.canvas_text = None  # Store signal strength text
        self.canvas_text_bg = None  # Store signal strength text background
        self.deleted = False

        self.path_color = color
        self.command = command
        self.width = width
        self.name = name
        self.signal_strength = signal_strength
        self.data = data

        self.last_upper_left_tile_pos = None
        self.last_position_list_length = len(self.position_list)
    
    def __del__(self):
        self.delete()

    def delete(self):
        for line in self.canvas_lines:
            self.map_widget.canvas.delete(line)
        self.canvas_lines = []
        if self.canvas_text:
            self.map_widget.canvas.delete(self.canvas_text)
            self.canvas_text = None
        if self.canvas_text_bg:
            self.map_widget.canvas.delete(self.canvas_text_bg)
            self.canvas_text_bg = None
        self.deleted = True
        self.map_widget.canvas.update()

    def set_position_list(self, position_list: list):
        self.position_list = position_list
        self.draw()

    def set_signal_strength(self, signal_strength: str):
        self.signal_strength = signal_strength
        # Remove existing text and background if any
        if self.canvas_text:
            self.map_widget.canvas.delete(self.canvas_text)
            self.canvas_text = None
        if self.canvas_text_bg:
            self.map_widget.canvas.delete(self.canvas_text_bg)
            self.canvas_text_bg = None
        self.draw()

    def add_position(self, deg_x, deg_y, index=-1):
        if index == -1:
            self.position_list.append((deg_x, deg_y))
        else:
            self.position_list.insert(index, (deg_x, deg_y))
        # self.draw()

    def remove_position(self, deg_x, deg_y):
        self.position_list.remove((deg_x, deg_y))
        self.draw()

    def get_canvas_pos(self, position, widget_tile_width, widget_tile_height):
        tile_position = decimal_to_osm(*position, round(self.map_widget.zoom))

        canvas_pos_x = ((tile_position[0] - self.map_widget.upper_left_tile_pos[0]) / widget_tile_width) * self.map_widget.width
        canvas_pos_y = ((tile_position[1] - self.map_widget.upper_left_tile_pos[1]) / widget_tile_height) * self.map_widget.height

        return canvas_pos_x, canvas_pos_y

    def mouse_enter(self, event=None):
        if sys.platform == "darwin":
            self.map_widget.canvas.config(cursor="pointinghand")
        elif sys.platform.startswith("win"):
            self.map_widget.canvas.config(cursor="hand2")
        else:
            self.map_widget.canvas.config(cursor="hand2")  # not tested what it looks like on Linux!

    def mouse_leave(self, event=None):
        self.map_widget.canvas.config(cursor="arrow")

    def click(self, event=None):
        if self.command is not None:
            self.command(self)

    def draw(self, move=False):
        new_line_length = self.last_position_list_length != len(self.position_list)
        self.last_position_list_length = len(self.position_list)

        widget_tile_width = self.map_widget.lower_right_tile_pos[0] - self.map_widget.upper_left_tile_pos[0]
        widget_tile_height = self.map_widget.lower_right_tile_pos[1] - self.map_widget.upper_left_tile_pos[1]

        if move is True and self.last_upper_left_tile_pos is not None and new_line_length is False:
            x_move = ((self.last_upper_left_tile_pos[0] - self.map_widget.upper_left_tile_pos[0]) / widget_tile_width) * self.map_widget.width
            y_move = ((self.last_upper_left_tile_pos[1] - self.map_widget.upper_left_tile_pos[1]) / widget_tile_height) * self.map_widget.height

            for i in range(0, len(self.position_list)* 2, 2):
                self.canvas_line_positions[i] += x_move
                self.canvas_line_positions[i + 1] += y_move
                
            # Move signal strength text and background as well
            if self.canvas_text:
                current_coords = self.map_widget.canvas.coords(self.canvas_text)
                if current_coords:
                    self.map_widget.canvas.coords(self.canvas_text, current_coords[0] + x_move, current_coords[1] + y_move)
            if self.canvas_text_bg:
                current_coords = self.map_widget.canvas.coords(self.canvas_text_bg)
                if current_coords:
                    self.map_widget.canvas.coords(self.canvas_text_bg, 
                                                 current_coords[0] + x_move, current_coords[1] + y_move,
                                                 current_coords[2] + x_move, current_coords[3] + y_move)
        else:
            self.canvas_line_positions = []
            for position in self.position_list:
                canvas_position = self.get_canvas_pos(position, widget_tile_width, widget_tile_height)
                self.canvas_line_positions.append(canvas_position[0])
                self.canvas_line_positions.append(canvas_position[1])

        if not self.deleted and ((self.path_color == "#006642" and self.map_widget.draw_heard == True) or (self.path_color != "#006642" and self.map_widget.draw_trail == True)):
            if not self.canvas_lines:
                self.map_widget.canvas.delete(self.canvas_lines)
                # Custom code to have 2 type of paths
                if self.path_color == "#006642":
                    zoom_level = round(self.map_widget.zoom)
                    zoom_factor = zoom_level * 0.35
                    new_length = round((4 + zoom_factor) * (zoom_level / 18), 2)
                    new_width  = round((8 + zoom_factor) * (zoom_level / 18), 2)
                    new_wing   = round((1 + zoom_factor) * (zoom_level / 18), 2)
                    line = self.map_widget.canvas.create_line(self.canvas_line_positions,
                                                              width=self.width, fill=self.path_color,
                                                              capstyle=tkinter.ROUND, joinstyle=tkinter.ROUND,
                                                              tag="path", arrow=tkinter.FIRST, arrowshape=(new_length, new_width, new_wing), dash=(3, 12), smooth=True)
                    self.canvas_lines.append(line)
                else: 
                    line = self.map_widget.canvas.create_line(self.canvas_line_positions,
                                                              width=self.width, fill=self.path_color,
                                                              capstyle=tkinter.ROUND, joinstyle=tkinter.ROUND,
                                                              tag="path")
                    self.canvas_lines.append(line)

                # if self.command is not None:
                #     self.map_widget.canvas.tag_bind(line, "<Enter>", self.mouse_enter)
                #     self.map_widget.canvas.tag_bind(line, "<Leave>", self.mouse_leave)
                #     self.map_widget.canvas.tag_bind(line, "<Button-1>", self.click)
                
                # Create signal strength text at 1/4 of the line
                if self.signal_strength and len(self.position_list) >= 2:
                    quarter_pos = self.get_quarter_position()
                    if quarter_pos:
                        canvas_text_pos = self.get_canvas_pos(quarter_pos, widget_tile_width, widget_tile_height)
                        
                        # Create text with background
                        self.create_text_with_background(
                            canvas_text_pos[0], canvas_text_pos[1],
                            self.signal_strength, 8
                        )
            else:
                for line in self.canvas_lines:
                    self.map_widget.canvas.coords(line, self.canvas_line_positions)
                
                # Handle signal strength text for both move and zoom operations
                if self.signal_strength and len(self.position_list) >= 2:
                    quarter_pos = self.get_quarter_position()
                    if quarter_pos:
                        canvas_text_pos = self.get_canvas_pos(quarter_pos, widget_tile_width, widget_tile_height)
                        
                        if move and self.canvas_text:
                            # For move operations, just update coordinates
                            self.map_widget.canvas.coords(self.canvas_text, canvas_text_pos[0], canvas_text_pos[1])
                            if self.canvas_text_bg:
                                # Update background rectangle position
                                bbox = self.map_widget.canvas.bbox(self.canvas_text)
                                if bbox:
                                    padding = 2
                                    x1, y1, x2, y2 = bbox
                                    x1 -= padding
                                    y1 -= padding
                                    x2 += padding
                                    y2 += padding
                                    self.map_widget.canvas.coords(self.canvas_text_bg, x1, y1, x2, y2)
                        else:
                            # For zoom operations, recreate the text and background
                            if self.canvas_text:
                                self.map_widget.canvas.delete(self.canvas_text)
                                self.canvas_text = None
                            if self.canvas_text_bg:
                                self.map_widget.canvas.delete(self.canvas_text_bg)
                                self.canvas_text_bg = None

                            self.create_text_with_background(
                                canvas_text_pos[0], canvas_text_pos[1],
                                self.signal_strength, 8
                            )
        else:
            for line in self.canvas_lines:
                self.map_widget.canvas.delete(line)
            self.canvas_lines = []
            # Remove signal strength text and background when line is hidden
            if self.canvas_text:
                self.map_widget.canvas.delete(self.canvas_text)
                self.canvas_text = None
            if self.canvas_text_bg:
                self.map_widget.canvas.delete(self.canvas_text_bg)
                self.canvas_text_bg = None

        self.map_widget.manage_z_order()
        self.last_upper_left_tile_pos = self.map_widget.upper_left_tile_pos

    def get_quarter_position(self):
        """Calculate the position at 1/4 of the line length for text placement"""
        if len(self.position_list) < 2:
            return None
        
        # Calculate total line length
        total_length = 0
        segment_lengths = []
        
        for i in range(len(self.position_list) - 1):
            pos1 = self.position_list[i]
            pos2 = self.position_list[i + 1]
            
            # Convert to canvas coordinates for accurate length calculation
            widget_tile_width = self.map_widget.lower_right_tile_pos[0] - self.map_widget.upper_left_tile_pos[0]
            widget_tile_height = self.map_widget.lower_right_tile_pos[1] - self.map_widget.upper_left_tile_pos[1]
            
            canvas_pos1 = self.get_canvas_pos(pos1, widget_tile_width, widget_tile_height)
            canvas_pos2 = self.get_canvas_pos(pos2, widget_tile_width, widget_tile_height)
            
            segment_length = ((canvas_pos2[0] - canvas_pos1[0]) ** 2 + (canvas_pos2[1] - canvas_pos1[1]) ** 2) ** 0.5
            segment_lengths.append(segment_length)
            total_length += segment_length
        
        # Find position at 1/4 of total length
        quarter_length = total_length * 0.25
        current_length = 0
        
        for i, segment_length in enumerate(segment_lengths):
            if current_length + segment_length >= quarter_length:
                # The quarter point is in this segment
                remaining_length = quarter_length - current_length
                ratio = remaining_length / segment_length if segment_length > 0 else 0
                
                pos1 = self.position_list[i]
                pos2 = self.position_list[i + 1]
                
                # Interpolate between the two positions
                quarter_pos = (
                    pos1[0] + (pos2[0] - pos1[0]) * ratio,
                    pos1[1] + (pos2[1] - pos1[1]) * ratio
                )
                
                return quarter_pos
            current_length += segment_length
        
        # Fallback to first position if calculation fails
        return self.position_list[0]

    def create_text_with_background(self, x, y, text, font_size=8):
        """Create text with a background rectangle for better readability"""
        # Create temporary text to measure dimensions
        temp_text = self.map_widget.canvas.create_text(x, y, text=text, font=("Arial", font_size, "bold"))
        bbox = self.map_widget.canvas.bbox(temp_text)
        self.map_widget.canvas.delete(temp_text)
        
        if bbox:
            # Add padding around the text
            padding = 1
            x1, y1, x2, y2 = bbox
            x1 -= padding
            y1 -= padding
            x2 += padding
            y2 += padding
            
            # Create background rectangle
            self.canvas_text_bg = self.map_widget.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill="#464646",
                outline="#464646",
                width=1,
                tags="signal_text_bg"
            )
            
            # Create text on top of background
            self.canvas_text = self.map_widget.canvas.create_text(
                x, y,
                text=text,
                fill="#00c983",
                font=("Arial", font_size, "bold"),
                tags="signal_text"
            )
        else:
            # Fallback if bbox fails
            self.canvas_text = self.map_widget.canvas.create_text(
                x, y,
                text=text,
                fill="#00c983",
                font=("Arial", font_size, "bold"),
                tags="signal_text"
            )
