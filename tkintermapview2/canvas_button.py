import tkinter
import sys
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .map_widget import TkinterMapView


class CanvasButton:
    def __init__(self, map_widget: "TkinterMapView", canvas_position, text="", command=None, fg="grey", width=None, height=None, bg="gray20"):
        self.map_widget = map_widget
        self.canvas_position = canvas_position

        if sys.platform == "darwin":
            self.width = width or 16
            self.height = height or 16
            self.border_width = 16
        else:
            self.width = width or 29
            self.height = height or 29
            self.border_width = 1

        self.text = text
        self.command = command
        self.fg = fg
        self.bg = bg
        self.canvas_rect = None
        self.canvas_text = None
        self.is_visible = True

        self.draw()

    def config(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
            if key == "fg" and self.canvas_text is not None:
                self.map_widget.canvas.itemconfig(self.canvas_text, fill=value)
            elif key == "bg" and self.canvas_rect is not None:
                self.map_widget.canvas.itemconfig(self.canvas_rect, fill=value)

    def show(self):
        """Show the button"""
        if self.canvas_rect is not None:
            self.map_widget.canvas.itemconfig(self.canvas_rect, state="normal")
        if self.canvas_text is not None:
            self.map_widget.canvas.itemconfig(self.canvas_text, state="normal")
        self.is_visible = True

    def hide(self):
        """Hide the button"""
        if self.canvas_rect is not None:
            self.map_widget.canvas.itemconfig(self.canvas_rect, state="hidden")
        if self.canvas_text is not None:
            self.map_widget.canvas.itemconfig(self.canvas_text, state="hidden")
        self.is_visible = False

    def click(self, event):
        if self.command is not None:
            self.command()

    def hover_on(self, event):
        if self.canvas_rect is not None:
            self.map_widget.canvas.itemconfig(self.canvas_rect, fill="gray50", outline="gray10")
            self.map_widget.canvas.itemconfig(self.canvas_text, fill="grey10")

            if sys.platform == "darwin":
                self.map_widget.canvas.config(cursor="pointinghand")
            elif sys.platform.startswith("win"):
                self.map_widget.canvas.config(cursor="hand2")
            else:
                self.map_widget.canvas.config(cursor="hand2")  # not tested what it looks like on Linux!

    def hover_off(self, event):
        if self.canvas_rect is not None:
            self.map_widget.canvas.itemconfig(self.canvas_rect, fill=self.bg, outline="gray10")
            self.map_widget.canvas.itemconfig(self.canvas_text, fill=self.fg)
        
        self.map_widget.canvas.config(cursor="arrow")

    def draw(self):
        self.canvas_rect = self.map_widget.canvas.create_polygon(self.canvas_position[0], self.canvas_position[1],
                                                                 self.canvas_position[0] + self.width, self.canvas_position[1],
                                                                 self.canvas_position[0] + self.width,
                                                                 self.canvas_position[1] + self.height,
                                                                 self.canvas_position[0], self.canvas_position[1] + self.height,
                                                                 width=self.border_width,
                                                                 fill=self.bg, outline="gray10",
                                                                 tag="button")

        self.canvas_text = self.map_widget.canvas.create_text(math.floor(self.canvas_position[0] + self.width / 2),
                                                              math.floor(self.canvas_position[1] + self.height / 2),
                                                              anchor=tkinter.CENTER,
                                                              text=self.text,
                                                              fill=self.fg,
                                                              font="Tahoma 10" if self.width < 35 else "Tahoma 14",
                                                              tag="button")

        self.map_widget.canvas.tag_bind(self.canvas_rect, "<Button-1>", self.click)
        self.map_widget.canvas.tag_bind(self.canvas_text, "<Button-1>", self.click)
        self.map_widget.canvas.tag_bind(self.canvas_rect, "<Enter>", self.hover_on)
        self.map_widget.canvas.tag_bind(self.canvas_text, "<Enter>", self.hover_on)
        self.map_widget.canvas.tag_bind(self.canvas_rect, "<Leave>", self.hover_off)
        self.map_widget.canvas.tag_bind(self.canvas_text, "<Leave>", self.hover_off)
