import tkinter
import sys
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .map_widget import TkinterMapView

from .utility_functions import decimal_to_osm, osm_to_decimal


class CanvasPolygon:
    def __init__(self,
                 map_widget: "TkinterMapView",
                 position: tuple,
                 range_in_meters: int = 10,
                 outline_color: str = "#3e97cb",
                 fill_color: str = "gray95",
                 text_color: str = "black", # not that we use it but meh....
                 border_width: int = 5,
                 command: Callable = None,
                 name: str = None,
                 data: any = None):

        self.map_widget = map_widget
        self.position = position  # list with decimal positions
        self.canvas_polygon_positions = []  # list with canvas coordinates positions
        self.range_in_meters = range_in_meters # range in meters for circle
        self.canvas_polygon = None
        self.deleted = False

        self.name = name
        self.data = data
        self.outline_color = outline_color
        self.fill_color = fill_color  # can also be None for transparent fill
        self.text_color = text_color
        self.border_width = border_width
        self.command = command

        self.last_upper_left_tile_pos = None
        self.last_position = self.position

    def delete(self):
        self.map_widget.canvas.delete(self.canvas_polygon)

        if self in self.map_widget.canvas_polygon_list:
            self.map_widget.canvas_polygon_list.remove(self)

        self.canvas_polygon = None
        self.deleted = True

    def add_position(self, deg_x, deg_y, index=None):
        self.position = (deg_x, deg_y)
        self.draw()

    def remove_position(self, deg_x, deg_y):
        self.draw()

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

    def get_canvas_pos(self, position):
        tile_position = decimal_to_osm(*position, round(self.map_widget.zoom))

        widget_tile_width = self.map_widget.lower_right_tile_pos[0] - self.map_widget.upper_left_tile_pos[0]
        widget_tile_height = self.map_widget.lower_right_tile_pos[1] - self.map_widget.upper_left_tile_pos[1]

        canvas_pos_x = ((tile_position[0] - self.map_widget.upper_left_tile_pos[0]) / widget_tile_width) * self.map_widget.width
        canvas_pos_y = ((tile_position[1] - self.map_widget.upper_left_tile_pos[1]) / widget_tile_height) * self.map_widget.height

        return canvas_pos_x, canvas_pos_y

    ## Custom addon replacing polygon for circle
    def draw(self, move=False):
        if not self.deleted:
            x, y = self.get_canvas_pos(self.position)
            zoom_level = round(self.map_widget.zoom)
            if self.map_widget.draw_range: # zoom_level > 12 and zoom_level < 17:
                pixels_per_meter = round((256 * (2 ** zoom_level)) / 40075016.686, 6) # 256 is the tile size, 40075016.686 is the earth circumference
                radius_in_pixels = round(self.range_in_meters * pixels_per_meter, 6)
                if self.canvas_polygon is None:
                    self.canvas_polygon = self.map_widget.canvas.create_oval(x - radius_in_pixels,
                                                                            y - radius_in_pixels,
                                                                            x + radius_in_pixels,
                                                                            y + radius_in_pixels,
                                                                            outline="#995c00",
                                                                            tag="polygon")
                    # if self.command is not None:
                    #     self.map_widget.canvas.tag_bind(self.canvas_polygon, "<Enter>", self.mouse_enter)
                    #     self.map_widget.canvas.tag_bind(self.canvas_polygon, "<Leave>", self.mouse_leave)
                    #     self.map_widget.canvas.tag_bind(self.canvas_polygon, "<Button-1>", self.click)
                else:
                    self.map_widget.canvas.coords(self.canvas_polygon, x - radius_in_pixels,
                                                                    y - radius_in_pixels,
                                                                    x + radius_in_pixels,
                                                                    y + radius_in_pixels)
            else:
                if self.canvas_polygon is not None:
                    self.map_widget.canvas.delete(self.canvas_polygon)
                    self.canvas_polygon = None
        else:
            self.map_widget.canvas.delete(self.canvas_polygon)
            self.canvas_polygon = None

        self.map_widget.manage_z_order()
        self.last_upper_left_tile_pos = self.map_widget.upper_left_tile_pos
