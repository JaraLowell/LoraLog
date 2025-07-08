import requests
import math
import threading
import tkinter
import tkinter.ttk as ttk
import tkinter.messagebox
import time
import PIL
import sys
import io
import sqlite3
import pyperclip
import geocoder
from PIL import Image, ImageTk, ImageEnhance, ImageOps, ImageChops
from typing import Callable, List, Dict, Union, Tuple
from functools import partial
import colorsys

from .canvas_position_marker import CanvasPositionMarker
from .canvas_tile import CanvasTile
from .utility_functions import decimal_to_osm, osm_to_decimal
from .canvas_button import CanvasButton
from .canvas_path import CanvasPath
from .canvas_polygon import CanvasPolygon

import os  # Add this import at the top of the file

class TkinterMapView(tkinter.Frame):
    def __init__(self, *args,
                 width: int = 300,
                 height: int = 200,
                 corner_radius: int = 0,
                 bg_color: str = None,
                 database_path: str = None,
                 use_database_only: bool = False,
                 max_zoom: int = 19,
                 use_filter: bool = False,
                 **kwargs):
        super().__init__(*args, **kwargs)

        self.running = True
        self.pausecount = 0
        self.viewport_bounds = (0, 0, 0, 0)
        self.width = width
        self.height = height
        self.corner_radius = corner_radius if corner_radius <= 30 else 30  # corner_radius can't be greater than 30
        self.configure(width=self.width, height=self.height)
        self.db_cursor = None

        self.draw_trail = False
        self.draw_range = False
        self.draw_heard = True
        self.draw_oldnodes = False
        self.oldnodes_filter = "7days"  # Options: "7days", "1month", "all"

        # detect color of master widget for rounded corners
        if bg_color is None:
            # map widget is placed in a CTkFrame from customtkinter library
            if (hasattr(self.master, "canvas") and hasattr(self.master, "fg_color")) or (hasattr(self.master, "_canvas") and hasattr(self.master, "_fg_color")):
                # customtkinter version >=5.0.0
                if hasattr(self.master, "_apply_appearance_mode"):
                    self.bg_color: str = self.master._apply_appearance_mode(self.master.cget("fg_color"))
                # customtkinter version <=4.6.3
                elif hasattr(self.master, "fg_color"):
                    if type(self.master.fg_color) == tuple or type(self.master.fg_color) == list:
                        self.bg_color: str = self.master.fg_color[self.master._appearance_mode]
                    else:
                        self.bg_color: str = self.master.fg_color

            # map widget is placed on a tkinter.Frame or tkinter.Tk
            elif isinstance(self.master, (tkinter.Frame, tkinter.Tk, tkinter.Toplevel, tkinter.LabelFrame)):
                self.bg_color: str = self.master.cget("bg")

            # map widget is placed in a ttk widget
            elif isinstance(self.master, (ttk.Frame, ttk.LabelFrame, ttk.Notebook)):
                try:
                    ttk_style = ttk.Style()
                    self.bg_color = ttk_style.lookup(self.master.winfo_class(), 'background')
                except Exception:
                    self.bg_color: str = "#000000"

            # map widget is placed on an unknown widget
            else:
                self.bg_color: str = "#000000"
        else:
            self.bg_color = bg_color

        self.grid_rowconfigure(0, weight=1)  # configure 1x1 grid system
        self.grid_columnconfigure(0, weight=1)

        self.canvas = tkinter.Canvas(master=self,
                                     highlightthicknes=0,
                                     bg="#1D1D1D",
                                     width=self.width,
                                     height=self.height)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # zoom buttons
        self.button_zoom_in = CanvasButton(self, (20, 20), text="+", command=self.button_zoom_in)
        self.button_zoom_out = CanvasButton(self, (20, 60), text="-", command=self.button_zoom_out)

        # Canvas Buttons Extra
        self.btoggle_trail  = CanvasButton(self, (20, 120), text="☈", command=self.toggle_trail)
        self.btoggle_heard  = CanvasButton(self, (20, 160), text="⇢", command=self.toggle_heard, fg="#00c27e")
        self.btoggle_range  = CanvasButton(self, (20, 200), text="⚆", command=self.toggle_range)
        self.btoggle_oldnodes = CanvasButton(self, (20, 240), text="☠", command=self.toggle_oldnodes)

        # Radio buttons for oldnodes filter (initially hidden)
        self.bradio_7days = CanvasButton(self, (70, 240), text="7d", command=lambda: self.set_oldnodes_filter("7days"), width=30, height=20)
        self.bradio_1month = CanvasButton(self, (105, 240), text="1m", command=lambda: self.set_oldnodes_filter("1month"), width=30, height=20)
        self.bradio_all = CanvasButton(self, (140, 240), text="All", command=lambda: self.set_oldnodes_filter("all"), width=30, height=20)
        
        # Initially hide the radio buttons
        self.update_oldnodes_radio_buttons()

        # bind events for mouse button pressed, mouse movement, and scrolling
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<Button-1>", self.mouse_click)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_release)
        self.canvas.bind("<MouseWheel>", self.mouse_zoom)
        self.canvas.bind("<Button-4>", self.mouse_zoom)
        self.canvas.bind("<Button-5>", self.mouse_zoom)
        self.bind('<Configure>', self.update_dimensions)
        self.last_mouse_down_position: Union[tuple, None] = None
        self.last_mouse_down_time: Union[float, None] = None
        self.mouse_click_position: Union[tuple, None] = None
        self.map_click_callback: Union[Callable, None] = None  # callback function for left click on map

        # movement fading
        self.fading_possible: bool = True
        self.move_velocity: Tuple[float, float] = (0, 0)
        self.last_move_time: Union[float, None] = None

        # describes the tile layout
        self.zoom: float = 0
        self.upper_left_tile_pos: Tuple[float, float] = (0, 0)  # in OSM coords
        self.lower_right_tile_pos: Tuple[float, float] = (0, 0)
        self.tile_size: int = 256  # in pixel
        self.last_zoom: float = self.zoom

        # canvas objects, image cache and standard empty images
        self.canvas_tile_array: List[List[CanvasTile]] = []
        self.canvas_marker_list: List[CanvasPositionMarker] = []
        self.canvas_path_list: List[CanvasPath] = []
        self.canvas_polygon_list: List[CanvasPolygon] = []

        self.tile_image_cache: Dict[str, PIL.ImageTk.PhotoImage] = {}
        self.empty_tile_image = ImageTk.PhotoImage(Image.new("RGB", (self.tile_size, self.tile_size), (190, 190, 190)))  # used for zooming and moving
        self.not_loaded_tile_image = ImageTk.PhotoImage(Image.new("RGB", (self.tile_size, self.tile_size), (250, 250, 250)))  # only used when image not found on tile server

        # tile server and database
        self.tile_server = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        self.serverur = "tile.openstreetmap.org"
        self.database_path = database_path
        self.use_database_only = use_database_only
        self.use_filter = use_filter
        self.overlay_tile_server: Union[str, None] = None
        self.max_zoom = max_zoom  # should be set according to tile server max zoom
        self.min_zoom: int = math.ceil(math.log2(math.ceil(self.width / self.tile_size)))  # min zoom at which map completely fills widget

        # pre caching for smoother movements (load tile images into cache at a certain radius around the pre_cache_position)
        self.pre_cache_position: Union[Tuple[float, float], None] = None
        self.pre_cache_thread = threading.Thread(daemon=True, target=self.pre_cache)
        self.pre_cache_thread.start()

        # image loading in background threads
        self.image_load_queue_tasks: List[tuple] = []  # task: ((zoom, x, y), canvas_tile_object)
        self.image_load_queue_results: List[tuple] = []  # result: ((zoom, x, y), canvas_tile_object, photo_image)
        self.after(10, self.update_canvas_tile_images)
        self.image_load_thread_pool: List[threading.Thread] = []

        # add background threads which load tile images from self.image_load_queue_tasks
        for i in range(14):
            image_load_thread = threading.Thread(daemon=True, target=self.load_images_background)
            image_load_thread.start()
            self.image_load_thread_pool.append(image_load_thread)

        # set initial position
        self.set_zoom(17)
        self.set_position(52.516268, 13.377695)  # Brandenburger Tor, Berlin

        # right click menu
        self.right_click_menu_commands: List[dict] = []  # list of dictionaries with "label": str, "command": Callable, "pass_coords": bool
        if sys.platform == "darwin":
            self.canvas.bind("<Button-2>", self.mouse_right_click)
        else:
            self.canvas.bind("<Button-3>", self.mouse_right_click)

        self.draw_rounded_corners()

    def destroy(self):
        self.running = False
        self.pre_cache_thread.join(0.2)
        for thread in self.image_load_thread_pool:
            thread.join(0.2)
        super().destroy()

    def draw_rounded_corners(self):
        self.canvas.delete("corner")

        if sys.platform.startswith("win"):
            pos_corr = -1
        else:
            pos_corr = 0

        if self.corner_radius > 0:
            radius = self.corner_radius
            self.canvas.create_arc(self.width - 2 * radius + 5 + pos_corr, self.height - 2 * radius + 5 + pos_corr,
                                   self.width + 5 + pos_corr, self.height + 5 + pos_corr,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=-90)
            self.canvas.create_arc(2 * radius - 5, self.height - 2 * radius + 5 + pos_corr, -5, self.height + 5 + pos_corr,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=180)
            self.canvas.create_arc(-5, -5, 2 * radius - 5, 2 * radius - 5,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=-270)
            self.canvas.create_arc(self.width - 2 * radius + 5 + pos_corr, -5, self.width + 5 + pos_corr, 2 * radius - 5,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=0)

    def update_dimensions(self, event):
        # only redraw if dimensions changed (for performance)
        if self.width != event.width or self.height != event.height:
            self.width = event.width
            self.height = event.height
            self.min_zoom = math.ceil(math.log2(math.ceil(self.width / self.tile_size)))

            self.set_zoom(self.zoom)  # call zoom to set the position vertices right
            self.draw_move()  # call move to draw new tiles or delete tiles
            self.draw_rounded_corners()

    def add_right_click_menu_command(self, label: str, command: Callable, pass_coords: bool = False) -> None:
        self.right_click_menu_commands.append({"label": label, "command": command, "pass_coords": pass_coords})

    def add_left_click_map_command(self, callback_function):
        self.map_click_callback = callback_function

    def convert_canvas_coords_to_decimal_coords(self, canvas_x: int, canvas_y: int) -> tuple:
        relative_mouse_x = canvas_x / self.canvas.winfo_width()
        relative_mouse_y = canvas_y / self.canvas.winfo_height()

        tile_mouse_x = self.upper_left_tile_pos[0] + (self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]) * relative_mouse_x
        tile_mouse_y = self.upper_left_tile_pos[1] + (self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]) * relative_mouse_y

        coordinate_mouse_pos = osm_to_decimal(tile_mouse_x, tile_mouse_y, round(self.zoom))
        return coordinate_mouse_pos

    def mouse_right_click(self, event):
        coordinate_mouse_pos = self.convert_canvas_coords_to_decimal_coords(event.x, event.y)

        def click_coordinates_event():
            try:
                pyperclip.copy(f"{coordinate_mouse_pos[0]:.7f} {coordinate_mouse_pos[1]:.7f}")
                tkinter.messagebox.showinfo(title="", message="Coordinates copied to clipboard!")

            except Exception as err:
                if sys.platform.startswith("linux"):
                    tkinter.messagebox.showinfo(title="", message="Error copying to clipboard.\n" + str(err) + "\n\nTry to install xclip:\n'sudo apt-get install xclip'")
                else:
                    tkinter.messagebox.showinfo(title="", message="Error copying to clipboard.\n" + str(err))

        m = tkinter.Menu(self, tearoff=0)
        m.add_command(label=f"{coordinate_mouse_pos[0]:.7f} {coordinate_mouse_pos[1]:.7f}",
                      command=click_coordinates_event)

        if len(self.right_click_menu_commands) > 0:
            m.add_separator()

        for command in self.right_click_menu_commands:
            if command["pass_coords"]:
                m.add_command(label=command["label"], command=partial(command["command"], coordinate_mouse_pos))
            else:
                m.add_command(label=command["label"], command=command["command"])

        m.tk_popup(event.x_root, event.y_root)  # display menu

    def set_overlay_tile_server(self, overlay_server: str):
        self.overlay_tile_server = overlay_server

    def set_tile_server(self, tile_server: str, tile_size: int = 256, max_zoom: int = 19):
        self.image_load_queue_tasks = []
        self.max_zoom = max_zoom
        self.tile_size = tile_size
        self.min_zoom = math.ceil(math.log2(math.ceil(self.width / self.tile_size)))
        self.tile_server = tile_server

        tmp = self.tile_server.split("/")
        self.serverur = f"{tmp[2]}"
        if "{" not in tmp[3]: self.serverur += f"/{tmp[3]}"

        self.tile_image_cache: Dict[str, PIL.ImageTk.PhotoImage] = {}
        self.canvas.delete("tile")
        self.image_load_queue_results = []
        self.draw_initial_array()

    def get_position(self) -> tuple:
        """ returns current middle position of map widget in decimal coordinates """

        return osm_to_decimal((self.lower_right_tile_pos[0] + self.upper_left_tile_pos[0]) / 2,
                              (self.lower_right_tile_pos[1] + self.upper_left_tile_pos[1]) / 2,
                              round(self.zoom))

    def fit_bounding_box(self, position_top_left: Tuple[float, float], position_bottom_right: Tuple[float, float]):
        # wait 200ms till method is called, because dimensions have to update first
        self.after(100, self._fit_bounding_box, position_top_left, position_bottom_right)

    def _fit_bounding_box(self, position_top_left: Tuple[float, float], position_bottom_right: Tuple[float, float]):
        """ Fit the map to contain a bounding box with the maximum zoom level possible. """

        # check positions
        if not (position_top_left[0] > position_bottom_right[0] and position_top_left[1] < position_bottom_right[1]):
            raise ValueError("incorrect bounding box positions, <must be top_left_position> <bottom_right_position>")

        # update idle-tasks to make sure current dimensions are correct
        self.update_idletasks()

        last_fitting_zoom_level = self.min_zoom
        middle_position_lat, middle_position_long = (position_bottom_right[0] + position_top_left[0]) / 2, (position_bottom_right[1] + position_top_left[1]) / 2

        # loop through zoom levels beginning at minimum zoom
        for zoom in range(self.min_zoom, self.max_zoom + 1):
            # calculate tile positions for bounding box
            middle_tile_position = decimal_to_osm(middle_position_lat, middle_position_long, zoom)
            top_left_tile_position = decimal_to_osm(*position_top_left, zoom)
            bottom_right_tile_position = decimal_to_osm(*position_bottom_right, zoom)

            # calculate tile positions for map corners
            calc_top_left_tile_position = (middle_tile_position[0] - ((self.width / 2) / self.tile_size),
                                           middle_tile_position[1] - ((self.height / 2) / self.tile_size))
            calc_bottom_right_tile_position = (middle_tile_position[0] + ((self.width / 2) / self.tile_size),
                                               middle_tile_position[1] + ((self.height / 2) / self.tile_size))

            # check if bounding box fits in map
            if calc_top_left_tile_position[0] < top_left_tile_position[0] and calc_top_left_tile_position[1] < top_left_tile_position[1] \
                    and calc_bottom_right_tile_position[0] > bottom_right_tile_position[0] and calc_bottom_right_tile_position[1] > bottom_right_tile_position[1]:
                # set last_fitting_zoom_level to current zoom becuase bounding box fits in map
                last_fitting_zoom_level = zoom
            else:
                # break because bounding box does not fit in map
                break

        # set zoom to last fitting zoom and position to middle position of bounding box
        self.set_zoom(last_fitting_zoom_level)
        self.set_position(middle_position_lat, middle_position_long)

    def set_position(self, deg_x, deg_y, text=None, marker=False, **kwargs) -> CanvasPositionMarker:
        """ set new middle position of map in decimal coordinates """

        # convert given decimal coordinates to OSM coordinates and set corner positions accordingly
        current_tile_position = decimal_to_osm(deg_x, deg_y, round(self.zoom))
        self.upper_left_tile_pos = (current_tile_position[0] - ((self.width / 2) / self.tile_size),
                                    current_tile_position[1] - ((self.height / 2) / self.tile_size))

        self.lower_right_tile_pos = (current_tile_position[0] + ((self.width / 2) / self.tile_size),
                                     current_tile_position[1] + ((self.height / 2) / self.tile_size))

        if marker is True:
            marker_object = self.set_marker(deg_x, deg_y, text, **kwargs)
        else:
            marker_object = None

        self.check_map_border_crossing()
        self.draw_initial_array()
        # self.draw_move() enough?

        return marker_object

    def set_address(self, address_string: str, marker: bool = False, text: str = None, **kwargs) -> CanvasPositionMarker:
        """ Function uses geocode service of OpenStreetMap (Nominatim).
            https://geocoder.readthedocs.io/providers/OpenStreetMap.html """

        result = geocoder.osm(address_string)

        if result.ok:

            # determine zoom level for result by bounding box
            if hasattr(result, "bbox"):
                zoom_not_possible = True

                for zoom in range(self.min_zoom, self.max_zoom + 1):
                    lower_left_corner = decimal_to_osm(*result.bbox['southwest'], zoom)
                    upper_right_corner = decimal_to_osm(*result.bbox['northeast'], zoom)
                    tile_width = upper_right_corner[0] - lower_left_corner[0]

                    if tile_width > math.floor(self.width / self.tile_size):
                        zoom_not_possible = False
                        self.set_zoom(zoom)
                        break

                if zoom_not_possible:
                    self.set_zoom(self.max_zoom)
            else:
                self.set_zoom(10)

            if text is None:
                try:
                    text = result.geojson['features'][0]['properties']['address']
                except:
                    text = address_string

            return self.set_position(*result.latlng, marker=marker, text=text, **kwargs)
        else:
            return False

    def set_marker(self, deg_x: float, deg_y: float, text: str = None, **kwargs) -> CanvasPositionMarker:
        marker = CanvasPositionMarker(self, (deg_x, deg_y), text=text, **kwargs)
        marker.draw()
        self.canvas_marker_list.append(marker)
        return marker

    def set_path(self, position_list: list, **kwargs) -> CanvasPath:
        path = CanvasPath(self, position_list, **kwargs)
        path.draw()
        self.canvas_path_list.append(path)
        return path

    def set_polygon(self, position: tuple, **kwargs) -> CanvasPolygon:
        polygon = CanvasPolygon(self, position, **kwargs)
        polygon.draw()
        self.canvas_polygon_list.append(polygon)
        return polygon

    def delete(self, map_object: any):
        if isinstance(map_object, (CanvasPath, CanvasPositionMarker, CanvasPolygon)):
            map_object.delete()
            if hasattr(map_object, 'deleted') and map_object.deleted:
                del map_object

    def delete_all_marker(self):
        for i in range(len(self.canvas_marker_list) - 1, -1, -1):
            self.canvas_marker_list[i].delete()
        self.canvas_marker_list = []

    def delete_all_path(self):
        for i in range(len(self.canvas_path_list) - 1, -1, -1):
            self.canvas_path_list[i].delete()
        self.canvas_path_list = []

    def delete_all_polygon(self):
        for i in range(len(self.canvas_polygon_list) - 1, -1, -1):
            self.canvas_polygon_list[i].delete()
        self.canvas_polygon_list = []

    def manage_z_order(self):
        self.canvas.lift("polygon")
        self.canvas.lift("path")
        self.canvas.lift("signal_text_bg")  # Text background above path lines
        self.canvas.lift("signal_text")     # Text above text background
        self.canvas.lift("signal")
        self.canvas.lift("marker")
        self.canvas.lift("marker_image")
        self.canvas.lift("corner")
        self.canvas.lift("button")

    # Lets see if we can reduce the memory footprint by removing the tile_image_cache that we are not using
    def is_within_viewport(self, x, y):
        """ Check if the tile (x, y, zoom) is within the viewport bounds. """
        min_x, max_x, min_y, max_y = self.viewport_bounds
        return min_x <= x <= max_x and min_y <= y <= max_y

    def update_cache(self):
        """ Update the cache by removing tiles outside the viewport. """
        keys_to_delete = []
        for key in self.tile_image_cache.keys():
            key_zoom, key_x, key_y = map(int, key.split('_'))
            if key_zoom == self.zoom and not self.is_within_viewport(key_x, key_y):
                keys_to_delete.append(key)
            elif key_zoom != self.zoom:
                keys_to_delete.append(key)

        if len(keys_to_delete):
            print(f"Deleting {len(keys_to_delete)} / {len(self.tile_image_cache)} tiles from cache")
            for key in keys_to_delete:
                image = self.tile_image_cache[key]
                del image
                del self.tile_image_cache[key]

    def pre_cache(self):
        """ single threaded pre-chace tile images in area of self.pre_cache_position """

        last_pre_cache_position = None
        radius = 1
        zoom = round(self.zoom)

        if self.database_path is not None:
            db_connection = sqlite3.connect(self.database_path, timeout=250)
            self.db_cursor = db_connection.cursor()
            # create tables if it not exists
            create_server_table = """CREATE TABLE IF NOT EXISTS server (
                                            url VARCHAR(300) PRIMARY KEY NOT NULL,
                                            max_zoom INTEGER NOT NULL);"""

            create_tiles_table = """CREATE TABLE IF NOT EXISTS tiles (
                                            zoom INTEGER NOT NULL,
                                            x INTEGER NOT NULL,
                                            y INTEGER NOT NULL,
                                            server VARCHAR(300) NOT NULL,
                                            tile_image BLOB NOT NULL,
                                            CONSTRAINT fk_server FOREIGN KEY (server) REFERENCES server (url),
                                            CONSTRAINT pk_tiles PRIMARY KEY (zoom, x, y, server));"""

            create_sections_table = """CREATE TABLE IF NOT EXISTS sections (
                                                position_a VARCHAR(100) NOT NULL,
                                                position_b VARCHAR(100) NOT NULL,
                                                zoom_a INTEGER NOT NULL,
                                                zoom_b INTEGER NOT NULL,
                                                server VARCHAR(300) NOT NULL,
                                                CONSTRAINT fk_server FOREIGN KEY (server) REFERENCES server (url),
                                                CONSTRAINT pk_tiles PRIMARY KEY (position_a, position_b, zoom_a, zoom_b, server));"""

            self.db_cursor.execute(create_server_table)
            self.db_cursor.execute(create_tiles_table)
            self.db_cursor.execute(create_sections_table)
            self.db_cursor.execute("PRAGMA journal_mode=OFF")
            self.db_cursor.connection.commit()
            if self.tile_server != '':
                self.db_cursor.execute(f"INSERT OR IGNORE INTO server (url, max_zoom) VALUES (?, ?);", (self.serverur, self.max_zoom))
                self.db_cursor.connection.commit()
        else:
            self.db_cursor = None

        while self.running:
            if last_pre_cache_position != self.pre_cache_position:
                last_pre_cache_position = self.pre_cache_position
                zoom = round(self.zoom)
                radius = 1

            if last_pre_cache_position is not None and radius <= 3:
                # pre cache top and bottom row
                for x in range(self.pre_cache_position[0] - radius, self.pre_cache_position[0] + radius + 1):
                    if f"{zoom}{x}{self.pre_cache_position[1] + radius}" not in self.tile_image_cache:
                        self.request_image(zoom, x, self.pre_cache_position[1] + radius, db_cursor=self.db_cursor)
                    if f"{zoom}{x}{self.pre_cache_position[1] - radius}" not in self.tile_image_cache:
                        self.request_image(zoom, x, self.pre_cache_position[1] - radius, db_cursor=self.db_cursor)

                # pre cache left and right column
                for y in range(self.pre_cache_position[1] - radius, self.pre_cache_position[1] + radius + 1):
                    if f"{zoom}{self.pre_cache_position[0] + radius}{y}" not in self.tile_image_cache:
                        self.request_image(zoom, self.pre_cache_position[0] + radius, y, db_cursor=self.db_cursor)
                    if f"{zoom}{self.pre_cache_position[0] - radius}{y}" not in self.tile_image_cache:
                        self.request_image(zoom, self.pre_cache_position[0] - radius, y, db_cursor=self.db_cursor)

                # Example usage within your existing code
                self.viewport_bounds = (
                    self.pre_cache_position[0] - radius, 
                    self.pre_cache_position[0] + radius, 
                    self.pre_cache_position[1] - radius, 
                    self.pre_cache_position[1] + radius
                )

                # raise the radius
                radius += 1
            else:
                time.sleep(0.1)

            # 10_000 images = 80 MB RAM-usage
            if len(self.tile_image_cache) > 10_000:  # delete random tiles if cache is too large
                # create list with keys to delete
                keys_to_delete = []
                for key in self.tile_image_cache.keys():
                    if len(self.tile_image_cache) - len(keys_to_delete) > 10_000:
                        keys_to_delete.append(key)

                # delete keys in list so that len(self.tile_image_cache) == 10_000
                for key in keys_to_delete:
                    del self.tile_image_cache[key]

    def execute_with_retry(tmp, db_cursor, zoom, x, y, server, data):
        insert_tile_cmd = """INSERT OR IGNORE INTO tiles (zoom, x, y, server, tile_image) VALUES (?, ?, ?, ?, ?);"""
        for attempt in range(3):
            try:
                db_cursor.execute(insert_tile_cmd, (zoom, x, y, server, data))
                db_cursor.connection.commit()
                return
            except sqlite3.OperationalError as err:
                if "database is locked" in str(err):
                    time.sleep(0.25)
                else:
                    raise
        raise sqlite3.OperationalError("Failed to execute command after retries due to database lock.")

    def request_image(self, zoom: int, x: int, y: int, db_cursor=None) -> ImageTk.PhotoImage:
        # if database is available check first if tile is in database, if not try to use server
        if db_cursor is not None:
            try:
                db_cursor.execute("SELECT t.tile_image FROM tiles t WHERE t.zoom=? AND t.x=? AND t.y=? AND t.server=?;",
                                  (zoom, x, y, self.serverur))
                result = db_cursor.fetchone()
                if result is not None:
                    image = Image.open(io.BytesIO(result[0]))
                    image_tk = ImageTk.PhotoImage(image)
                    self.tile_image_cache[f"{zoom}_{x}_{y}"] = image_tk
                    return image_tk
            except Exception:
                print("Error loading tile from database")

        if self.tile_server == "":
            return self.empty_tile_image

        # try to get the tile from the server
        try:
            url = self.tile_server.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
            response = requests.get(url, stream=True, headers={"User-Agent": "TkinterMapView"})
            image_org = Image.open(io.BytesIO(response.content))
            if image_org.mode != 'RGB': image_org = image_org.convert('RGB')

            if self.use_filter:
                # Making a darkmode map from a light one like using the css filter: invert(0.9) hue-rotate(170deg) brightness(1.5) contrast(1.2) saturate(0.3);
                # Invert colors
                inverted_image = ImageOps.invert(image_org)
                image_org = ImageChops.blend(image_org, inverted_image, 0.9)
                # Adjust brightness
                enhancer = ImageEnhance.Brightness(image_org)
                image_org = enhancer.enhance(1.1)
                # Adjust contrast
                enhancer = ImageEnhance.Contrast(image_org)
                image_org = enhancer.enhance(1.2)
                # Adjust saturation
                enhancer = ImageEnhance.Color(image_org)
                image_org = enhancer.enhance(0.12)

            output = io.BytesIO()

            # Save to Disk 
            # folder_path = os.path.join('jaramaps', str(zoom), str(x))
            # os.makedirs(folder_path, exist_ok=True)
            # file_path = os.path.join(folder_path, str(y) + ".png")
            # image_org.save(file_path, format="PNG")
            # output.seek(0)  # Reset the stream position to the beginning

            image_org.save(output, format="JPEG", quality=72)  # Save the (possibly filtered) image to output
            output.seek(0)  # Reset the stream position to the beginning

            if db_cursor is not None and output is not None:
                try:
                    self.execute_with_retry(db_cursor, zoom, x, y, self.serverur, output.getvalue())
                except Exception as err:
                    print(f"Error inserting tile into database: {err}")

            if self.overlay_tile_server is not None:
                url = self.overlay_tile_server.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
                image_overlay = Image.open(requests.get(url, stream=True, headers={"User-Agent": "TkinterMapView"}).raw)
                image = image.convert("RGBA")
                image_overlay = image_overlay.convert("RGBA")

                if image_overlay.size is not (self.tile_size, self.tile_size):
                    image_overlay = image_overlay.resize((self.tile_size, self.tile_size), Image.ANTIALIAS)

                image.paste(image_overlay, (0, 0), image_overlay)

            if self.running:
                image = Image.open(output)
                image_tk = ImageTk.PhotoImage(image)
            else:
                return self.empty_tile_image

            self.tile_image_cache[f"{zoom}_{x}_{y}"] = image_tk
            return image_tk

        except PIL.UnidentifiedImageError:  # image does not exist for given coordinates
            self.tile_image_cache[f"{zoom}_{x}_{y}"] = self.empty_tile_image
            return self.empty_tile_image

        except requests.exceptions.ConnectionError:
            return self.empty_tile_image

        except Exception:
            return self.empty_tile_image

    def get_tile_image_from_cache(self, zoom: int, x: int, y: int):
        if f"{zoom}_{x}_{y}" not in self.tile_image_cache:
            return False
        else:
            return self.tile_image_cache[f"{zoom}_{x}_{y}"]

    def load_images_background(self):
        if self.database_path is not None:
            db_connection = sqlite3.connect(self.database_path)
            db_cursor = db_connection.cursor()
        else:
            db_cursor = None

        while self.running:
            if len(self.image_load_queue_tasks) > 0:
                # task queue structure: [((zoom, x, y), corresponding canvas tile object), ... ]
                task = self.image_load_queue_tasks.pop()

                zoom = task[0][0]
                x, y = task[0][1], task[0][2]
                canvas_tile = task[1]

                image = self.get_tile_image_from_cache(zoom, x, y)
                if image is False:
                    image = self.request_image(zoom, x, y, db_cursor=db_cursor)
                    if image is None:
                        self.image_load_queue_tasks.append(task)
                        continue

                # result queue structure: [((zoom, x, y), corresponding canvas tile object, tile image), ... ]
                self.image_load_queue_results.append(((zoom, x, y), canvas_tile, image))

            else:
                time.sleep(0.01)

    def update_canvas_tile_images(self):
        menow = int(time.time())
        while len(self.image_load_queue_results) > 0 and self.running:
            # result queue structure: [((zoom, x, y), corresponding canvas tile object, tile image), ... ]
            result = self.image_load_queue_results.pop(0)

            zoom, x, y = result[0][0], result[0][1], result[0][2]
            canvas_tile = result[1]
            image = result[2]

            # check if zoom level of result is still up to date, otherwise don't update image
            if zoom == round(self.zoom):
                canvas_tile.set_image(image)
            
            self.pausecount = menow

        if len(self.image_load_queue_results) == 0 and self.running:
            if self.pausecount == 0 or menow - self.pausecount > 200:
                self.pausecount = menow
                self.update_cache()

        # This function calls itself every 10 ms with tk.after() so that the image updates come
        # from the main GUI thread, because tkinter can only be updated from the main thread.
        if self.running:
            self.after(10, self.update_canvas_tile_images)

    def insert_row(self, insert: int, y_name_position: int):

        for x_pos in range(len(self.canvas_tile_array)):
            tile_name_position = self.canvas_tile_array[x_pos][0].tile_name_position[0], y_name_position

            image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)
            if image is False:
                canvas_tile = CanvasTile(self, self.not_loaded_tile_image, tile_name_position)
                self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), canvas_tile))
            else:
                canvas_tile = CanvasTile(self, image, tile_name_position)

            canvas_tile.draw()

            self.canvas_tile_array[x_pos].insert(insert, canvas_tile)

    def insert_column(self, insert: int, x_name_position: int):
        canvas_tile_column = []

        for y_pos in range(len(self.canvas_tile_array[0])):
            tile_name_position = x_name_position, self.canvas_tile_array[0][y_pos].tile_name_position[1]

            image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)
            if image is False:
                # image is not in image cache, load blank tile and append position to image_load_queue
                canvas_tile = CanvasTile(self, self.not_loaded_tile_image, tile_name_position)
                self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), canvas_tile))
            else:
                # image is already in cache
                canvas_tile = CanvasTile(self, image, tile_name_position)

            canvas_tile.draw()

            canvas_tile_column.append(canvas_tile)

        self.canvas_tile_array.insert(insert, canvas_tile_column)

    def draw_initial_array(self):
        self.image_load_queue_tasks = []

        x_tile_range = math.ceil(self.lower_right_tile_pos[0]) - math.floor(self.upper_left_tile_pos[0])
        y_tile_range = math.ceil(self.lower_right_tile_pos[1]) - math.floor(self.upper_left_tile_pos[1])

        # upper left tile name position
        upper_left_x = math.floor(self.upper_left_tile_pos[0])
        upper_left_y = math.floor(self.upper_left_tile_pos[1])

        for x_pos in range(len(self.canvas_tile_array)):
            for y_pos in range(len(self.canvas_tile_array[0])):
                self.canvas_tile_array[x_pos][y_pos].__del__()

        # create tile array with size (x_tile_range x y_tile_range)
        self.canvas_tile_array = []

        for x_pos in range(x_tile_range):
            canvas_tile_column = []

            for y_pos in range(y_tile_range):
                tile_name_position = upper_left_x + x_pos, upper_left_y + y_pos

                image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)
                if image is False:
                    # image is not in image cache, load blank tile and append position to image_load_queue
                    canvas_tile = CanvasTile(self, self.not_loaded_tile_image, tile_name_position)
                    self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), canvas_tile))
                else:
                    # image is already in cache
                    canvas_tile = CanvasTile(self, image, tile_name_position)

                canvas_tile_column.append(canvas_tile)

            self.canvas_tile_array.append(canvas_tile_column)

        # draw all canvas tiles
        for x_pos in range(len(self.canvas_tile_array)):
            for y_pos in range(len(self.canvas_tile_array[0])):
                self.canvas_tile_array[x_pos][y_pos].draw()

        # draw other objects on canvas
        for marker in self.canvas_marker_list:
            marker.draw()
        for path in self.canvas_path_list:
            path.draw()
        for polygon in self.canvas_polygon_list:
            polygon.draw()

        # update pre-cache position
        self.pre_cache_position = (round((self.upper_left_tile_pos[0] + self.lower_right_tile_pos[0]) / 2),
                                   round((self.upper_left_tile_pos[1] + self.lower_right_tile_pos[1]) / 2))

    def draw_move(self, called_after_zoom: bool = False):

        if self.canvas_tile_array:

            # insert or delete rows on top
            top_y_name_position = self.canvas_tile_array[0][0].tile_name_position[1]
            top_y_diff = self.upper_left_tile_pos[1] - top_y_name_position
            if top_y_diff <= 0:
                for y_diff in range(1, math.ceil(-top_y_diff) + 1):
                    self.insert_row(insert=0, y_name_position=top_y_name_position - y_diff)
            elif top_y_diff >= 1:
                for y_diff in range(1, math.ceil(top_y_diff)):
                    for x in range(len(self.canvas_tile_array) - 1, -1, -1):
                        if len(self.canvas_tile_array[x]) > 1:
                            self.canvas_tile_array[x][0].delete()
                            del self.canvas_tile_array[x][0]

            # insert or delete columns on left
            left_x_name_position = self.canvas_tile_array[0][0].tile_name_position[0]
            left_x_diff = self.upper_left_tile_pos[0] - left_x_name_position
            if left_x_diff <= 0:
                for x_diff in range(1, math.ceil(-left_x_diff) + 1):
                    self.insert_column(insert=0, x_name_position=left_x_name_position - x_diff)
            elif left_x_diff >= 1:
                for x_diff in range(1, math.ceil(left_x_diff)):
                    if len(self.canvas_tile_array) > 1:
                        for y in range(len(self.canvas_tile_array[0]) - 1, -1, -1):
                            self.canvas_tile_array[0][y].delete()
                            del self.canvas_tile_array[0][y]
                        del self.canvas_tile_array[0]

            # insert or delete rows on bottom
            bottom_y_name_position = self.canvas_tile_array[0][-1].tile_name_position[1]
            bottom_y_diff = self.lower_right_tile_pos[1] - bottom_y_name_position
            if bottom_y_diff >= 1:
                for y_diff in range(1, math.ceil(bottom_y_diff)):
                    self.insert_row(insert=len(self.canvas_tile_array[0]), y_name_position=bottom_y_name_position + y_diff)
            elif bottom_y_diff <= 1:
                for y_diff in range(1, math.ceil(-bottom_y_diff) + 1):
                    for x in range(len(self.canvas_tile_array) - 1, -1, -1):
                        if len(self.canvas_tile_array[x]) > 1:
                            self.canvas_tile_array[x][-1].delete()
                            del self.canvas_tile_array[x][-1]

            # insert or delete columns on right
            right_x_name_position = self.canvas_tile_array[-1][0].tile_name_position[0]
            right_x_diff = self.lower_right_tile_pos[0] - right_x_name_position
            if right_x_diff >= 1:
                for x_diff in range(1, math.ceil(right_x_diff)):
                    self.insert_column(insert=len(self.canvas_tile_array), x_name_position=right_x_name_position + x_diff)
            elif right_x_diff <= 1:
                for x_diff in range(1, math.ceil(-right_x_diff) + 1):
                    if len(self.canvas_tile_array) > 1:
                        for y in range(len(self.canvas_tile_array[-1]) - 1, -1, -1):
                            self.canvas_tile_array[-1][y].delete()
                            del self.canvas_tile_array[-1][y]
                        del self.canvas_tile_array[-1]

            # draw all canvas tiles
            for x_pos in range(len(self.canvas_tile_array)):
                for y_pos in range(len(self.canvas_tile_array[0])):
                    self.canvas_tile_array[x_pos][y_pos].draw()

            # draw other objects on canvas
            for marker in self.canvas_marker_list:
                marker.draw()
            for path in self.canvas_path_list:
                path.draw(move=not called_after_zoom)
            for polygon in self.canvas_polygon_list:
                polygon.draw(move=not called_after_zoom)

            # update pre-cache position
            self.pre_cache_position = (round((self.upper_left_tile_pos[0] + self.lower_right_tile_pos[0]) / 2),
                                       round((self.upper_left_tile_pos[1] + self.lower_right_tile_pos[1]) / 2))

    def draw_zoom(self):

        if self.canvas_tile_array:
            # clear tile image loading queue, so that no old images from other zoom levels get displayed
            self.image_load_queue_tasks = []

            # upper left tile name position
            upper_left_x = math.floor(self.upper_left_tile_pos[0])
            upper_left_y = math.floor(self.upper_left_tile_pos[1])

            for x_pos in range(len(self.canvas_tile_array)):
                for y_pos in range(len(self.canvas_tile_array[0])):

                    tile_name_position = upper_left_x + x_pos, upper_left_y + y_pos

                    image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)
                    if image is False:
                        image = self.not_loaded_tile_image
                        # noinspection PyCompatibility
                        self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), self.canvas_tile_array[x_pos][y_pos]))

                    self.canvas_tile_array[x_pos][y_pos].set_image_and_position(image, tile_name_position)

            self.pre_cache_position = (round((self.upper_left_tile_pos[0] + self.lower_right_tile_pos[0]) / 2),
                                       round((self.upper_left_tile_pos[1] + self.lower_right_tile_pos[1]) / 2))

            self.draw_move(called_after_zoom=True)

    def mouse_move(self, event):
        # calculate moving difference from last mouse position
        mouse_move_x = self.last_mouse_down_position[0] - event.x
        mouse_move_y = self.last_mouse_down_position[1] - event.y

        # set move velocity for movement fading out
        delta_t = time.time() - self.last_mouse_down_time
        if delta_t == 0:
            self.move_velocity = (0, 0)
        else:
            self.move_velocity = (mouse_move_x / delta_t, mouse_move_y / delta_t)

        # save current mouse position for next move event
        self.last_mouse_down_position = (event.x, event.y)
        self.last_mouse_down_time = time.time()

        # calculate exact tile size of widget
        tile_x_range = self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]
        tile_y_range = self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]

        # calculate the movement in tile coordinates
        tile_move_x = (mouse_move_x / self.width) * tile_x_range
        tile_move_y = (mouse_move_y / self.height) * tile_y_range

        # calculate new corner tile positions
        self.lower_right_tile_pos = (self.lower_right_tile_pos[0] + tile_move_x, self.lower_right_tile_pos[1] + tile_move_y)
        self.upper_left_tile_pos = (self.upper_left_tile_pos[0] + tile_move_x, self.upper_left_tile_pos[1] + tile_move_y)

        self.check_map_border_crossing()
        self.draw_move()

    def mouse_click(self, event):
        self.fading_possible = False

        self.mouse_click_position = (event.x, event.y)

        # save mouse position where mouse is pressed down for moving
        self.last_mouse_down_position = (event.x, event.y)
        self.last_mouse_down_time = time.time()

    def mouse_release(self, event):
        self.fading_possible = True
        self.last_move_time = time.time()

        # check if mouse moved after mouse click event
        if self.mouse_click_position == (event.x, event.y):
            # mouse didn't move
            if self.map_click_callback is not None:
                # get decimal coords of current mouse position
                coordinate_mouse_pos = self.convert_canvas_coords_to_decimal_coords(event.x, event.y)
                self.map_click_callback(coordinate_mouse_pos)
        else:
            # mouse was moved, start fading animation
            self.after(1, self.fading_move)

    def fading_move(self):
        delta_t = time.time() - self.last_move_time
        self.last_move_time = time.time()

        # only do fading when at least 10 fps possible and fading is possible (no mouse movement at the moment)
        if delta_t < 0.1 and self.fading_possible is True:

            # calculate fading velocity
            mouse_move_x = self.move_velocity[0] * delta_t
            mouse_move_y = self.move_velocity[1] * delta_t

            # lower the fading velocity
            lowering_factor = 2 ** (-9 * delta_t)
            self.move_velocity = (self.move_velocity[0] * lowering_factor, self.move_velocity[1] * lowering_factor)

            # calculate exact tile size of widget
            tile_x_range = self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]
            tile_y_range = self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]

            # calculate the movement in tile coordinates
            tile_move_x = (mouse_move_x / self.width) * tile_x_range
            tile_move_y = (mouse_move_y / self.height) * tile_y_range

            # calculate new corner tile positions
            self.lower_right_tile_pos = (self.lower_right_tile_pos[0] + tile_move_x, self.lower_right_tile_pos[1] + tile_move_y)
            self.upper_left_tile_pos = (self.upper_left_tile_pos[0] + tile_move_x, self.upper_left_tile_pos[1] + tile_move_y)

            self.check_map_border_crossing()
            self.draw_move()

            if abs(self.move_velocity[0]) > 1 or abs(self.move_velocity[1]) > 1:
                if self.running:
                    self.after(1, self.fading_move)

    def set_zoom(self, zoom: int, relative_pointer_x: float = 0.5, relative_pointer_y: float = 0.5):

        mouse_tile_pos_x = self.upper_left_tile_pos[0] + (self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]) * relative_pointer_x
        mouse_tile_pos_y = self.upper_left_tile_pos[1] + (self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]) * relative_pointer_y

        current_deg_mouse_position = osm_to_decimal(mouse_tile_pos_x,
                                                    mouse_tile_pos_y,
                                                    round(self.zoom))
        self.zoom = zoom

        if self.zoom > self.max_zoom:
            self.zoom = self.max_zoom
        if self.zoom < self.min_zoom:
            self.zoom = self.min_zoom

        current_tile_mouse_position = decimal_to_osm(*current_deg_mouse_position, round(self.zoom))

        self.upper_left_tile_pos = (current_tile_mouse_position[0] - relative_pointer_x * (self.width / self.tile_size),
                                    current_tile_mouse_position[1] - relative_pointer_y * (self.height / self.tile_size))

        self.lower_right_tile_pos = (current_tile_mouse_position[0] + (1 - relative_pointer_x) * (self.width / self.tile_size),
                                     current_tile_mouse_position[1] + (1 - relative_pointer_y) * (self.height / self.tile_size))

        if round(self.zoom) != round(self.last_zoom):
            self.check_map_border_crossing()
            self.draw_zoom()
            self.last_zoom = round(self.zoom)

            # Custom addon to dynammicly scale arrow heads in paths
            zoom_level = round(self.zoom)
            zoom_factor = zoom_level * 0.35
            new_length = round((4 + zoom_factor) * (zoom_level / 18), 2)
            new_width  = round((8 + zoom_factor) * (zoom_level / 18), 2)
            new_wing   = round((1 + zoom_factor) * (zoom_level / 18), 2)
            self.canvas.itemconfigure("path", arrowshape=(new_length, new_width, new_wing))

    def mouse_zoom(self, event):
        relative_mouse_x = event.x / self.width  # mouse pointer position on map (x=[0..1], y=[0..1])
        relative_mouse_y = event.y / self.height

        if sys.platform == "darwin":
            new_zoom = self.zoom + event.delta * 0.1
        elif sys.platform.startswith("win"):
            new_zoom = self.zoom + event.delta * 0.01
        elif event.num == 4:
            new_zoom = self.zoom + 1
        elif event.num == 5:
            new_zoom = self.zoom - 1
        else:
            new_zoom = self.zoom + event.delta * 0.1

        self.set_zoom(new_zoom, relative_pointer_x=relative_mouse_x, relative_pointer_y=relative_mouse_y)

    def check_map_border_crossing(self):
        diff_x, diff_y = 0, 0
        if self.upper_left_tile_pos[0] < 0:
            diff_x += 0 - self.upper_left_tile_pos[0]

        if self.upper_left_tile_pos[1] < 0:
            diff_y += 0 - self.upper_left_tile_pos[1]
        if self.lower_right_tile_pos[0] > 2 ** round(self.zoom):
            diff_x -= self.lower_right_tile_pos[0] - (2 ** round(self.zoom))
        if self.lower_right_tile_pos[1] > 2 ** round(self.zoom):
            diff_y -= self.lower_right_tile_pos[1] - (2 ** round(self.zoom))

        self.upper_left_tile_pos = self.upper_left_tile_pos[0] + diff_x, self.upper_left_tile_pos[1] + diff_y
        self.lower_right_tile_pos = self.lower_right_tile_pos[0] + diff_x, self.lower_right_tile_pos[1] + diff_y

    def button_zoom_in(self):
        # zoom into middle of map
        self.set_zoom(self.zoom + 1, relative_pointer_x=0.5, relative_pointer_y=0.5)

    def button_zoom_out(self):
        # zoom out of middle of map
        self.set_zoom(self.zoom - 1, relative_pointer_x=0.5, relative_pointer_y=0.5)

    def toggle_trail(self):
        self.draw_trail = not self.draw_trail
        if self.draw_trail:
            self.btoggle_trail.config(fg="#e63030")
        else:
            self.btoggle_trail.config(fg="gray")
        self.draw_move()

    def toggle_range(self):
        self.draw_range = not self.draw_range
        if self.draw_range:
            self.btoggle_range.config(fg="#e08700")
        else:
            self.btoggle_range.config(fg="gray")
        self.draw_move()

    def toggle_heard(self):
        self.draw_heard = not self.draw_heard
        if self.draw_heard:
            self.btoggle_heard.config(fg="#00c27e")
        else:
            self.btoggle_heard.config(fg="gray")
        self.draw_move()
    
    def toggle_oldnodes(self):
        self.draw_oldnodes = not self.draw_oldnodes
        if self.draw_oldnodes:
            self.btoggle_oldnodes.config(fg="white")
        else:
            self.btoggle_oldnodes.config(fg="gray")
        self.update_oldnodes_radio_buttons()
        self.draw_move()

    def get_oldnodes_filter(self):
        """Get the current oldnodes filter setting"""
        return self.oldnodes_filter

    def set_oldnodes_filter(self, filter_type):
        """Set the oldnodes filter type and update radio button states"""

        self.oldnodes_filter = filter_type
        self.update_oldnodes_radio_buttons()
        self.draw_move()

    def update_oldnodes_radio_buttons(self):
        """Update the visibility and state of oldnodes radio buttons"""
        if self.draw_oldnodes:
            # Show radio buttons
            self.bradio_7days.show()
            self.bradio_1month.show()
            self.bradio_all.show()
            
            # Update button states based on current selection
            if self.oldnodes_filter == "7days":
                self.bradio_7days.config(fg="white", bg="#404040")
                self.bradio_1month.config(fg="gray", bg="#2D2D2D")
                self.bradio_all.config(fg="gray", bg="#2D2D2D")
            elif self.oldnodes_filter == "1month":
                self.bradio_7days.config(fg="gray", bg="#2D2D2D")
                self.bradio_1month.config(fg="white", bg="#404040")
                self.bradio_all.config(fg="gray", bg="#2D2D2D")
            else:  # "all"
                self.bradio_7days.config(fg="gray", bg="#2D2D2D")
                self.bradio_1month.config(fg="gray", bg="#2D2D2D")
                self.bradio_all.config(fg="white", bg="#404040")
        else:
            # Hide radio buttons
            self.bradio_7days.hide()
            self.bradio_1month.hide()
            self.bradio_all.hide()
