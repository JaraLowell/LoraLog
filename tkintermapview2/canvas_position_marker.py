import tkinter
import sys
import os
from typing import TYPE_CHECKING, Callable
from tkinter import PhotoImage

if TYPE_CHECKING:
    from .map_widget import TkinterMapView

from .utility_functions import decimal_to_osm, osm_to_decimal


class CanvasPositionMarker:
    iconspack = []

    @classmethod
    def initialize_icons(cls):
        cls.iconspack = [
            None,
            PhotoImage(file='Data' + os.path.sep + 'marker.png'),
            PhotoImage(file='Data' + os.path.sep + 'marker-green.png'),
            PhotoImage(file='Data' + os.path.sep + 'marker-orange.png'),
            PhotoImage(file='Data' + os.path.sep + 'marker-grey.png'),
            PhotoImage(file='Data' + os.path.sep + 'signal.png'),
            PhotoImage(file='Data' + os.path.sep + 'txbck.png'),
            PhotoImage(file='Data' + os.path.sep + 'blank.png')
        ]

    text_background_image = None  # Class variable

    def __init__(self,
                 map_widget: "TkinterMapView",
                 position: tuple,
                 text: str = None,
                 text_color: str = "#652A22",
                 font=None,
                 marker_color_circle: str = "#9B261E",
                 marker_color_outside: str = "#C5542D",
                 command: Callable = None,
                 image: tkinter.PhotoImage = None,
                 icon_index: int = 0,
                 icon_anchor: str = "center",
                 image_zoom_visibility: tuple = (0, float("inf")),
                 data: any = None):

        # Ensure icons are initialized
        if not CanvasPositionMarker.iconspack:
            CanvasPositionMarker.initialize_icons()

        self.icon_index = icon_index
        self.map_widget = map_widget
        self.position = position
        self.text_color = text_color
        self.marker_color_circle = marker_color_circle
        self.marker_color_outside = marker_color_outside
        self.text = text
        self.text_y_offset = 0  # vertical offset pf text from marker position in px
        self.image = image
        self.icon = CanvasPositionMarker.iconspack[icon_index]
        self.icon_anchor = icon_anchor  # can be center, n, nw, w, sw, s, ew, e, ne
        self.image_hidden = False
        self.image_zoom_visibility = image_zoom_visibility
        self.deleted = False
        self.command = command
        self.data = data
        self.text_background_image = CanvasPositionMarker.iconspack[6]
        self.temperature = None  # Temperature value to display
        self.temperature_unit = "°C"  # Default temperature unit
        self.battery_percentage = None  # Battery percentage to display

        self.polygon = None
        self.big_circle = None
        self.canvas_text = None
        self.canvas_text_bg = None
        self.canvas_image = None
        self.canvas_icon = None
        self.canvas_temperature = None  # Canvas element for temperature display
        self.canvas_battery = None  # Canvas element for battery display

        if font is None:
            if sys.platform == "darwin":
                self.font = "Tahoma 13 bold"
            else:
                self.font = "Tahoma 11 bold"
        else:
            self.font = font

        self.calculate_text_y_offset()

    def __del__(self):
        self.delete()

    def calculate_text_y_offset(self):
        if self.icon is not None:
            if self.icon_anchor in ("center", "e", "w"):
                self.text_y_offset = -round(self.icon.height() / 2) - 5
            elif self.icon_anchor in ("nw", "n", "ne"):
                self.text_y_offset = -5
            elif self.icon_anchor in ("sw", "s", "se"):
                self.text_y_offset = -self.icon.height() - 5
            else:
                raise ValueError(f"CanvasPositionMarker: wring anchor value: {self.icon_anchor}")
        else:
            self.text_y_offset = -56

    def delete(self):
        if self in self.map_widget.canvas_marker_list:
            self.map_widget.canvas_marker_list.remove(self)

        self.map_widget.canvas.delete(self.polygon)
        self.map_widget.canvas.delete(self.big_circle)
        self.map_widget.canvas.delete(self.canvas_text)
        self.map_widget.canvas.delete(self.canvas_text_bg)
        self.map_widget.canvas.delete(self.canvas_icon)
        self.map_widget.canvas.delete(self.canvas_image)
        self.map_widget.canvas.delete(self.canvas_temperature)
        self.map_widget.canvas.delete(self.canvas_battery)

        self.polygon, self.big_circle, self.canvas_text, self.canvas_text_bg, self.canvas_image, self.canvas_icon, self.canvas_temperature, self.canvas_battery = None, None, None, None, None, None, None, None
        self.deleted = True
        self.map_widget.canvas.update()

    def set_position(self, deg_x, deg_y):
        self.position = (deg_x, deg_y)
        self.draw()

    def get_position(self):
        return self.position

    def set_text(self, text):
        self.text = text
        self.draw()

    def set_temperature(self, temperature: float, unit: str = "°C"):
        self.temperature = temperature
        self.temperature_unit = unit
        self.draw()

    def clear_temperature(self):
        """Clear the temperature display."""
        self.temperature = None
        self.draw()

    def get_temperature(self):
        """Get the current temperature value."""
        return self.temperature

    def get_temperature_color(self, temperature: float) -> str:
        if temperature <= 0:
            return "#2bd5ff"  # Light blue for 0 and below
        elif temperature >= 40:
            return "#de6933"  # Orange-red for 40 and above
        else:
            # Three-color gradient: #2bd5ff -> #c9a500 -> #de6933
            # Split the range: 0-20 (blue to yellow), 20-40 (yellow to orange)
            
            if temperature <= 20:
                # Interpolate between blue (#2bd5ff) and yellow (#c9a500)
                ratio = temperature / 20.0
                start_r, start_g, start_b = 43, 213, 255    # #2bd5ff
                end_r, end_g, end_b = 201, 165, 0          # #c9a500
            else:
                # Interpolate between yellow (#c9a500) and orange (#de6933)
                ratio = (temperature - 20) / 20.0
                start_r, start_g, start_b = 201, 165, 0     # #c9a500
                end_r, end_g, end_b = 222, 105, 51         # #de6933
            
            # Interpolate between the colors
            red = int(start_r + (end_r - start_r) * ratio)
            green = int(start_g + (end_g - start_g) * ratio)
            blue = int(start_b + (end_b - start_b) * ratio)
            
            return f"#{red:02X}{green:02X}{blue:02X}"

    def set_battery_percentage(self, percentage: int):
        if percentage >= 99:
            self.battery_percentage = None
        else:
            self.battery_percentage = percentage
        self.draw()

    def clear_battery_percentage(self):
        self.battery_percentage = None
        self.draw()

    def get_battery_percentage(self):
        return self.battery_percentage

    def get_battery_color(self, percentage: int) -> str:
        if percentage <= 20:
            return "#de6933"  # Red for low battery
        elif percentage <= 50:
            return "#c9a500"  # Orange for medium battery
        else:
            return "#00c983"  # Green for good battery

    def change_icon(self, new_icon: int = 0):
        if new_icon == 0:
            raise AttributeError("CanvasPositionMarker: marker needs icon image in constructor to change icon image later")
        else:
            self.icon = CanvasPositionMarker.iconspack[new_icon]
            self.calculate_text_y_offset()
            self.map_widget.canvas.itemconfigure(self.canvas_icon, image=self.icon)

    def hide_image(self, image_hidden: bool):
        self.image_hidden = image_hidden
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

    def draw(self, event=None):
        canvas_pos_x, canvas_pos_y = self.get_canvas_pos(self.position)

        if not self.deleted:
            if 0 - 50 < canvas_pos_x < self.map_widget.width + 50 and 0 < canvas_pos_y < self.map_widget.height + 70:

                # draw icon image for marker
                if self.icon is not None:
                    if self.canvas_icon is None:
                        tagdata = "marker"
                        if self.icon_index > 4:
                            tagdata = "signal"
                        self.canvas_icon = self.map_widget.canvas.create_image(canvas_pos_x, canvas_pos_y,
                                                                               anchor=self.icon_anchor,
                                                                               image=self.icon,
                                                                               tag=tagdata)
                        if self.command is not None and self.icon_index < 5:
                            self.map_widget.canvas.tag_bind(self.canvas_icon, "<Enter>", self.mouse_enter)
                            self.map_widget.canvas.tag_bind(self.canvas_icon, "<Leave>", self.mouse_leave)
                            self.map_widget.canvas.tag_bind(self.canvas_icon, "<Button-1>", self.click)
                    else:
                        self.map_widget.canvas.coords(self.canvas_icon, canvas_pos_x, canvas_pos_y)

                # draw standard icon shape
                else:
                    if self.polygon is None:
                        self.polygon = self.map_widget.canvas.create_polygon(canvas_pos_x - 14, canvas_pos_y - 23,
                                                                             canvas_pos_x, canvas_pos_y,
                                                                             canvas_pos_x + 14, canvas_pos_y - 23,
                                                                             fill=self.marker_color_outside, width=2,
                                                                             outline=self.marker_color_outside, tag="marker")
                        if self.command is not None:
                            self.map_widget.canvas.tag_bind(self.polygon, "<Enter>", self.mouse_enter)
                            self.map_widget.canvas.tag_bind(self.polygon, "<Leave>", self.mouse_leave)
                            self.map_widget.canvas.tag_bind(self.polygon, "<Button-1>", self.click)
                    else:
                        self.map_widget.canvas.coords(self.polygon,
                                                      canvas_pos_x - 14, canvas_pos_y - 23,
                                                      canvas_pos_x, canvas_pos_y,
                                                      canvas_pos_x + 14, canvas_pos_y - 23)
                    if self.big_circle is None:
                        self.big_circle = self.map_widget.canvas.create_oval(canvas_pos_x - 14, canvas_pos_y - 45,
                                                                             canvas_pos_x + 14, canvas_pos_y - 17,
                                                                             fill=self.marker_color_circle, width=6,
                                                                             outline=self.marker_color_outside, tag="marker")
                        if self.command is not None:
                            self.map_widget.canvas.tag_bind(self.big_circle, "<Enter>", self.mouse_enter)
                            self.map_widget.canvas.tag_bind(self.big_circle, "<Leave>", self.mouse_leave)
                            self.map_widget.canvas.tag_bind(self.big_circle, "<Button-1>", self.click)
                    else:
                        self.map_widget.canvas.coords(self.big_circle,
                                                      canvas_pos_x - 14, canvas_pos_y - 45,
                                                      canvas_pos_x + 14, canvas_pos_y - 17)

                if self.text is not None:
                    if self.canvas_text is None:
                        self.canvas_text_bg = self.map_widget.canvas.create_image(canvas_pos_x, canvas_pos_y + (self.text_y_offset + 1),
                                                                                image=self.text_background_image,
                                                                                anchor=tkinter.S,
                                                                                tag=("marker", "marker_text_bg"))
                        self.canvas_text = self.map_widget.canvas.create_text(canvas_pos_x, canvas_pos_y + self.text_y_offset,
                                                                              anchor=tkinter.S,
                                                                              text=self.text,
                                                                              fill=self.text_color,
                                                                              font=self.font,
                                                                              tag=("marker", "marker_text"))
                        if self.command is not None:
                            self.map_widget.canvas.tag_bind(self.canvas_text, "<Enter>", self.mouse_enter)
                            self.map_widget.canvas.tag_bind(self.canvas_text, "<Leave>", self.mouse_leave)
                            self.map_widget.canvas.tag_bind(self.canvas_text, "<Button-1>", self.click)
                    else:
                        self.map_widget.canvas.coords(self.canvas_text_bg, canvas_pos_x, canvas_pos_y + (self.text_y_offset + 1))
                        self.map_widget.canvas.coords(self.canvas_text, canvas_pos_x, canvas_pos_y + self.text_y_offset)
                        self.map_widget.canvas.itemconfig(self.canvas_text, text=self.text)
                else:
                    if self.canvas_text is not None:
                        self.map_widget.canvas.tag_unbind(self.canvas_text, "<Enter>")
                        self.map_widget.canvas.tag_unbind(self.canvas_text, "<Leave>")
                        self.map_widget.canvas.tag_unbind(self.canvas_text, "<Button-1>")
                        self.map_widget.canvas.delete(self.canvas_text)
                    if self.canvas_text_bg is not None:
                        self.map_widget.canvas.delete(self.canvas_text_bg)

                if self.image is not None and self.image_zoom_visibility[0] <= self.map_widget.zoom <= self.image_zoom_visibility[1]\
                        and not self.image_hidden:

                    if self.canvas_image is None:
                        self.canvas_image = self.map_widget.canvas.create_image(canvas_pos_x, canvas_pos_y + (self.text_y_offset - 30),
                                                                                anchor=tkinter.S,
                                                                                image=self.image,
                                                                                tag=("marker", "marker_image"))
                    else:
                        self.map_widget.canvas.coords(self.canvas_image, canvas_pos_x, canvas_pos_y + (self.text_y_offset - 30))
                else:
                    if self.canvas_image is not None:
                        self.map_widget.canvas.delete(self.canvas_image)
                        self.canvas_image = None

                # draw temperature under the marker if set
                if self.temperature is not None:
                    temp_text = f"{self.temperature}{self.temperature_unit}"
                    temp_y_pos = canvas_pos_y + self.text_y_offset - 18
                    temp_color = self.get_temperature_color(self.temperature)
                    
                    if self.canvas_temperature is None:
                        self.canvas_temperature = self.map_widget.canvas.create_text(canvas_pos_x, temp_y_pos,
                                                                                    anchor=tkinter.S,
                                                                                    text=temp_text,
                                                                                    fill=temp_color,
                                                                                    font=(self.font[0], int(self.font[1]) - 2),
                                                                                    tag=("marker", "marker_temperature"))
                    else:
                        self.map_widget.canvas.coords(self.canvas_temperature, canvas_pos_x, temp_y_pos)
                        self.map_widget.canvas.itemconfig(self.canvas_temperature, text=temp_text, fill=temp_color)
                else:
                    if self.canvas_temperature is not None:
                        self.map_widget.canvas.delete(self.canvas_temperature)
                        self.canvas_temperature = None

                # draw battery percentage on opposite side from text if set and under 99%
                if self.battery_percentage is not None and self.battery_percentage < 99:
                    battery_text = f"{self.battery_percentage}%"
                    # Position on opposite side from text_y_offset
                    battery_y_pos = canvas_pos_y + (-self.text_y_offset)
                    battery_color = self.get_battery_color(self.battery_percentage)

                    if self.canvas_battery is None:
                        self.canvas_battery = self.map_widget.canvas.create_text(canvas_pos_x, battery_y_pos,
                                                                                anchor=tkinter.N,
                                                                                text=battery_text,
                                                                                fill=battery_color,
                                                                                font=(self.font[0], int(self.font[1]) - 2),
                                                                                tag=("marker", "marker_battery"))
                    else:
                        self.map_widget.canvas.coords(self.canvas_battery, canvas_pos_x, battery_y_pos)
                        self.map_widget.canvas.itemconfig(self.canvas_battery, text=battery_text, fill=battery_color)
                else:
                    if self.canvas_battery is not None:
                        self.map_widget.canvas.delete(self.canvas_battery)
                        self.canvas_battery = None
            else:
                self.map_widget.canvas.delete(self.canvas_icon)
                self.map_widget.canvas.delete(self.canvas_text)
                self.map_widget.canvas.delete(self.canvas_text_bg)
                self.map_widget.canvas.delete(self.polygon)
                self.map_widget.canvas.delete(self.big_circle)
                self.map_widget.canvas.delete(self.canvas_image)
                self.map_widget.canvas.delete(self.canvas_temperature)
                self.map_widget.canvas.delete(self.canvas_battery)
                self.canvas_text, self.polygon, self.big_circle, self.canvas_text_bg, self.canvas_image, self.canvas_icon, self.canvas_temperature, self.canvas_battery = None, None, None, None, None, None, None, None

            self.map_widget.manage_z_order()
