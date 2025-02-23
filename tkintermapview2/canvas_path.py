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
                 width: int = 9,
                 data: any = None):

        self.map_widget = map_widget
        self.position_list = position_list
        self.canvas_lines = []  # Store multiple lines
        self.deleted = False

        self.path_color = color
        self.command = command
        self.width = width
        self.name = name
        self.data = data

        self.last_upper_left_tile_pos = None
        self.last_position_list_length = len(self.position_list)
    
    def __del__(self):
        self.delete()

    def delete(self):
        for line in self.canvas_lines:
            self.map_widget.canvas.delete(line)
        self.canvas_lines = []
        self.deleted = True
        self.map_widget.canvas.update()

    def set_position_list(self, position_list: list):
        self.position_list = position_list
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
            else:
                for line in self.canvas_lines:
                    self.map_widget.canvas.coords(line, self.canvas_line_positions)
        else:
            for line in self.canvas_lines:
                self.map_widget.canvas.delete(line)
            self.canvas_lines = []

        self.map_widget.manage_z_order()
        self.last_upper_left_tile_pos = self.map_widget.upper_left_tile_pos
