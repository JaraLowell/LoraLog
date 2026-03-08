# LoraLogCore.py
# This script serves as a GUI for monitoring and interacting with Lora packets. It utilizes tkinter/customtkinter and TkinterMapView for rendering the interface.

import tkinter as tk
from tkinter import scrolledtext
from tkinter import messagebox
from customtkinter import CTk, CTkFrame, CTkLabel, CTkEntry, CTkButton
from TkinterMapView import TkinterMapView

class LoraLogApp(CTk):
    def __init__(self):
        super().__init__()
        self.title('LoraLog Panel')
        self.geometry('800x600')  # Width x Height

        # Left Panel for Live Packets
        self.packets_frame = CTkFrame(self)
        self.packets_frame.pack(side='left', fill='y')
        self.packets_label = CTkLabel(self.packets_frame, text='Live Packets')
        self.packets_label.pack()
        self.packets_listbox = tk.Listbox(self.packets_frame)
        self.packets_listbox.pack(fill='both', expand=True)

        # Middle Panel for Map
        self.map_frame = CTkFrame(self)
        self.map_frame.pack(side='left', fill='both', expand=True)
        self.map_view = TkinterMapView(self.map_frame)
        self.map_view.pack(fill='both', expand=True)

        # Right Panel for Active Nodes
        self.nodes_frame = CTkFrame(self)
        self.nodes_frame.pack(side='right', fill='y')
        self.nodes_label = CTkLabel(self.nodes_frame, text='Active Nodes (Last 3 Hours)')
        self.nodes_label.pack()
        self.nodes_listbox = tk.Listbox(self.nodes_frame)
        self.nodes_listbox.pack(fill='both', expand=True)

        # Bottom Panel for Public Chat
        self.chat_frame = CTkFrame(self)
        self.chat_frame.pack(side='bottom', fill='x')
        self.chat_label = CTkLabel(self.chat_frame, text='Public Chat')
        self.chat_label.pack()
        self.chat_window = scrolledtext.ScrolledText(self.chat_frame, height=10)
        self.chat_window.pack(fill='both', expand=True)
        self.input_entry = CTkEntry(self.chat_frame)
        self.input_entry.pack(side='left', fill='x', expand=True)
        self.send_button = CTkButton(self.chat_frame, text='Send', command=self.send_message)
        self.send_button.pack(side='right')

    def send_message(self):
        message = self.input_entry.get()
        if message:
            self.chat_window.insert(tk.END, f'You: {message}\n')
            self.input_entry.delete(0, tk.END)
            # Placeholder for sending message logic

    def ingest_packets(self):
        # Placeholder for MeshCore/Meshtastic packet ingestion
        pass

    def update_data(self):
        # Placeholder for update loops
        pass

if __name__ == '__main__':
    app = LoraLogApp()
    app.mainloop()  
