#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
from datetime import datetime, timedelta
from sys import exit
import asyncio
import gc
from psutil import Process
import math
from configparser import ConfigParser
from html import unescape
from pygame import mixer
# import threading
import threading
import sqlite3
import ast
# DEBUG
# import yaml

# Tkinter imports
from PIL import Image, ImageTk
from tkinter import ttk, Frame, Text, Label, Entry, Button, StringVar, LabelFrame, Toplevel, IntVar, BooleanVar, DoubleVar
from customtkinter import CTk
from tkintermapview2 import TkinterMapView
import textwrap

# Meshtastic imports
from base64 import b64encode
from pubsub import pub
import meshtastic.remote_hardware
import meshtastic.version
from copy import deepcopy

try:
    from meshtastic.protobuf import config_pb2
except ImportError:
    from meshtastic import config_pb2

'''
Fix sub parts if they brake a main part install > pip install --upgrade setuptools <sub tool name>
Upgrade the Meshtastic Python Library           > pip install --upgrade meshtastic
Build the build                                 > pyinstaller --icon=mesh.ico -F --onefile --noconsole LoraLog.py

from pprint import pprint
pprint(vars(object))
'''

# Configure Error logging
import logging
logging.basicConfig(filename='LoraLog.log', level=logging.WARN, format='%(asctime)s : %(message)s', datefmt='%m-%d %H:%M', filemode='w')
logging.error("Startin Up")

telemetry_thread = None
position_thread  = None
trace_thread = None
MapMarkers = {}
ok2Send = 0
chan2send = -1
MyLora = 'ffffffff'
MyLoraID = ''
MyLora_SN = ''
MyLora_LN = ''
MyLora_Lat = -8.0
MyLora_Lon = -8.0
MyLoraText1 = ''
MyLoraText2 = ''
mylorachan = {}
tlast = int(time.time())
loop = None
pingcount = 0
incoming_uptime = 0
package_received_time = 0
zoomhome = False
ourNode = None
NIenabled = False

def showLink(event):
    try:
        tag_names = event.widget.tag_names("current")
        idx = tag_names[0] if '#' in tag_names[1] else tag_names[1]

        if '#' not in idx:
            temp = type('temp', (object,), {})()
            temp.data = idx
            click_command(temp)
    except Exception as e:
        logging.error("Error in showLink: %s", str(e))

# Function to insert colored text
def insert_colored_text(text_widget, text, color, center=False, tag=None):
    global MyLora
    parent_frame = str(text_widget.winfo_parent())
    if "frame5" not in parent_frame or "notebook" in parent_frame:
        text_widget.configure(state="normal")
        if color == '#d1d1d1': # and "frame3" not in parent_frame:
            text_widget.insert("end", "─" * 60 + "\n", '#414141')
            text_widget.tag_configure('#414141', foreground='#414141')

    if tag != None: # and tag != MyLora:
        text_widget.tag_configure(tag, foreground=color, underline=False)
        text_widget.insert('end', text, (color, tag))
        text_widget.tag_bind(tag, "<Button-1>", showLink)
    else:
        text_widget.insert('end', text, color)

    text_widget.tag_configure(color, foreground=color)

    if center:
        text_widget.tag_configure("center", justify='center')
        text_widget.tag_add("center", "1.0", "end")
    if "!frame5" not in parent_frame or "notebook" in parent_frame:
        text_widget.see('end')
        text_widget.configure(state="disabled")

def add_message(nodeid, mtext, msgtime, private=False, msend='all', ackn=False, bulk=False):
    global dbconnection, tabControl, text_boxes
    dbcursor = dbconnection.cursor()
    result = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (nodeid,)).fetchone()
    dbcursor.close()
    if result is None:
        logging.error(f"Node {nodeid} not in database")
        return

    msend2 = unescape(msend)
    private2 = 0
    if msend2 in text_boxes:
        text_widget = text_boxes[msend2]
    else:
        text_widget = text_boxes['Direct Message']
        msend2 = 'Direct Message'
        private2 = 1

    if bulk == False and nodeid != MyLora:
        for i in range(tabControl.index("end")):
            if tabControl.tab(i, "text") == msend2:
                current_text = tabControl.tab(i, "text")
                if '*' not in current_text:
                    tabControl.tab(i, text=f"{current_text} *")

    label = result[5] + " (" + result[4] + ")"
    tcolor = "#00c983"
    if nodeid == MyLora: tcolor = "#2bd5ff"
    timestamp = datetime.fromtimestamp(msgtime).strftime("%Y-%m-%d %H:%M:%S")

    insert_colored_text(text_widget, "─" * 60, "#414141")
    insert_colored_text(text_widget,'\n From ' + unescape(label),tcolor)
    if private:
        dbcursor = dbconnection.cursor()
        result = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (msend,)).fetchone()
        dbcursor.close()
        if result != None:
            label = result[5] + " (" + result[4] + ")"
            insert_colored_text(text_widget,' to ' + label, tcolor)
    ptext = unescape(mtext).strip()
    ptext = textwrap.fill(ptext, 87)
    tcolor = "#d2d2d2"
    if bulk == True:
        tcolor = "#a1a1a1"
    ptext = textwrap.indent(text=ptext, prefix='  ', predicate=lambda line: True)
    insert_colored_text(text_widget, '\n' + ptext + '\n', tcolor)
    insert_colored_text(text_widget,timestamp.rjust(89) + '\n', "#818181")

    if bulk == False:
        msend = str(msend.encode('ascii', 'xmlcharrefreplace'), 'ascii')
        dbcursor = dbconnection.cursor()
        dbcursor.execute("INSERT INTO chat_log (node_id, timerec, private, sendto, ackn, seen, text) VALUES (?, ?, ?, ?, ?, ? ,?)", (nodeid, msgtime, private2, msend, 0, 0, str(mtext.encode('ascii', 'xmlcharrefreplace'), 'ascii')))
        dbcursor.close()
        # Update chatbox if it is open
        global lastchat, overlay
        if len(lastchat) == 4 and overlay != None:
            if lastchat[0] == nodeid or lastchat[0] == msend:
                update_chat_log()

def get_messages():
    with dbconnection:
        dbcursor = dbconnection.cursor()
        result = dbcursor.execute("SELECT * FROM chat_log ORDER BY timerec ASC").fetchall()
        dbcursor.close()
        for entry in result:
            add_message(entry[0], unescape(entry[6]), entry[1], private=entry[2], msend=entry[3], ackn=entry[4], bulk=True)

#------------------------------------------------------------- Database Setup --------------------------------------------------------------------------

# SQLite Database
if not os.path.exists('DataBase'):
    os.makedirs('DataBase')

database = 'DataBase' + os.path.sep + 'LoraLog.db3'
dbconnection = sqlite3.connect(database, timeout=250, check_same_thread=False)
dbcursor = dbconnection.cursor()
create_tmp = """CREATE TABLE IF NOT EXISTS node_info (
                            "node_id" integer NOT NULL PRIMARY KEY, 
                            "timerec" TIMESTAMP,
                            "mac_id" text,
                            "hex_id" text,
                            "long_name" text,
                            "short_name" text,
                            "hw_model_id" text,
                            "is_licensed" integer DEFAULT False,
                            "role" integer,
                            "latitude" real DEFAULT -8.0,
                            "longitude" real DEFAULT -8.0,
                            "altitude" integer DEFAULT 0,
                            "precision_bits" integer,
                            "timefirst" TIMESTAMP,
                            "uptime" TIMESTAMP,
                            "ismqtt" integer DEFAULT False,
                            "last_snr" real DEFAULT 0.0,
                            "last_rssi" integer DEFAULT 0,
                            "last_battery" integer DEFAULT 0,
                            "last_voltage" real DEFAULT 0.0,
                            "last_sats" integer DEFAULT 0,
                            "ChUtil" real DEFAULT 0.0,
                            "AirUtilTX" real DEFAULT 0.0,
                            "hopstart" integer DEFAULT 0,
                            "distance" real DEFAULT 0.0
                        );"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS naibor_info ("node_id" integer NOT NULL PRIMARY KEY, "hex_id" text, "node_pos" text, "timerec" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "timedraw" TIMESTAMP NOT NULL DEFAULT 0,"neighbor_text" text );"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS device_metrics ("node_hex" text, "node_id" integer, "timerec" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "battery_level" integer DEFAULT 0, "voltage" real DEFAULT 0.0, "channel_utilization" real DEFAULT 0.0, "air_util_tx" real DEFAULT 0.0, "snr" real DEFAULT 0.0, "rssi" integer DEFAULT 0);"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS environment_metrics ("node_hex" text, "node_id" integer, "timerec" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "temperature" real DEFAULT 0.0, "relative_humidity" real DEFAULT 0.0, "barometric_pressure" real DEFAULT 0.0, "gas_resistance" real DEFAULT 0.0, iaq integer DEFAULT 0);"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS chat_log ("node_id" text, "timerec" integer, "private" integer, "sendto" text, "ackn" integer, "seen" integer, "text" text);"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS movement_log ("node_hex" text, "node_id" integer, "timerec" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "from_latitude" real DEFAULT -8.0, "from_longitude" real DEFAULT -8.0, "from_altitude" integer DEFAULT 0, "to_latitude" real DEFAULT -8.0, "to_longitude" real DEFAULT -8.0, "to_altitude" integer DEFAULT 0);"""
dbcursor.execute(create_tmp)

dbcursor.execute("PRAGMA journal_mode=OFF")
dbcursor.connection.commit()
dbcursor.close()

def get_data_for_node(database, nodeID, days=3):
    global dbconnection
    cursor = dbconnection.cursor()
    query = f"SELECT *, strftime('%s', timerec) as time_epoch FROM {database} WHERE node_hex = ? AND DATETIME(timerec, 'auto') > DATETIME('now', '-{days} day') ORDER BY timerec ASC"
    result = cursor.execute(query, (nodeID,)).fetchall()
    cursor.close()
    return result

def safedatabase():
     logging.error("Database saved!")

#----------------------------------------------------------- Config File Handle ------------------------------------------------------------------------
config = ConfigParser()
config['meshtastic'] = {
    'interface': 'tcp',
    'host': '127.0.0.1',
    'serial_port': 'COM1',
    'map_delete_time': '60',
    'map_oldnode_time': '10080',
    'map_trail_age': '12',
    'metrics_age': '7',
    'max_lines': '1000',
    'map_tileserver': 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
    'map_cache': 'False',
    'weatherbeacon': 'False',
    'weatherjson': 'http://127.0.0.1/weather.json',
}

if not os.path.exists('config.ini'):
    logging.error("No config file found, creating a new one")
    with open('config.ini', 'w') as configfile:
        config.write(configfile)

try:
    config.read('config.ini')
    map_delete = int(config.get('meshtastic', 'map_delete_time')) * 60
    map_oldnode = int(config.get('meshtastic', 'map_oldnode_time')) * 60
    map_trail_age = int(config.get('meshtastic', 'map_trail_age')) # In Hours !
    metrics_age = int(config.get('meshtastic', 'metrics_age')) # In Days !
    max_lines = int(config.get('meshtastic', 'max_lines')) # Max lines in log box 1 and 2
except Exception as e :
    logging.error("Error loading databases: %s", str(e))

# Import the necessary module based on the interface type
if config.get('meshtastic', 'interface') == 'tcp':
    import meshtastic.tcp_interface
else:
    import meshtastic.serial_interface
#----------------------------------------------------------- Meshtastic Lora Con ------------------------------------------------------------------------    
meshtastic_client = None

mixer.init()
sound_cache = {}
def playsound(soundfile):
    if soundfile not in sound_cache:
        sound_cache[soundfile] = mixer.Sound(soundfile)
        sound_cache[soundfile].set_volume(0.5)
    sound_cache[soundfile].play()

def value_to_graph(value, min_value=-19, max_value=1, graph_length=12):
    value = max(min_value, min(max_value, value))
    position = int((value - min_value) / (max_value - min_value) * (graph_length - 1))
    position0 = int((0 - min_value) / (max_value - min_value) * (graph_length - 1))
    graph = ['─'] * graph_length
    graph[position0] = '┴'
    graph[position] = '╫'
    txt = "Poor"
    if value > -15.0:
        txt = "Fair"
    if value > -7.0:
        txt = "Good"
    return '└' + ''.join(graph) + '┘ ' + txt

def format_number(n):
    if n >= 1_000_000_000:
        return f'{n // 1_000_000_000},{(n % 1_000_000_000) // 100_000_000}B'
    elif n >= 1_000_000:
        return f'{n // 1_000_000},{(n % 1_000_000) // 100_000}M'
    # elif n >= 1_000:
    #     return f'{n // 1_000}K{(n % 1_000) // 100}'
    else:
        return f'{n:,}'

def connect_meshtastic(force_connect=False):
    global meshtastic_client, MyLora, loop, isLora, MyLora_Lat, MyLora_Lon, MyLora_SN, MyLora_LN, mylorachan, chan2send, MyLoraID, zoomhome, ourNode
    if meshtastic_client and not force_connect:
        return meshtastic_client

    # Initialize the event loop
    try:
        loop = asyncio.get_event_loop()
        # loop.run_forever()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    pub.subscribe(on_meshtastic_message, "meshtastic.receive", loop=asyncio.get_event_loop())
    pub.subscribe(on_meshtastic_connection, "meshtastic.connection.established")
    pub.subscribe(on_lost_meshtastic_connection,"meshtastic.connection.lost")

    meshtastic_client = None
    # Initialize Meshtastic interface
    retry_limit = 3
    attempts = 1
    successful = False
    target_host = config.get('meshtastic', 'host')
    com_port = config.get('meshtastic', 'serial_port')
    cnto = target_host
    if config.get('meshtastic', 'interface') != 'tcp':
        cnto = com_port
    logging.debug("Connecting to meshtastic on " + cnto + "...")

    insert_colored_text(text_box1, " Connecting to meshtastic on " + cnto + "...\n", "#00c983")
    while not successful and attempts <= retry_limit:
        try:
            if config.get('meshtastic', 'interface') == 'tcp':
                meshtastic_client = meshtastic.tcp_interface.TCPInterface(hostname=target_host)
            else:
                meshtastic_client = meshtastic.serial_interface.SerialInterface(com_port)
            successful = True
            isLora = True
        except Exception as e:
            attempts += 1
            if attempts <= retry_limit:
                insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                insert_colored_text(text_box1, " Connect re-try:" + str(e), "#db6544")
                logging.error("Connect re-try: " + str(e))
                time.sleep(5)
            else:
                logging.error("Could not connect: " + str(e))
                isLora = False
                return None
    nodeInfo = meshtastic_client.getMyNodeInfo()
    logging.error("Connected to " + nodeInfo['user']['id'] + " > "  + nodeInfo['user']['shortName'] + " / " + nodeInfo['user']['longName'] + " using a " + nodeInfo['user']['hwModel'])
    insert_colored_text(text_box1, " Connected to " + nodeInfo['user']['id'] + " > "  + nodeInfo['user']['shortName'] + " / " + nodeInfo['user']['longName'] + " using a " + nodeInfo['user']['hwModel'] + "\n", "#00c983")
    MyLoraID = nodeInfo['num']
    MyLora = (nodeInfo['user']['id'])[1:]
    MyLora_SN = nodeInfo['user']['shortName']
    if MyLora_SN == '':
        MyLora_SN = str(MyLora)[-4:]
    MyLora_LN = nodeInfo['user']['longName']

    print("MyLora: " + MyLora)
    root.wm_title("Meshtastic Lora Logger - !" + str(MyLora).upper() + " - " + unescape(MyLora_SN))

    # logLora((nodeInfo['user']['id'])[1:], ['NODEINFO_APP', nodeInfo['user']['shortName'], nodeInfo['user']['longName'], nodeInfo['user']["macaddr"],nodeInfo['user']['hwModel']])
    ## NEED AD MY SELF TO LOG 1ST TIME

    if 'position' in nodeInfo and 'latitude' in nodeInfo['position']:
        MyLora_Lat = round(nodeInfo['position']['latitude'],6)
        MyLora_Lon = round(nodeInfo['position']['longitude'],6)
        zoomhome = False

    nodeInfo = meshtastic_client.getNode('^local')
    ourNode = nodeInfo

    # Lets get the Local Node's channels
    lora_config = nodeInfo.localConfig.lora
    modem_preset_enum = lora_config.modem_preset
    modem_preset_string = config_pb2._CONFIG_LORACONFIG_MODEMPRESET.values_by_number[modem_preset_enum].name
    channels = nodeInfo.channels
    chan2send = 0
    addtotab = False
    mylorachan = {}
    if channels:
        for channel in channels:
            addtotab = True
            if len(str(channel.settings)) > 4:
                psk_base64 = b64encode(channel.settings.psk).decode('utf-8')
                addtotab = True
                if channel.settings.name == '':
                    mylorachan[channel.index] = channame(modem_preset_string)
                else:
                    mylorachan[channel.index] = channame(channel.settings.name)

                if chan2send == -1:
                    chan2send = channel.index

                # Need add to tabs for each channel
                if mylorachan[channel.index] != '' and addtotab:
                    if mylorachan[channel.index] not in text_boxes: # Reconnected ?

                        insert_colored_text(text_box1, " Joined Lora Channel " + str(channel.index) + " " + mylorachan[channel.index] + " using Key " + psk_base64 + "\n", "#00c983")

                        tab = Frame(tabControl, background="#121212", padx=0, pady=0, borderwidth=0) # ttk.Frame(tabControl, style='TFrame', padding=0, borderwidth=0)
                        tab.grid_rowconfigure(0, weight=1)
                        tab.grid_columnconfigure(0, weight=1)
                        tabControl.add(tab, text=mylorachan[channel.index], padding=(0, 0, 0, 0))
                        text_area = Text(tab, wrap='word', width=90, height=15, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), undo=False, borderwidth=1, highlightthickness=0)
                        text_area.grid(sticky='nsew')
                        text_area.configure(state="disabled")
                        text_boxes[mylorachan[channel.index]] = text_area

    if 'Direct Message' not in text_boxes:
        tab = Frame(tabControl, background="#121212", padx=0, pady=0, borderwidth=0) # ttk.Frame(tabControl, style='TFrame', padding=0, borderwidth=0)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        tabControl.add(tab, text='Direct Message', padding=(0, 0, 0, 0))
        text_area = Text(tab, wrap='word', width=90, height=15, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), undo=False, borderwidth=1, highlightthickness=0)
        text_area.grid(sticky='nsew')
        text_area.configure(state="disabled")
        text_boxes['Direct Message'] = text_area

    time.sleep(0.5)
    updatesnodes()
    return meshtastic_client

def channame(s):
    if '_' in s:
        parts = s.lower().split('_')
        return ''.join(part.capitalize() for part in parts)
    return s

# Function to reset the tab's background color
def reset_tab_highlight(event):
    global chan2send
    selected_tab = tabControl.select()
    current_text = tabControl.tab(selected_tab, "text")
    
    if current_text.endswith(" *"):
        tabControl.tab(selected_tab, text=current_text[:-2])
    
    # the index of mylorachan[0] = 'ChanName' is the same as the channel index
    chan2text = tabControl.tab(selected_tab, "text")
    if chan2text != 'Direct Message':
        chan2send = None
        for key, value in mylorachan.items():
            if value == chan2text:
                chan2send = key
                break

def on_lost_meshtastic_connection(interface):
    global root, loop, telemetry_thread, position_thread, trace_thread, meshtastic_client

    pub.unsubscribe(on_lost_meshtastic_connection, "meshtastic.connection.lost")

    logging.error("Lost connection to Meshtastic Node.")
    if telemetry_thread != None and telemetry_thread.is_alive():
        telemetry_thread.join()
    if  position_thread != None and position_thread.is_alive():
        position_thread.join()
    if  trace_thread != None and trace_thread.is_alive():
        trace_thread.join()

    pub.unsubscribe(on_meshtastic_message, "meshtastic.receive")
    pub.unsubscribe(on_meshtastic_connection, "meshtastic.connection.established")

    insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
    insert_colored_text(text_box1, " Lost connection to node!, Reconnecting in 10 seconds\n", "#db6544")
    try:
        root.meshtastic_interface = None
        meshtastic_client.close()
        meshtastic_client = None
    except Exception as e:
        logging.error("Error closing connection: %s", str(e))
    time.sleep(10)
    root.meshtastic_interface = connect_meshtastic(force_connect=True)
 
def on_meshtastic_connection(interface, topic=pub.AUTO_TOPIC):
    print("Connected to meshtastic")

def print_range(range_in_meters):
    if range_in_meters < 1:
        # Convert to centimeters
        range_in_cm = range_in_meters * 100
        return f"{range_in_cm:.0f}cm"
    elif range_in_meters < 1000:
        # Print in meters
        return f"{range_in_meters:.0f}meter"
    else:
        # Convert to kilometers
        range_in_km = range_in_meters / 1000
        return f"{range_in_km:.0f}km"

def idToHex(nodeId):
    if type(nodeId) is int:
        if nodeId > 0:
            in_hex = hex(nodeId)
            if len(in_hex)%2: in_hex = in_hex.replace("0x","0x0") # Need account for leading zero, wish hex removes if it has one
            return f"!{in_hex[2:]}"
    return '!ffffffff'

def MapMarkerDelete(node_id):
    global MapMarkers, mapview
    if node_id in MapMarkers:
        # Move Trail
        if MapMarkers[node_id][4] != None:
            MapMarkers[node_id][4].delete()
            MapMarkers[node_id][4] = None
        # Check Trail
        MapMarkers[node_id][5] = 0
        # Signal
        if MapMarkers[node_id][6] != None:
            MapMarkers[node_id][6].delete()
            MapMarkers[node_id][6] = None
        # Range Circle
        if len(MapMarkers[node_id]) == 8:
            if MapMarkers[node_id][7] != None:
                MapMarkers[node_id][7].delete()
                MapMarkers[node_id][7] = None
            MapMarkers[node_id].pop()
        # Deleting Mehard lines and Move Trail in map_widget, as we not always get all via delete up above

# Lets work the local nodes heard list
HeardDB = {}
def logheard(sourseIDx, nodeIDx, dbdata, nodesname):
    global HeardDB, MapMarkers, mapview
    tnow = int(time.time())
    key = (sourseIDx, nodeIDx)
    sourseID = idToHex(sourseIDx)[1:]
    nodeID = idToHex(nodeIDx)[1:]

    heard_entry = HeardDB.setdefault(key, [tnow, dbdata, None, nodesname])
    heard_entry[0] = tnow
    heard_entry[1] = dbdata

    if sourseID in MapMarkers and nodeID in MapMarkers:
        if heard_entry[2] is None:
            listmaps = [MapMarkers[sourseID][0].get_position(), MapMarkers[nodeID][0].get_position() ]
            heard_entry[2] = mapview.set_path(listmaps, color="#006642", width=2, name=sourseID)

# We moved need re draw 
def redrawnaibors(sourceIDx):
    for key, value in HeardDB.items():
        if value[2] is not None and (key[0] == sourceIDx or key[1] == sourceIDx):
            value[2].delete()
            value[2] = None
            sourseID = idToHex(key[0])[1:]
            nodeID = idToHex(key[1])[1:]
            if sourseID in MapMarkers and nodeID in MapMarkers:
                listmaps = [MapMarkers[sourseID][0].get_position(), MapMarkers[nodeID][0].get_position()]
                value[2] = mapview.set_path(listmaps, color="#006642", width=2, name=sourseID)

def deloldheard(deltime):
    tnow = int(time.time())
    keys_to_delete = [key for key, value in HeardDB.items() if tnow - value[0] > (deltime / 3)]
    for key in keys_to_delete:
        value = HeardDB[key]
        if value[2] is not None:
            value[2].delete()
            value[2] = None
        del HeardDB[key]

def on_meshtastic_message(packet, interface, loop=None):
    # print(yaml.dump(packet), end='\n\n')
    global MyLora, MyLoraText1, MyLoraText2, MapMarkers, dbconnection, MyLora_Lat, MyLora_Lon, incoming_uptime, package_received_time
    if MyLora == '':
        print('*** MyLora is empty ***\n')
        # return

    ischat = False
    tnow = int(time.time())

    text_from = ''
    if 'fromId' in packet and packet['fromId'] is not None:
        text_from = packet.get('fromId', '')[1:]
    if text_from == '':
        text_from = idToHex(packet["from"])[1:]
    fromraw = text_from
    fromname = text_from

    viaMqtt = False
    if "viaMqtt" in packet:
        viaMqtt = True

    hopStart = -1
    if "hopStart" in packet:
        hopStart = packet.get('hopStart', 0) - packet.get('hopLimit', 0) # packet.get('hopStart', -1)

    with dbconnection:
        dbcursor = dbconnection.cursor()
        if text_from != '':
            result = dbcursor.execute("SELECT * FROM node_info WHERE node_id = ?", (packet["from"],)).fetchone()
            if result is None:
                sn = str(fromraw[-4:])
                ln = "Meshtastic " + sn
                dbcursor.execute("INSERT INTO node_info (node_id, timerec, hex_id, ismqtt, last_snr, last_rssi, timefirst, short_name, long_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (packet["from"], tnow, text_from, viaMqtt, packet.get('rxSnr', 0), packet.get('rxRssi', 0), tnow, sn, ln))
                result = dbcursor.execute("SELECT * FROM node_info WHERE node_id = ?", (packet["from"],)).fetchone()
                insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] New Node Logged\n", "#d1d1d1")
                insert_colored_text(text_box1, (' ' * 11) + "Node ID !" + fromraw + " (" + text_from + ")\n", "#e8643f", tag=fromraw)
                playsound('Data' + os.path.sep + 'NewNode.mp3')
            else:
                # Added timefirst here for now to so we can sync up the 2 databases
                if result[5] == '': result[5] = str(fromraw[-4:])
                if result[4] == '': result[4] = "Meshtastic " + str(fromraw[-4:])
                text_from = unescape(result[5]) + " (" + unescape(result[4]) + ")"
                fromname = unescape(result[5])
                dbcursor.execute("UPDATE node_info SET timerec = ?, ismqtt = ?, last_snr = ?, last_rssi = ?, hopstart = ? WHERE node_id = ?", (tnow, viaMqtt, packet.get('rxSnr', 0), packet.get('rxRssi', 0), hopStart, packet["from"]))

        if "decoded" in packet:
            data = packet["decoded"]
            if text_from !='':
                text_msgs = ''

                # Lets Work the Msgs
                if data["portnum"] == "ADMIN_APP":
                    if "getDeviceMetadataResponse" in data["admin"]:
                        text_raws = f"Firmware version : {data['admin']['getDeviceMetadataResponse']['firmwareVersion']}"
                    else:
                        text_raws = 'Admin Data'
                elif data["portnum"] == "TELEMETRY_APP":
                    text_raws = 'Node Telemetry'
                    telemetry = packet['decoded'].get('telemetry', {})
                    if telemetry:
                        device_metrics = telemetry.get('deviceMetrics', {})
                        if device_metrics:
                            dbcursor.execute("UPDATE node_info SET last_battery = ?, last_voltage = ?, uptime = ?, ChUtil = ?, AirUtilTX = ? WHERE node_id = ?", (device_metrics.get('batteryLevel', 0), device_metrics.get('voltage', 0.00), device_metrics.get('uptimeSeconds', 0), device_metrics.get('channelUtilization', 0.00), device_metrics.get('airUtilTx', 0.00), packet["from"]))
                            dbcursor.execute("INSERT INTO device_metrics (node_hex, node_id, battery_level, voltage, channel_utilization, air_util_tx, snr, rssi) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (fromraw, packet["from"], device_metrics.get('batteryLevel', 0), device_metrics.get('voltage', 0.00), device_metrics.get('channelUtilization', 0.00), device_metrics.get('airUtilTx', 0.00), packet.get('rxSnr', 0), packet.get('rxRssi', 0)))
                            text_raws += '\n' + (' ' * 11) + 'Battery: ' + str(device_metrics.get('batteryLevel', 0)) + '% '
                            text_raws += 'Power: ' + str(round(device_metrics.get('voltage', 0.00),2)) + 'v '
                            text_raws += 'ChUtil: ' + str(round(device_metrics.get('channelUtilization', 0.00),2)) + '% '
                            text_raws += 'AirUtilTX (DutyCycle): ' + str(round(device_metrics.get('airUtilTx', 0.00),2)) + '%'
                            if 'uptimeSeconds' in device_metrics:
                                text_raws += '\n' + (' ' * 11) + uptimmehuman(device_metrics.get('uptimeSeconds', 0), tnow)
                            if MyLora == fromraw:
                                MyLoraText1 = (' ChUtil').ljust(13) + str(round(device_metrics.get('channelUtilization', 0.00),2)).rjust(6) + '%\n' + (' AirUtilTX').ljust(13) + str(round(device_metrics.get('airUtilTx', 0.00),2)).rjust(6) + '%\n'
                                if device_metrics.get('voltage', 0.00) > 0.00: MyLoraText1 += (' Power').ljust(13) + str(round(device_metrics.get('voltage', 0.00),2)).rjust(6) + 'v\n' 
                                if device_metrics.get('batteryLevel', 0) > 0: MyLoraText1 += (' Battery').ljust(13) + str(device_metrics.get('batteryLevel', 0)).rjust(6) + '%\n'
                        power_metrics = telemetry.get('powerMetrics', {})
                        if power_metrics:
                            text_raws += '\n' + (' ' * 11) + 'CH1 Voltage: ' + str(round(power_metrics.get('ch1_voltage', 'N/A'),2)) + 'v'
                            text_raws += ' CH1 Current: ' + str(round(power_metrics.get('ch1_current', 'N/A'),2)) + 'mA'
                            text_raws += ' CH2 Voltage: ' + str(round(power_metrics.get('ch2_voltage', 'N/A'),2)) + 'v'
                            text_raws += ' CH2 Current: ' + str(round(power_metrics.get('ch2_current', 'N/A'),2)) + 'mA'
                        environment_metrics = telemetry.get('environmentMetrics', {})
                        if environment_metrics:
                            dbcursor.execute("INSERT INTO environment_metrics (node_hex, node_id, temperature, relative_humidity, barometric_pressure) VALUES (?, ?, ?, ?, ?)", (fromraw, packet["from"], environment_metrics.get('temperature', 0.0), environment_metrics.get('relativeHumidity', 0.0), environment_metrics.get('barometricPressure', 0.0)))
                            # , environment_metrics.get('gasResistance', 0.00) ? no clue yet how metrics reports this
                            # , environment_metrics.get('iaq', 0) ? no clue yet how metrics reports this
                            # But we have in DB for now so all we need do if we do get these is add it to the insert
                            text_raws += '\n' + (' ' * 11) + 'Temperature: ' + str(round(environment_metrics.get('temperature', 0.0),1)) + '°C'
                            text_raws += ' Humidity: ' + str(round(environment_metrics.get('relativeHumidity', 0.0),1)) + '%'
                            text_raws += ' Pressure: ' + str(round(environment_metrics.get('barometricPressure', 0.00),2)) + 'hPa'
                        localstats_metrics = telemetry.get('localStats', {})
                        if localstats_metrics:
                            text_raws += '\n' + (' ' * 11) + 'PacketsTx: ' + str(localstats_metrics.get('numPacketsTx', 0))
                            text_raws += ' PacketsRx: ' + str(localstats_metrics.get('numPacketsRx', 0))
                            text_raws += ' PacketsRxBad: ' + str(localstats_metrics.get('numPacketsRxBad', 0))
                            if localstats_metrics.get('numRxDupe', 0) > 0:
                                # Number of received packets that were duplicates (due to multiple nodes relaying)
                                text_raws += ' RxDupe: ' + str(localstats_metrics.get('numRxDupe', 0))
                            if localstats_metrics.get('numTxRelay', 0) > 0:
                                # Number of packets we transmitted that were a relay for others (not originating from ourselves)
                                text_raws += '\n' + (' ' * 11) + 'TxRelay: ' + str(localstats_metrics.get('numTxRelay', 0))
                            if localstats_metrics.get('numTxRelayCanceled', 0) > 0:
                                # Number of times we canceled a packet to be relayed, because someone else did it before us
                                text_raws += ' TxCanceled: ' + str(localstats_metrics.get('numTxRelayCanceled', 0))
                            text_raws += ' Nodes: ' + str(localstats_metrics.get('numOnlineNodes', 0)) + '/' + str(localstats_metrics.get('numTotalNodes', 0))

                            MyLoraText2 = (' Packets Tx').ljust(13) + format_number(localstats_metrics.get('numPacketsTx', 0)).rjust(7) + '\n'
                            if localstats_metrics.get('numTxRelay', 0) > 0:
                                MyLoraText2 += (' Tx Relay').ljust(13) + format_number(localstats_metrics.get('numTxRelay', 0)).rjust(7) + '\n'
                            if localstats_metrics.get('numTxRelayCanceled', 0) > 0:
                                MyLoraText2 += (' Tx Cancel').ljust(13) + format_number(localstats_metrics.get('numTxRelayCanceled', 0)).rjust(7) + '\n'
                            MyLoraText2 += (' Packets Rx').ljust(13) + format_number(localstats_metrics.get('numPacketsRx', 0)).rjust(7) + '\n' + (' Rx Bad').ljust(13) + format_number(localstats_metrics.get('numPacketsRxBad', 0)).rjust(7) + '\n'
                            if localstats_metrics.get('numRxDupe', 0) > 0:
                                MyLoraText2 += (' Rx Dupe').ljust(13) + format_number(localstats_metrics.get('numRxDupe', 0)).rjust(7) + '\n'
                            MyLoraText2 += (' Nodes').ljust(13) + (format_number(localstats_metrics.get('numOnlineNodes', 0)) + '/' + format_number(localstats_metrics.get('numTotalNodes', 0))).rjust(7) + '\n'

                        if 'uptimeSeconds' in device_metrics and fromraw == MyLora:
                            incoming_uptime = device_metrics.get('uptimeSeconds', 0)
                            package_received_time = tnow

                    if text_raws == 'Node Telemetry':
                        text_raws += ' No Data'
                elif data["portnum"] == "CHAT_APP" or data["portnum"] == "TEXT_MESSAGE_APP":
                    text = ''
                    if 'chat' in data:
                        text = data.get('chat', '')
                    if 'text' in data:  
                        text = data.get('text', '')
                    
                    if text != '':
                        text_msgs = str(text.encode('ascii', 'xmlcharrefreplace'), 'ascii').rstrip()
                        text_raws = text
                        text_chns = 'Direct Message'
                        if "toId" in packet:
                            if packet["toId"] == '^all':
                                text_chns = str(mylorachan[0])
                        if "channel" in packet:
                            text_chns = str(mylorachan[packet["channel"]])

                        ischat = True
                        playsound('Data' + os.path.sep + 'NewChat.mp3')
                    else:
                        text_raws = 'Node Chat Encrypted'
                elif data["portnum"] == "POSITION_APP":
                    position = data["position"]
                    nodelat = round(position.get('latitude', -8.0),6)
                    nodelon = round(position.get('longitude', -8.0),6)
                    nodealt = position.get('altitude', 0)
                    node_dist = 0.0
                    extra = ''
                    if nodelat != -8.0 and nodelon != -8.0:
                        if (result[9] != nodelat or result[10] != nodelon or result[11] != nodealt) and result[9] != -8.0 and result[10] != -8.0:
                            # We moved add to movement log ?
                            dbcursor.execute("INSERT INTO movement_log (node_hex, node_id, timerec, from_latitude, from_longitude, from_altitude, to_latitude, to_longitude, to_altitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (fromraw, packet["from"], tnow, result[9], result[10], result[11], nodelat, nodelon, nodealt))
                            extra = '(Moved!) '
                            # MapMarkerDelete(fromraw)
                        if fromraw == MyLora:
                            MyLora_Lat = nodelat
                            MyLora_Lon = nodelon
                        else:
                            node_dist = calc_gc(nodelat, nodelon, MyLora_Lat, MyLora_Lon)
                        dbcursor.execute("UPDATE node_info SET latitude = ?, longitude = ?, altitude = ?, precision_bits = ?, last_sats = ?, distance = ? WHERE node_id = ?", (nodelat, nodelon, position.get('altitude', 0), position.get('precisionBits', 0), position.get('satsInView', 0), node_dist, packet["from"]))
                    text_msgs = 'Node Position '
                    text_msgs += 'latitude ' + str(round(nodelat,4)) + ' '
                    text_msgs += 'longitude ' + str(round(nodelon,4)) + ' '
                    text_msgs += 'altitude ' + str(nodealt) + ' meter\n' + (' ' * 11)
                    if nodelat != -8.0 and nodelon != -8.0:
                        if MyLora != fromraw and nodelat != -8.0 and nodelon != -8.0:
                            text_msgs += "Distance: ±" + str(node_dist) + "km "
                        if fromraw in MapMarkers:
                            if MapMarkers[fromraw][0] != None:
                                MapMarkers[fromraw][0].set_position(nodelat, nodelon)
                                MapMarkers[fromraw][0].set_text(result[5])
                            if MapMarkers[fromraw][6] != None:
                                MapMarkers[fromraw][6].set_position(nodelat, nodelon)
                        text_msgs += extra
                        if 'precisionBits' in position and position.get('precisionBits', 0) > 0:
                            AcMeters = round(23905787.925008 * math.pow(0.5, position.get('precisionBits', 0)), 2)
                            if AcMeters > 1.0:
                                text_msgs += '(Accuracy ±' + print_range(AcMeters) + ') '
                                if fromraw in MapMarkers and AcMeters >= 30.0 and AcMeters <= 5000.0:
                                    # Lets draw only a circle if distance bigger then 30m or smaller then 5km
                                    if len(MapMarkers[fromraw]) == 7:
                                        MapMarkers[fromraw].append(None)
                                        MapMarkers[fromraw][7] = mapview.set_polygon(position=(nodelat, nodelon), range_in_meters=(AcMeters * 2),fill_color="gray25")
                    if "satsInView" in position:
                        text_msgs += '(' + str(position.get('satsInView', 0)) + ' satelites)'
                    if extra == '(Moved!) ':
                        redrawnaibors(packet["from"])
                    text_raws = text_msgs
                elif data["portnum"] == "NODEINFO_APP":
                    node_info = packet['decoded'].get('user', {})
                    if node_info:
                        tmp = node_info.get('shortName', str(fromraw)[:-4])
                        if tmp == str(fromraw)[:-4]:
                            if result[5] != tmp and result[5] != '':
                                tmp = result[5]
                        lora_sn = str(tmp.encode('ascii', 'xmlcharrefreplace'), 'ascii')
                        tmp = node_info.get('longName', 'Meshtastic ' + str(fromraw)[:-4])
                        if tmp == 'Meshtastic ' + str(fromraw)[:-4]:
                            if result[4] != tmp and result[4] != '':
                                tmp = result[4]
                        lora_ln = str(tmp.encode('ascii', 'xmlcharrefreplace'), 'ascii')
                        lora_mc = node_info.get('macaddr', 'N/A')
                        lora_mo = node_info.get('hwModel', 'N/A')
                        if fromraw in MapMarkers and MapMarkers[fromraw][0] != None:
                            MapMarkers[fromraw][0].set_text(unescape(lora_sn))
                        text_raws = "Node Info using hardware " + lora_mo
                        nodelicense = False
                        if 'isLicensed' in packet:
                            text_raws += " (Licensed)"
                            nodelicense = True
                        if 'role' in packet:
                            text_raws +=  " Role: " + node_info.get('role', 'N/A')
                        text_from = lora_sn + " (" + lora_ln + ")"

                        dbcursor.execute("UPDATE node_info SET mac_id = ?, long_name = ?, short_name = ?, hw_model_id = ?, is_licensed = ?, role = ? WHERE node_id = ?", (lora_mc, lora_ln, lora_sn, lora_mo, nodelicense, node_info.get('role', 'N/A'), packet["from"]))
                    else:
                        text_raws = 'Node Info No Data'
                elif data["portnum"] == "NEIGHBORINFO_APP":
                    text_raws = 'Node Neighborinfo'
                    if fromraw not in MapMarkers:
                        if result[9] != -8.0 and result[10] != -8.0:
                            MapMarkers[fromraw] = [None, True, tnow, None, None, 0, None]
                            MapMarkers[fromraw][0] = mapview.set_marker(result[9], result[10], text=unescape(result[5]), icon_index=3, text_color = '#2bd5ff', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                    if "neighborinfo" in data and "neighbors" in data["neighborinfo"]:
                        text = data["neighborinfo"]["neighbors"]
                        for neighbor in text:
                            nodeid = idToHex(neighbor["nodeId"])[1:]
                            tmp = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ? AND latitude != -8 AND longitude != -8", (nodeid,)).fetchone()
                            nbNide = '!' + nodeid
                            if tmp is not None:
                                nbNide = str(tmp[5].encode('ascii', 'xmlcharrefreplace'), 'ascii') # unescape(tmp[5])
                                if nodeid not in MapMarkers:
                                    MapMarkers[nodeid] = [None, True, tnow, None, None, 0, None]
                                    MapMarkers[nodeid][0] = mapview.set_marker(tmp[9], tmp[10], text=unescape(nbNide), icon_index=3, text_color = '#2bd5ff', font = ('Fixedsys', 8), data=nodeid, command = click_command)
                                    dbcursor.execute("UPDATE node_info SET timerec = ? WHERE hex_id = ?", (tnow, nodeid)) # We dont need to update this as we only update if we hear it our self
                                nodeid = tmp[5]
                            else:
                                nodeid = '!' + nodeid

                            text_raws += '\n' + (' ' * 11) + nodeid
                            if "snr" in neighbor:
                                text_raws += ' (' + str(neighbor["snr"]) + 'dB)'

                            logheard(packet["from"], neighbor["nodeId"], neighbor.get('snr', 0.00), nbNide)
                    else:
                        text_raws += ' No Data'
                elif data["portnum"] == "RANGE_TEST_APP":
                    text_raws = 'Node RangeTest'
                    payload = data.get('payload', b'')
                    text_raws += '\n' + (' ' * 11) + 'Payload: ' + str(payload.decode())
                elif data["portnum"] == "TRACEROUTE_APP":
                    TraceTo = idToHex(packet['to'])
                    TraceTo_tx = TraceTo
                    TraceFrom = idToHex(packet['from'])
                    TraceFrom_tx = TraceFrom

                    result2 = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (TraceTo[1:],)).fetchone()
                    if result2:
                        TraceTo_tx = result2[5]
                    result2 = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (TraceFrom[1:],)).fetchone()
                    if result2:
                        TraceFrom_tx = result2[5]

                    route = packet['decoded']['traceroute'].get('route', [])
                    snr = packet['decoded']['traceroute'].get('snrTowards', [])
                    routeBack = packet['decoded']['traceroute'].get('routeBack', [])
                    snrBack = packet['decoded']['traceroute'].get('snrBack', [])
                    text_raws = 'Node Traceroute\n' + (' ' * 11) + 'From : ' + TraceTo_tx + ' --> '
                    index = 0
                    if routeBack:
                        for nodeuuid in routeBack:
                            nodeidt = idToHex(nodeuuid)[1:]
                            result2 = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (nodeidt,)).fetchone()
                            if result2:
                                text_raws += result2[5]
                            else:
                                text_raws += '!' + nodeidt

                            if snrBack and snrBack[index] != -128 and snrBack[index] != 0:
                                text_raws += f" ({snrBack[index] / 4:.2f}dB)"
                            text_raws += ' --> '
                            index += 1
                    text_raws += TraceFrom_tx
                    if snrBack and snrBack[index] != -128 and snrBack[index] != 0:
                        text_raws += f" ({snrBack[index] / 4:.2f}dB)"
                    text_raws += '\n' + (' ' * 11) + 'Back : ' + TraceFrom_tx + ' --> '
                    index = 0
                    if route:
                        for nodeuuid in route:
                            nodeidt = idToHex(nodeuuid)[1:]
                            result2 = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (nodeidt,)).fetchone()
                            if result2:
                                text_raws += result2[5]
                            else:
                                text_raws += '!' + nodeidt
                            if snr and snr[index] != -128 and snr[index] != 0:
                                text_raws += f" ({snr[index] / 4:.2f}dB)"
                            text_raws += ' --> '
                            index += 1
                    text_raws += TraceTo_tx
                    if snr and snr[index] != -128 and snr[index] != 0:
                        text_raws += f" ({snr[index] / 4:.2f}dB)"
                elif data["portnum"] == "ROUTING_APP":
                    text_raws = 'Node Routing'
                    if "errorReason" in data["routing"]:
                        text_raws += ' - Error : ' + data["routing"]["errorReason"]
                else:
                    if 'portnum' in data:
                        text_raws = 'Node ' + (data["portnum"].split('_APP', 1)[0]).title()
                    else:
                        text_raws = 'Node Unknown Packet'

                nodesnr = 0
                if "rxSnr" in packet and packet['rxSnr'] is not None:
                    dbcursor.execute("UPDATE node_info SET last_snr = ?, last_rssi = ?, ismqtt = ? WHERE node_id = ?", (packet.get('rxSnr', 0), packet.get('rxRssi', 0), viaMqtt, packet["from"]))
                    nodesnr = packet['rxSnr']

                # Lets work the map
                if fromraw != MyLora:
                    if fromraw in MapMarkers:
                        MapMarkers[fromraw][2] = tnow
                        if viaMqtt == True and MapMarkers[fromraw][1] == False:
                            MapMarkers[fromraw][1] = True
                            if MapMarkers[fromraw][0] != None:
                                MapMarkers[fromraw][0].change_icon(3)
                        elif viaMqtt == False and MapMarkers[fromraw][1] == True:
                            MapMarkers[fromraw][1] = False
                            if MapMarkers[fromraw][0] != None:
                                MapMarkers[fromraw][0].change_icon(2)
                    elif result[9] != -8.0 and result[10] != -8.0 and viaMqtt == True:
                        MapMarkers[fromraw] = [None, True, tnow, None, None, 0, None]
                        MapMarkers[fromraw][0] = mapview.set_marker(result[9], result[10], text=unescape(result[5]), icon_index=3, text_color = '#2bd5ff', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                        MapMarkers[fromraw][0].text_color = '#2bd5ff'
                    elif result[9] != -8.0 and result[10] != -8.0 and viaMqtt == False:
                        MapMarkers[fromraw] = [None, False, tnow, None, None, 0, None]
                        MapMarkers[fromraw][0] = mapview.set_marker(result[9], result[10], text=unescape(result[5]), icon_index=2, text_color = '#2bd5ff', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                        MapMarkers[fromraw][0].text_color = '#2bd5ff'

                # Lets add a indicator
                if fromraw in MapMarkers and MapMarkers[fromraw][6] == None and 'localstats_metrics' not in packet:
                    MapMarkers[fromraw][6] = mapview.set_marker(result[9], result[10], icon_index=5, data=fromraw, command = click_command)
                elif fromraw in MapMarkers and MapMarkers[fromraw][6] != None and 'localstats_metrics' not in packet:
                    MapMarkers[fromraw][6].change_icon(5)

                # Cleanup and get ready to print
                text_from = unescape(text_from)
                text_raws = unescape(text_raws)
                text_via = ''
                if viaMqtt == True:
                    text_via = ' via mqtt'
                elif hopStart > 0:
                    text_via = ' via ' + str(hopStart) + ' node'

                chantxt = (' ' * 11)
                if "channel" in packet:
                    chantxt = ' ' + str(mylorachan[packet["channel"]])
                    if len(chantxt) <= 10:
                        chantxt += (' ' * (11 - len(chantxt)))
                    else:
                        chantxt = chantxt[:8] + '.. '

                if text_raws != '' and MyLora != fromraw:
                    insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + ' [!' + fromraw + ']' + text_via + "\n", "#d1d1d1", tag=fromraw)
                    if ischat == True:
                        add_message(fromraw, text_raws, tnow, msend=text_chns)

                    if viaMqtt == True:
                        insert_colored_text(text_box1, chantxt + text_raws + '\n', "#c9a500")
                    else:
                        text_from = ''
                        if nodesnr != 0 and MyLora != fromraw:
                            if text_from == '':
                                text_from = '\n' + (' ' * 11)
                            text_from += f"{round(nodesnr,1)}dB {value_to_graph(nodesnr)}"

                        insert_colored_text(text_box1, chantxt + text_raws + text_from + '\n', "#00c983")
                elif text_raws != '' and MyLora == fromraw:
                    insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + text_via + "\n", "#d1d1d1")
                    insert_colored_text(text_box2, chantxt + text_raws + '\n', "#00c983")
                else:
                    insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + ' [!' + fromraw + ']' + text_via + "\n", "#d1d1d1", tag=fromraw)
            else:
                logging.debug("No fromId in packet")
                insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] No fromId in packet\n', "#c24400")
        else:
            insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + ']', "#d1d1d1")
            if hopStart > 0:
                text_from += ' via ' + str(hopStart) + ' node'
            insert_colored_text(text_box1, ' Encrypted packet from ' + text_from + '\n', "#db6544", tag=fromraw)

            if fromraw not in MapMarkers:
                if result[9] != -8.0 and result[10] != -8.0:
                    MapMarkers[fromraw] = [None, False, tnow, None, None, 0, None]
                    MapMarkers[fromraw][0] = mapview.set_marker(result[9], result[10], text=unescape(result[5]), icon_index=4, text_color = '#aaaaaa', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                    MapMarkers[fromraw][0].text_color = '#aaaaaa'
                    MapMarkers[fromraw][6] = mapview.set_marker(result[9], result[10], icon_index=5, data=fromraw, command = click_command)
            elif fromraw in MapMarkers and MapMarkers[fromraw][0] == None:
                MapMarkers[fromraw][6] = mapview.set_marker(result[9], result[10], icon_index=5, data=fromraw, command = click_command)

        # Lets add the mheard lines
        if MyLoraID != 'ffffffff' and packet["from"] != '' and viaMqtt == False and hopStart == 0:
            logheard(MyLoraID, packet["from"], packet.get('rxSnr', 0.00), fromname)

        dbcursor.close()

def updatesnodes():
    global MyLora, MapMarkers, dbconnection, MyLora_Lat, MyLora_Lon, MyLora_SN, MyLora_LN, zoomhome
    info = ''
    tnow = int(time.time())
    with dbconnection:
        cursor = dbconnection.cursor()
        for nodes, info in meshtastic_client.nodes.items():

            nodeID = str(info['user']['id'])[1:]
            if nodeID == '': nodeID = idToHex(info["num"])[1:]
            result = cursor.execute("SELECT * FROM node_info WHERE node_id = ?", (info["num"],)).fetchone()
            if result is None:
                print(f"updatesnodes > Node {nodeID} not in DB")
                cursor.execute("INSERT INTO node_info (node_id, hex_id, short_name, long_name, timefirst) VALUES (?, ?, ?, ?, ?)", (info["num"], nodeID, nodeID[-4:], 'Meshtastic ' + nodeID[-4:], tnow))
                insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] New Node Logged\n", "#d1d1d1")
                insert_colored_text(text_box1, (' ' * 11) + "Node ID !" + nodeID + "\n", "#e8643f", tag=nodeID)
                result = cursor.execute("SELECT * FROM node_info WHERE node_id = ?", (info["num"],)).fetchone()

            if "user" in info:
                tmp = info['user']
                if "id" in tmp and tmp['id'] != '':
                    # Only push to DB if we actually get a node ID
                    nodeID = tmp.get('id', '')[1:]
                    if nodeID != '':
                        if result[5] == nodeID[-4:]:
                            if "shortName" in tmp and "longName" in tmp:
                                lora_sn = str(tmp['shortName'].encode('ascii', 'xmlcharrefreplace'), 'ascii').replace("\n", "")
                                lora_ln = str(tmp['longName'].encode('ascii', 'xmlcharrefreplace'), 'ascii').replace("\n", "")
                                if lora_sn == '':
                                    lora_sn = str(nodeID[-4:])
                                    lora_ln = "Meshtastic " + str(nodeID[-4:])
                                if nodeID == MyLora:
                                    MyLora_SN = lora_sn
                                    MyLora_LN = lora_ln
                                cursor.execute("UPDATE node_info SET mac_id = ?, long_name = ?, short_name = ?, hw_model_id = ?, is_licensed = ? WHERE hex_id = ?", (tmp.get('macaddr', 'N/A'), lora_ln, lora_sn, tmp.get('hwModel', 'N/A'), tmp.get('isLicensed', False) ,nodeID))

                        if "position" in info:
                            tmp2 = info['position']
                            nodelat = round(tmp2.get('latitude', -8.0),6)
                            nodelon = round(tmp2.get('longitude', -8.0),6)
                            nodealt = tmp2.get('altitude', 0)
                            if nodelat != -8.0 and nodelon != -8.0:
                                if result[9] == -8.0 or result[10] == -8.0: # We allready have your position
                                    node_dist = calc_gc(nodelat, nodelon, MyLora_Lat, MyLora_Lon)
                                    cursor.execute("UPDATE node_info SET latitude = ?, longitude = ?, altitude = ?, hopstart = ? , distance = ? WHERE hex_id = ?", (nodelat, nodelon, nodealt, info.get('hopsAway', -1), node_dist, nodeID))
                                    MapMarkerDelete(nodeID)

                        if nodeID == MyLora:
                            if MyLora_Lat != -8.0 and MyLora_Lon != -8.0:
                                if MyLora not in MapMarkers:
                                    MyLora_Lat = result[9]
                                    MyLora_Lon = result[10]
                                    time.sleep(0.5)
                                    MapMarkers[MyLora] = [None, False, tnow, None, None, 0, None]
                                    MapMarkers[MyLora][0] = mapview.set_marker(MyLora_Lat, MyLora_Lon, text=unescape(MyLora_SN), icon_index=1, text_color = '#e67a7f', font = ('Fixedsys', 8), data=MyLora, command = click_command)
                                    MapMarkers[MyLora][0].text_color = '#e67a7f'
                                    zoomhome = False
                            else:
                                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                                insert_colored_text(text_box2, " My Node has no position !!\n", "#e8643f")

                        if "viaMqtt" in info:
                            cursor.execute("UPDATE node_info SET ismqtt = ? WHERE hex_id = ?", (info.get('viaMqtt', False), nodeID))

        cursor.close()

#-------------------------------------------------------------- Side Functions ---------------------------------------------------------------------------

def ez_date(d):
    units = [(31536000, "year"), (2419200, "month"), (604800, "week"), (86400, "day"), (3600, "hour"), (60, "minute")]
    for unit_seconds, unit_name in units:
        if d >= unit_seconds:
            temp = int(d / unit_seconds)
            return f"{temp} {unit_name}{'s' if temp > 1 else ''}"
    return "Just now"

def uptimmehuman(uptime, lastseentime):
    tnow = int(time.time())
    days, remainder = divmod(uptime + (tnow - lastseentime), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    text = 'Uptime   : '
    if days > 0: text += str(days) + ' days, '
    text += str(hours) + ' hours and ' + str(minutes) + ' minutes'
    if tnow - lastseentime >= map_delete: text += ' ? Seems offline'
    return text

def LatLon2qth(latitude, longitude):
    A = ord('A')
    a = divmod(longitude + 180, 20)
    b = divmod(latitude + 90, 10)
    locator = chr(A + int(a[0])) + chr(A + int(b[0]))
    lon = a[1] / 2.0
    lat = b[1]
    i = 1
    while i < 5:
        i += 1
        a = divmod(lon, 1)
        b = divmod(lat, 1)
        if not (i % 2):
            locator += str(int(a[0])) + str(int(b[0]))
            lon = 24 * a[1]
            lat = 24 * b[1]
        else:
            locator += chr(A + int(a[0])) + chr(A + int(b[0]))
            lon = 10 * a[1]
            lat = 10 * b[1]
    return locator

def calc_gc(end_lat, end_long, start_lat, start_long):
    EARTH_R = 6372.8

    start_lat = math.radians(start_lat)
    start_long = math.radians(start_long)
    end_lat = math.radians(end_lat)
    end_long = math.radians(end_long)

    # d_lat = math.fabs(start_lat - end_lat)
    d_long = math.fabs(start_long - end_long)

    y = ((math.sin(start_lat)*math.sin(end_lat)) + (math.cos(start_lat)*math.cos(end_lat)*math.cos(d_long)))
    x = math.sqrt((math.cos(end_lat)*math.sin(d_long))**2 + ( (math.cos(start_lat)*math.sin(end_lat)) - (math.sin(start_lat)*math.cos(end_lat)*math.cos(d_long)))**2)
    c = math.atan(x/y)

    return round(EARTH_R*c,1)

#-------------------------------------------------------------- Plot Functions ---------------------------------------------------------------------------

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import ScalarFormatter
from pandas import DataFrame
from scipy.signal import savgol_filter

plt.switch_backend('TkAgg') # No clue why we even need this
plt.rcParams["font.family"] = 'sans-serif'
plt.rcParams["font.size"] = 7

def plot_rssi_log(node_id, frame, width=512, height=96):
    global MyLora, dbconnection,metrics_age

    metrics = []
    result = get_data_for_node('device_metrics', node_id, days=metrics_age)
    if result:
        metrics = [{'time': int(row[9]), 'snr': row[7], 'rssi': row[8]} for row in result]

    if len(metrics) < 5:
        return None

    df = DataFrame({
        'time': [datetime.fromtimestamp(entry['time']) for entry in metrics],
        'snr': [entry['snr'] for entry in metrics],
        'rssi': [entry['rssi'] for entry in metrics],
    })
    total_minutes = (df['time'].max() - df['time'].min()).total_seconds() / 60
    resample_interval =  max(int(total_minutes // 100), 1)
    df_resampled = df.set_index('time').resample(f'{resample_interval}min').mean().dropna().reset_index()
    times_resampled = df_resampled['time'].tolist()
    snr_resampled = df_resampled['snr'].tolist()
    rssi_levels_resampled = df_resampled['rssi'].tolist()

    if all(value == 0.0 for value in snr_resampled):
        return None
    if all(value == 0 for value in rssi_levels_resampled):
        return None
    if len(snr_resampled) < 5 or len(rssi_levels_resampled) < 5:
        return None

    snr_levels_smooth = savgol_filter(snr_resampled, window_length=5, polyorder=2)
    rssi_smooth = savgol_filter(rssi_levels_resampled, window_length=5, polyorder=2)

    total_hours = 0
    if len(times_resampled) > 1:
        total_hours = (times_resampled[-1] - times_resampled[0]).total_seconds() / 3600

    fig, axs = plt.subplots(1, 2, figsize=(width/100, height/100))
    fig.patch.set_facecolor('#242424')

    # Plot snr
    axs[0].plot(times_resampled, snr_levels_smooth, label='snr', color='#2bd5ff')
    axs[0].set_title('snr')
    axs[0].set_xlabel(None)
    axs[0].set_ylabel(None)
    axs[0].grid(True, color='#444444')
    # Plot rssi
    axs[1].plot(times_resampled, rssi_smooth, label='rssi', color='#c9a500')
    axs[1].set_title('rssi')
    axs[1].set_xlabel(None)
    axs[1].set_ylabel(None)
    axs[1].grid(True, color='#444444')
    for ax in axs.flat:
        ax.set_facecolor('#242424')
        if total_hours <= 12:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        elif total_hours <= 24:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
            ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.title.set_color('white')
        ax.xaxis.label.set_color('white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.set(frame_on=False)
    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()

    return canvas.get_tk_widget()

def plot_metrics_log(node_id, frame, width=512, height=162):
    global MyLora, dbconnection, metrics_age

    metrics = []
    result = get_data_for_node('device_metrics', node_id, days=metrics_age)
    if result:
        metrics = [{'time': int(row[9]), 'battery': row[3], 'voltage': row[4], 'utilization': row[5], 'airutiltx': row[6]} for row in result]

    if len(metrics) < 5:
        return None

    df = DataFrame({
        'time': [datetime.fromtimestamp(entry['time']) for entry in metrics],
        'battery': [entry['battery'] for entry in metrics],
        'voltage': [entry['voltage'] for entry in metrics],
        'utilization': [entry['utilization'] for entry in metrics],
        'airutiltx': [entry['airutiltx'] for entry in metrics]
    })
    total_minutes = (df['time'].max() - df['time'].min()).total_seconds() / 60
    resample_interval =  max(int(total_minutes // 100), 1)
    df_resampled = df.set_index('time').resample(f'{resample_interval}min').mean().dropna().reset_index()
    times_resampled = df_resampled['time'].tolist()
    battery_levels_resampled = df_resampled['battery'].tolist()
    voltages_resampled = df_resampled['voltage'].tolist()
    utilizations_resampled = df_resampled['utilization'].tolist()
    airutiltxs_resampled = df_resampled['airutiltx'].tolist()

    if len(battery_levels_resampled) < 5 or len(voltages_resampled) < 5 or len(utilizations_resampled) < 5 or len(airutiltxs_resampled) < 5:
        return None

    battery_levels_smooth = savgol_filter(battery_levels_resampled, window_length=5, polyorder=2)
    voltages_smooth = savgol_filter(voltages_resampled, window_length=5, polyorder=2)
    utilizations_smooth = savgol_filter(utilizations_resampled, window_length=5, polyorder=2)
    airutiltxs_smooth = savgol_filter(airutiltxs_resampled, window_length=5, polyorder=2)

    total_hours = 0
    if len(times_resampled) > 1:
        total_hours = (times_resampled[-1] - times_resampled[0]).total_seconds() / 3600

    fig, axs = plt.subplots(2, 2, figsize=(width/100, height/100))
    fig.patch.set_facecolor('#242424')

    # Plot battery levels
    axs[0, 0].plot(times_resampled, battery_levels_smooth, label='Battery Level', color='#2bd5ff')
    axs[0, 0].set_title('Battery Level %')
    axs[0, 0].set_xlabel(None)
    axs[0, 0].set_ylabel(None)
    axs[0, 0].grid(True, color='#444444')
    # Plot voltages
    axs[0, 1].plot(times_resampled, voltages_smooth, label='Voltage', color='#c9a500')
    axs[0, 1].set_title('Voltage')
    axs[0, 1].set_xlabel(None)
    axs[0, 1].set_ylabel(None)
    axs[0, 1].grid(True, color='#444444')
    # Plot utilizations
    axs[1, 0].plot(times_resampled, utilizations_smooth, label='Utilization', color='#00c983')
    axs[1, 0].set_title('Utilization %')
    axs[1, 0].set_xlabel(None)
    axs[1, 0].set_ylabel(None)
    axs[1, 0].grid(True, color='#444444')
    # Plot Air Utilization TX
    axs[1, 1].plot(times_resampled, airutiltxs_smooth, label='Air Utilization TX', color='#ee0000')
    axs[1, 1].set_title('Air Utilization TX %')
    axs[1, 1].set_xlabel(None)
    axs[1, 1].set_ylabel(None)
    axs[1, 1].grid(True, color='#444444')
    for ax in axs.flat:
        ax.set_facecolor('#242424')
        if total_hours <= 12:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        elif total_hours <= 24:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
            ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.title.set_color('white')
        ax.xaxis.label.set_color('white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.set(frame_on=False)
    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()

    return canvas.get_tk_widget()

def plot_environment_log(node_id, frame , width=512, height=106):
    global metrics_age
    metrics = []
    result = get_data_for_node('environment_metrics', node_id, days=metrics_age)
    if result:
        metrics = [{'time': int(row[8]), 'temperatures': row[3], 'humidities': row[4], 'pressures': row[5]} for row in result]

    if len(metrics) < 5:
        return None

    df = DataFrame({
        'time': [datetime.fromtimestamp(entry['time']) for entry in metrics],
        'temperatures': [entry['temperatures'] for entry in metrics],
        'humidities': [entry['humidities'] for entry in metrics],
        'pressures': [entry['pressures'] for entry in metrics],
    })
    total_minutes = (df['time'].max() - df['time'].min()).total_seconds() / 60
    resample_interval =  max(int(total_minutes // 100), 1)
    df_resampled = df.set_index('time').resample(f'{resample_interval}min').mean().dropna().reset_index()
    times = df_resampled['time'].tolist()
    temperatures_resampled = df_resampled['temperatures'].tolist()
    humidities_resampled = df_resampled['humidities'].tolist()
    pressures_resampled = df_resampled['pressures'].tolist()

    if len(temperatures_resampled) < 5 or len(humidities_resampled) < 5 or len(pressures_resampled) < 5:
        return None

    temperatures = savgol_filter(temperatures_resampled, window_length=5, polyorder=2)
    humidities = savgol_filter(humidities_resampled, window_length=5, polyorder=2)
    pressures = savgol_filter(pressures_resampled, window_length=5, polyorder=2)

    total_hours = 0
    if len(times) > 1:
        total_hours = (times[-1] - times[0]).total_seconds() / 3600

    fig, ax1 = plt.subplots(figsize=(width/100, height/100))
    fig.patch.set_facecolor('#242424')

    ax1.set_facecolor('#242424')
    if total_hours <= 12:
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    elif total_hours <= 24:
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    else:
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
        ax1.xaxis.set_major_locator(mdates.DayLocator())

    ax1.plot(times, temperatures, '#c9a500', label='Temperature (°C)')
    ax1.plot(times, humidities, '#2bd5ff', label='Humidity (%)')
    ax1.tick_params(axis='y', labelcolor='white', colors='white')
    ax1.tick_params(axis='x', colors='white')
    ax1.grid(True, color='#444444')
    ax1.set(frame_on=False)
    # Set y-axis limits to extend 10 units above and below the min and max values
    min_temp = min(temperatures)
    max_temp = max(temperatures)
    min_humidity = min(humidities)
    max_humidity = max(humidities)
    ax1.set_ylim(min(min_temp, -15.0), max(120.0, max_humidity))

    # Add pressure data if available
    if pressures[-1] != 0 and pressures[0] != 0:
        ax2 = ax1.twinx()
        ax2.set_facecolor('#242424')
        ax2.plot(times, pressures, '#00c983', label='Pressure (hPa)')
        ax2.tick_params(axis='y', labelcolor='white', colors='white')
        ax2.grid(False)
        ax2.set(frame_on=False)
        formatter = ScalarFormatter(useOffset=False)
        formatter.set_scientific(False)
        ax2.yaxis.set_major_formatter(formatter)

    fig.legend(loc='upper center', ncol=3, facecolor='#242424', edgecolor='#242424', labelcolor='linecolor')
    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()

    return canvas.get_tk_widget()

def plot_movment_curve(node_id, frame, width=512, height=102):
    global metrics_age
    positions = []
    result = get_data_for_node('movement_log', node_id, days=1)
    if result:
        positions = [{'time': int(row[2]), 'altitude': row[8]} for row in result]

    if len(positions) < 5:
        return None

    times = [entry['time'] for entry in positions]
    altitudes = [entry['altitude'] for entry in positions]
    dates = [datetime.fromtimestamp(time) for time in times]
    
    fig, ax = plt.subplots(figsize=(width/100, height/100))
    fig.patch.set_facecolor('#242424')
    ax.set_facecolor('#242424')
    ax.plot(dates, altitudes, marker='.', linestyle='-', color='#2bd5ff')

    total_hours = 0
    if len(times) > 1:
        total_hours = (times[-1] - times[0]) / 3600

    if total_hours <= 12:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    elif total_hours <= 24:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
        ax.xaxis.set_major_locator(mdates.DayLocator())

    ax.title.set_color('white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')
    ax.set(frame_on=False)
    # ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    # ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.set_title('Altitude change in meters')
    ax.grid(True, color='#444444')

    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()

    return canvas.get_tk_widget()

'''
# Test for later on to add image like signal strength as an emoticon
def crop_image(image_path, crop_area):
    with Image.open(image_path) as img:
        cropped_image = img.crop(crop_area)
        return cropped_image

def insert_image_to_text(text_widget, image_path, crop_area):
    cropped_image = crop_image(image_path, crop_area)
    tk_image = ImageTk.PhotoImage(cropped_image)
    
    text_widget.image_create("end", image=tk_image)
    text_widget.image = tk_image  # Keep a reference to avoid garbage collection

    # image_path = 'path_to_your_emoticons_image.png'  # Path to your image file
    # emoticon_area = (10, 10, 50, 50)  # Define the crop area for the specific emoticon (left, upper, right, lower)
    # insert_image_to_text(text_widget, image_path, emoticon_area)
'''

def has_open_figures():
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        fig.clear()
        plt.close(fig)
        del fig
    plt.figure().clear()
    plt.cla()
    plt.clf()
    plt.close()
    return bool(plt.get_fignums())

def destroy_overlay():
    try:
        overlay.destroy()
    except Exception as e:
        logging.error("Error destroying overlay: ", str(e))

#---------------------------------------------------------------- Start Mains -----------------------------------------------------------------------------

if __name__ == "__main__":
    os.system("")
    gc.enable()
    isLora = True

    def on_closing():
        global isLora, meshtastic_client, mapview, root, dbconnection
        isLora = False
        if meshtastic_client is not None:
            try:
                logging.error("Closing link to meshtastic client (Exit)")
                pub.unsubscribe(on_lost_meshtastic_connection, "meshtastic.connection.lost")
                pub.unsubscribe(on_meshtastic_message, "meshtastic.receive")
                meshtastic_client.close()
            except Exception as e:
                logging.error("Error closing meshtastic client: ", str(e))
        if dbconnection is not None:
            try:
                # Finish any commit and close the database
                logging.error("Cleaning and closing Databases (Exit)")
                dbconnection.commit()
                dbconnection.execute("VACUUM")
                dbconnection.close()
            except Exception as e:
                logging.error("Error closing database connection: ", str(e))
        logging.error("Closed Program, Bye! (Exit)")
        # mapview.destroy()
        root.quit()
        exit()

    # Initialize the main window
    def create_text(frame, row, column, frheight, frwidth):
        # Create a frame with a black background to simulate padding color
        padding_frame = Frame(frame, background="#121212", padx=2, pady=2)
        padding_frame.grid(row=row, column=column, rowspan=1, columnspan=1, padx=0, pady=0, sticky='nsew')
        
        # Configure grid layout for the padding frame
        padding_frame.grid_rowconfigure(0, weight=1)
        padding_frame.grid_columnconfigure(0, weight=1)
        
        # Create a text widget inside the frame
        text_area = Text(padding_frame, wrap='word', width=frwidth, height=frheight, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), undo=False)
        text_area.grid(row=0, column=0, sticky='nsew')
        return text_area

    def send_message(tx, to="^all", wa=False, wr=False, ch=0):
        global meshtastic_client, mylorachan, MyLora, MyLora_SN, MyLora_LN, text_box2
        tx = tx.strip()
        sendto = to
        if sendto != "^all":
            sendto = '!' + to
        print(f"Sending message to {to} on channel {ch}")
        # neeed check max, some seem to say 237 ?
        if len(tx.encode('utf-8')) <= 220 and tx != '':
            meshtastic_client.sendText(
                text=tx,
                destinationId=sendto,
                wantAck=wa,
                wantResponse=wr,
                channelIndex=ch
            )
            toid = mylorachan[ch]
            if to != "^all":
                toid = to
            add_message(MyLora, tx, int(time.time()), msend=toid)
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(f"{MyLora_SN} ({MyLora_LN})") + "\n", "#d1d1d1")
            insert_colored_text(text_box2, (' ' * 11) + '[to ' + str(toid) +'] ' + tx + '\n', "#00c983")
            playsound('Data' + os.path.sep + 'NewChat.mp3')

    def prechat_priv(message, nodeid):
        global my_chat
        print(f"Sending private message to {nodeid}")
        if message != '':
            send_message(message, to=nodeid, ch=0)
            my_chat.set("")

    def prechat_chan(event=None):
        global chan2send
        text2send = my_msg.get()
        if len(text2send.encode('utf-8')) > 220:
            insert_colored_text(text_box2, "Text message to long, keep it under 220 bytes\n", "#d1d1d1")
        elif text2send != '':
            if text2send == '/neighbors':
                neighbors_update()
            else:
                send_message(text2send, ch=chan2send)
                my_msg.set("")

    # runnign send_position, send_telemetry, send_trace in threads so they do not block the main loop; 
    # however, right now send_trace might cause a tread to stay open and cause the program to not close properly.
    def timeout():
        thread = threading.current_thread()
        if thread.is_alive():
            raise TimeoutError("Operation timed out")

    def req_meta():
        global meshtastic_client, loop, ok2Send
        timer = threading.Timer(60.0, timeout)
        timer.start()
        try:
            meshtastic_client.localNode.getMetadata()
        except TimeoutError as e:
            logging.error("Timeout requesting metadata: %s", str(e))
        except Exception as e:
            logging.error("Error requesting metadata: %s", str(e))
        finally:
            timer.cancel()
            print(f"Finished requesting metadata")
            ok2Send = 0

    def send_position(nodeid):
        global meshtastic_client, loop, ok2Send
        print(f"Requesting Position Data from {nodeid}")
        timer = threading.Timer(60.0, timeout)
        timer.start()
        try:
            meshtastic_client.sendPosition(destinationId=nodeid, wantResponse=True, channelIndex=0)
        except TimeoutError as e:
            logging.error("Timeout sending Position: %s", str(e))
        except Exception as e:
            logging.error("Error sending Position: %s", str(e))
        finally:
            timer.cancel()
            print(f"Finished sending Position")
            ok2Send = 0

    def send_telemetry(nodeid):
        global meshtastic_client, loop, ok2Send
        print(f"Requesting Telemetry Data from {nodeid}")
        timer = threading.Timer(60.0, timeout)
        timer.start()
        try:
            meshtastic_client.sendTelemetry(destinationId=nodeid, wantResponse=True, channelIndex=0)
        except TimeoutError as e:
            logging.error("Timeout sending Telemetry: %s", str(e))
        except Exception as e:
            logging.error("Error sending Telemetry: %s", str(e))
        finally:
            timer.cancel()
            print(f"Finished sending Telemetry")
            ok2Send = 0

    def send_trace(nodeid):
        global meshtastic_client, loop, ok2Send
        print(f"Requesting Traceroute Data from {nodeid}")
        timer = threading.Timer(60.0, timeout)
        timer.start()
        try:
            meshtastic_client.sendTraceRoute(dest=nodeid, hopLimit=7, channelIndex=0)
        except TimeoutError as e:
            logging.error("Timeout sending Traceroute: %s", str(e))
        except Exception as e:
            logging.error("Error sending Traceroute: %s", str(e))
        finally:
            timer.cancel()
            print(f"Finished sending Traceroute")
            ok2Send = 0

    def close_overlay():
        global overlay, lastchat, chat_input, text_box4
        lastchat = []
        playsound('Data' + os.path.sep + 'Button.mp3')

        if chat_input is not None:
            chat_input.unbind("<Return>")
            chat_input = None
            text_box4.bind("<Return>", send_message)

        if overlay is not None:
            destroy_overlay()
        if has_open_figures():
            logging.debug("Closing open figures failed?")

        gc.collect()

    # Hadnle the buttons
    def buttonpress(info, nodeid):
        global ok2Send, telemetry_thread, position_thread, trace_thread, MyLora_SN, MyLora_LN
        text_from = MyLora_SN + " (" + MyLora_LN + ")"
        if ok2Send == 0:
            ok2Send = 15
            node_id = '!' + str(nodeid)
            if info == 'ReqInfo':
                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
                insert_colored_text(text_box2, (' ' * 11) + "Node Telemetry sending Telemetry request\n", "#2bd5ff")
                telemetry_thread = threading.Thread(target=send_telemetry, args=(node_id,))
                telemetry_thread.start()
            elif info == 'ReqPos':
                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
                insert_colored_text(text_box2, (' ' * 11) + "Node Position sending Position request\n", "#2bd5ff")
                position_thread = threading.Thread(target=send_position, args=(node_id,))
                position_thread.start()
            elif info == 'ReqTrace':
                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
                insert_colored_text(text_box2, (' ' * 11) + "Node TraceRoute sending Trace Route request\n", "#2bd5ff")
                trace_thread = threading.Thread(target=send_trace, args=(node_id,))
                trace_thread.start()
        else:
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
            insert_colored_text(text_box2, (' ' * 11) + "Please wait before the next request, 30 secconds inbetween requests\n", "#2bd5ff")

    def update_chat_log():
        global dbconnection, MyLora, MyLora_SN, MyLora_LN, lastchat
        nodeid = lastchat[0]
        nodesn = lastchat[1]
        nodeln = lastchat[2]
        chat_box = lastchat[3]
        with dbconnection:
            cursor = dbconnection.cursor()
            query = f"SELECT * FROM chat_log WHERE node_id = '{nodeid}' AND sendto = '{MyLora}' OR sendto = '{nodeid}' AND node_id = '{MyLora}' ORDER BY timerec ASC;"
            results = cursor.execute(query).fetchall()
            cursor.close()
        chat_box.configure(state="normal")
        chat_box.delete("1.0", 'end')
        if results:
            for entry in results:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry[1]))
                tcolor = "#00c983"
                if entry[0] == MyLora:
                    tcolor = "#2bd5ff"
                    txtfrom = MyLora_SN + " (" + MyLora_LN + ")"
                else:
                    txtfrom = nodesn + " (" + nodeln + ")"
                insert_colored_text(chat_box, f" {unescape(txtfrom)}\n", "#d1d1d1")
                ptext = unescape(entry[6]).strip()
                ptext = textwrap.fill(ptext, 62)
                ptext = textwrap.indent(text=ptext, prefix='  ', predicate=lambda line: True)
                insert_colored_text(chat_box, f"  {ptext}\n", tcolor)
                insert_colored_text(chat_box, timestamp.rjust(63) + '\n', "#818181")
        else:
            insert_colored_text(chat_box, "\n  No messages found\n", "#dddddd")

    lastchat = []

    chat_input = None

    def chatbox(nodeid, nodesn, nodeln):
        global overlay, my_chat, chat_input, lastchat, chat_input
        playsound('Data' + os.path.sep + 'Button.mp3')
        if overlay is not None:
            destroy_overlay()
        if has_open_figures():
            logging.debug("No fromId in packet")
        
        overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#777777', highlightcolor="#777777",highlightthickness=1, takefocus=True, border=1)
        overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame
        chat_label = Label(overlay, text=unescape(nodesn) + '\n' + unescape(nodeln), font=('Fixedsys', 12), bg='#242424', fg='#2bd5ff')
        chat_label.pack(side="top", fill="x", pady=3)
        chat_box = Text(overlay, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), width=64, height=12)
        chat_box.pack_propagate(False)  # Prevent resizing based on the content
        chat_box.pack(side="top", fill="both", expand=True, padx=10, pady=3)

        lastchat = [nodeid, nodesn, nodeln, chat_box]
        update_chat_log()

        chat_input = Entry(overlay, textvariable=my_chat, width=50, bg='#242424', fg='#eeeeee', font=('Fixedsys', 10))
        chat_input.pack(side="top", fill="x", padx=10, pady=3)

        text_box4.unbind("<Return>")
        chat_input.bind("<Return>", prechat_priv(chat_input.get(), nodeid))

        button_frame = Frame(overlay, bg='#242424')
        button_frame.pack(pady=12)
        send_button = Button(button_frame, image=btn_img, command=lambda: prechat_priv(chat_input.get(), nodeid), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Send Message", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        send_button.pack(side='left', padx=2)
        clear_button = Button(button_frame, image=btn_img, command=lambda: print("Button Clear clicked"), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Clear Chat", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        clear_button.pack(side='left', padx=2)
        close_button = Button(button_frame, image=btn_img, command=lambda: close_overlay(), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Close Chat", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        close_button.pack(side='left', padx=2)

    def click_command(marker):
        global MyLora, overlay, mapview, dbconnection
        # Destroy the existing overlay if it exists
        playsound('Data' + os.path.sep + 'Button.mp3')
        if overlay is not None:
           destroy_overlay()
        if has_open_figures():
            logging.debug("Closing open figures failed?")

        dbcursor = dbconnection.cursor()
        result = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (marker.data,)).fetchone()
        dbcursor.close()
        if result is None:
            logging.error(f"Node {marker.data} not in database")
            return

        overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#777777', highlightcolor="#777777",highlightthickness=1, takefocus=True, border=1)
        overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame

        info_label = Text(overlay, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), width=64, height=13, highlightbackground='#242424', highlightthickness=0)
        info_label.grid(row=0, column=0, columnspan=2, padx=1, pady=1, sticky='nsew')

        insert_colored_text(info_label, "⬢ ", "#" + marker.data[-6:],  center=True)
        if result[4] != '':
            text_loc = unescape(result[5]) + '\n' + unescape(result[4]) + '\n'
        else:
            text_loc = unescape(result[5]) + '\n'
        insert_colored_text(info_label, text_loc, "#2bd5ff",  center=True)
        insert_colored_text(info_label, "─" * 30 + "\n", "#414141",  center=True)

        if result[9] != -8.0 and result[10] != -8.0:
            text_loc = '  Position : ' + str(result[9]) + ' / ' + str(result[10]) + ' (' + LatLon2qth(result[9],result[10])[:-2] + ')'
            text_loc += ' Altitude ' + str(result[11]) + 'm\n'
        else:
            text_loc = '  Position : Unknown\n'

        insert_colored_text(info_label, text_loc, "#d2d2d2",  center=True)
        insert_colored_text(info_label, "─" * 30 + "\n", "#414141",  center=True)

        text_loc = '\n  HW Model : ' + str(result[6]) + '\n'
        text_loc += '  Hex ID   : ' + '!' + str(result[3]).ljust(18)
        text_loc += 'MAC Addr  : ' + str(result[2]) + '\n'
        # Add uptime back
        if result[14] and int(result[14]) != 0:
            text_loc += '  ' + uptimmehuman(int(result[14]), int(result[1])) + '\n'
        text_loc += '  Last SNR : ' + str(result[16]).ljust(19)
        text_loc += 'Last Seen : ' + ez_date(int(time.time()) - result[1]) + '\n'
        text_loc += '  Power    : ' + str(result[19]).ljust(19)
        text_loc += 'First Seen: ' + datetime.fromtimestamp(result[13]).strftime('%b %#d \'%y')
        if marker.data != MyLora:
            if result[24] != 0.0:
                text_loc += '\n  Distance : ' + (str(result[24]) + 'km').ljust(19)
            else:
                text_loc += '\n  Distance : ' + ('Unknown').ljust(19)

            if result[23] > 0:
                text_loc += 'HopsAway  : ' + str(result[23])

        text_naib = ''
        dbcursor = dbconnection.cursor()
        for key in HeardDB.keys():
            if idToHex(key[0])[1:] == marker.data and key[1] != MyLoraID:
                # yada = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (idToHex(key[1])[1:],)).fetchone()
                # if yada is not None:
                text_naib += f" {str(HeardDB[key][3])} ({str(HeardDB[key][1])}dB),"
                # else:
                #    text_naib += f" !{key[1]} ({str(HeardDB[key][1])}dB),"
        dbcursor.close()
        if text_naib != '':
            text_loc += '\n  Naibors  :' + text_naib[:-1]

        insert_colored_text(info_label, text_loc, "#d2d2d2")

        plot_frame = Frame(overlay, bg='#242424')
        plot_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky='nsew')

        plot_functions = [plot_metrics_log, plot_rssi_log, plot_environment_log, plot_movment_curve]
        row, col = 0, 0
        for plot_func in plot_functions:
            plot_widget = plot_func(marker.data, plot_frame, width=448, height=164)
            if plot_widget:
                plot_widget.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
                col += 1
                if col > 1:
                    col = 0
                    row += 1

        # Create a frame to hold the buttons
        button_frame = Frame(overlay, bg='#242424')
        button_frame.grid(row=2, column=0, columnspan=2, pady=2, sticky='nsew')
        if result[3] != MyLora:
            button1 = Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqInfo', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Request Info", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button1.grid(row=0, column=0, padx=(0, 1), sticky='e')
            button2 = Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqPos', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Request Pos", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button2.grid(row=0, column=1, padx=(0, 0), sticky='ew')
            button3 = Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqTrace', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Trace Node", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button3.grid(row=0, column=2, padx=(1, 0), sticky='w')

        button_frame2 = Frame(overlay, bg='#242424')
        button_frame2.grid(row=3, column=0, columnspan=2, pady=2, sticky='nsew')

        button4 = Button(button_frame2, image=btn_img, command=lambda: mapview.set_position(result[9], result[10]) if result[9] != -8.0 and result[10] != -8.0 else None, borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Zoom", compound="center", fg='#d1d1d1' if result[9] != -8.0 and result[10] != -8.0 else '#616161', font=('Fixedsys', 10))
        button4.grid(row=0, column=0, padx=(0, 1), sticky='e')
        button5 = Button(button_frame2, image=btn_img, command=lambda: close_overlay(), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Close", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        button5.grid(row=0, column=1, padx=(0, 0), sticky='ew')
        button6 = Button(button_frame2, image=btn_img, command=lambda: chatbox(result[3], result[5], result[4]), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Chat", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        button6.grid(row=0, column=2, padx=(1, 0), sticky='w')

        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        button_frame2.grid_columnconfigure(0, weight=1)
        button_frame2.grid_columnconfigure(1, weight=1)
        button_frame2.grid_columnconfigure(2, weight=1)

    # Function to update the middle frame with the last 30 active nodes
    peekmem = 0

    def checknode(node_id, icon, color, lat, lon, nodesn, drawme=True):
        global MapMarkers, mapview
        tmp = False
        if icon == 2: tmp = True
        
        if node_id in MapMarkers:
            if (drawme == False and icon != 4) or drawme == True:
                if MapMarkers[node_id][0] != None:
                    if hasattr(MapMarkers[node_id][0], 'text_color'):
                        if MapMarkers[node_id][0].text_color != color:
                            MapMarkerDelete(node_id)
                            MapMarkers[node_id][0].delete()
                            MapMarkers[node_id][0] = None
                            MapMarkers[node_id][0] = mapview.set_marker(lat, lon, text=nodesn, icon_index=icon, text_color = color, font = ('Fixedsys', 8), data=node_id, command = click_command)
                            MapMarkers[node_id][0].text_color = color
                    else:
                        MapMarkerDelete(node_id)
                        MapMarkers[node_id][0].delete()
                        MapMarkers[node_id][0] = None
                        MapMarkers[node_id][0] = mapview.set_marker(lat, lon, text=nodesn, icon_index=icon, text_color = color, font = ('Fixedsys', 8), data=node_id, command = click_command)
                        MapMarkers[node_id][0].text_color = color
                else:
                    MapMarkers[node_id][0] = mapview.set_marker(lat, lon, text=nodesn, icon_index=icon, text_color = color, font = ('Fixedsys', 8), data=node_id, command = click_command)
                    MapMarkers[node_id][0].text_color = color
                MapMarkers[node_id][1] = tmp
            else:
                MapMarkerDelete(node_id)
                MapMarkers[node_id][0].delete()
                MapMarkers[node_id][0] = None
                del MapMarkers[node_id]
        else:
            if lat != -8.0 and lon != -8.0:
                if (drawme == False and icon != 4) or drawme == True:
                    tmp = False
                    if icon == 2: tmp = True
                    MapMarkers[node_id] = [None, tmp, int(time.time()), None, None, 0, None]
                    MapMarkers[node_id][0] = mapview.set_marker(lat, lon, text=nodesn, icon_index=icon, text_color = color, font = ('Fixedsys', 8), data=node_id, command = click_command)
                    MapMarkers[node_id][0].text_color = color
                    MapMarkers[node_id][1] = tmp

    def update_active_nodes():
        global MyLora, MyLoraText1, MyLoraText2, tlast, MapMarkers, ok2Send, peekmem, dbconnection, MyLora_Lat, MyLora_Lon, incoming_uptime, package_received_time
        start = time.perf_counter()
        tnow = int(time.time())

        if ok2Send != 0:
            ok2Send -= 1
            if ok2Send < 0: ok2Send = 0

        text_box_middle.configure(state="normal")
        current_view = text_box_middle.yview()
        
        # Unbind all tags from text_box_middle
        for tag in text_box_middle.tag_names():
            text_box_middle.tag_unbind(tag, "<Button-1>")
        text_box_middle.delete("1.0", 'end')

        insert_colored_text(text_box_middle, "\n " + MyLora_SN.ljust(12), "#e67a7f", tag=MyLora)

        if incoming_uptime != 0:
            elapsed_time = tnow - package_received_time
            delta = timedelta(seconds=(incoming_uptime + elapsed_time))
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            tmp = f"{days}d{hours}h" if days > 0 else f"{hours}h{minutes}m"
            insert_colored_text(text_box_middle, tmp.rjust(7) + '\n', "#9d9d9d")
        else:
            insert_colored_text(text_box_middle,'\n', "#9d9d9d")

        if MyLoraText1:
            insert_colored_text(text_box_middle, MyLoraText1, "#c1c1c1")
        if MyLoraText2:
            insert_colored_text(text_box_middle, MyLoraText2, "#c1c1c1")


        try:
            cursor = dbconnection.cursor()
            result = cursor.execute(
                "SELECT * FROM node_info WHERE (? - timerec) <= ? ORDER BY timerec DESC",
                (tnow, map_oldnode + 60)
            ).fetchall()
            cursor.close()

            drawoldnodes = mapview.draw_oldnodes
            nodes_to_delete = []
            nodes_to_update = []
            yeet = map_delete
            if drawoldnodes:
                yeet = map_oldnode

            for row in result:
                node_id = row[3]
                node_time = row[1]
                timeoffset = tnow - node_time

                if timeoffset >= yeet and node_id != MyLora:
                    if node_id in MapMarkers:
                        nodes_to_delete.append(node_id)
                elif timeoffset < yeet and node_id != MyLora:
                    nodes_to_update.append((node_id, node_time, row))

            # Batch delete nodes
            for node_id in nodes_to_delete:
                MapMarkerDelete(node_id)
                MapMarkers[node_id][0].delete()
                MapMarkers[node_id][0] = None
                del MapMarkers[node_id]

            # Batch update nodes
            for node_id, node_time, row in nodes_to_update:
                node_id = row[3]
                node_name = unescape(row[5]).strip()
                node_time = row[1]
                if tnow - row[1] >= map_delete:
                    if node_id in MapMarkers:
                        MapMarkerDelete(node_id)
                    checknode(node_id, 4, '#aaaaaa', row[9], row[10], node_name, drawoldnodes)
                else:
                    node_wtime = ez_date(tnow - node_time).rjust(10)
                    node_dist = ' '
                    if row[24] != 0.0:
                        node_dist = "%.1f" % row[24] + "km"
                    elif row[9] != -8.0 and row[10] != -8.0:
                        node_dist = round(calc_gc(row[9], row[10], MyLora_Lat, MyLora_Lon), 2)
                        cursor = dbconnection.cursor()
                        cursor.execute("UPDATE node_info SET distance = ? WHERE hex_id = ?", (node_dist, node_id))
                        cursor.close()
                        node_dist = "%.1f" % node_dist + "km"
                    insert_colored_text(text_box_middle, ('─' * 14) + '\n', "#414141")
                    if row[15]:
                        insert_colored_text(text_box_middle, f" {node_name.ljust(9)}", "#c9a500", tag=str(node_id))
                        insert_colored_text(text_box_middle, f"{node_wtime}\n", "#9d9d9d")
                        insert_colored_text(text_box_middle, f" {node_dist.ljust(9)}\n", "#9d9d9d")
                        checknode(node_id, 3, '#2bd5ff', row[9], row[10], node_name, drawoldnodes)
                    else:
                        node_sig = (' ' + str(row[16]) + 'dB').rjust(10)
                        # ["#de6933", "#c9a500", "#00c983"] # red, yellow, green
                        if row[16] > -7:
                            color = "#00c983"  # green
                        elif -15 <= row[16] <= -7:
                            color = "#c9a500"  # orange
                        else:
                            color = "#de6933"  # red
                        insert_colored_text(text_box_middle, f" {node_name.ljust(9)}", "#00c983", tag=str(node_id))
                        insert_colored_text(text_box_middle, f"{node_wtime}\n", "#9d9d9d")
                        insert_colored_text(text_box_middle, f" {node_dist.ljust(9)}", "#9d9d9d")
                        insert_colored_text(text_box_middle, f"{node_sig}\n", color)

                        checknode(node_id, 2, '#2bd5ff', row[9], row[10], node_name, drawoldnodes)
        except Exception as e:
            logging.error(f"Error updating active nodes: {e}")

        # Just some stats for checks
        insert_colored_text(text_box_middle, '\n' + ('─' * 14), "#3d3d3d")
        time1 = (time.perf_counter() - start) * 1000
        insert_colored_text(text_box_middle, f'\n Update  : {time1:.2f}ms', "#9d9d9d")

        time1 = Process(os.getpid()).memory_full_info()[-1] / 1024 ** 2 # Process(os.getpid()).memory_info().rss / 1024 ** 2
        if peekmem < time1: peekmem = time1
        insert_colored_text(text_box_middle, f"\n Mem     : {time1:.1f}MB\n", "#9d9d9d")
        insert_colored_text(text_box_middle, f" Mem Max : {peekmem:.1f}MB\n\n", "#9d9d9d")

        insert_colored_text(text_box_middle, " F5 Show Node DB\n F6 Map Extend Mode\n", "#9d9d9d")

        text_box_middle.yview_moveto(current_view[0])
        text_box_middle.configure(state="disabled")

        root.after(1000, update_paths_nodes)
    ### end

    def parse_result(result):
        # Split the string by the delimiter separating the tuples
        parts = result.split('),(')
        
        # Add parentheses back to the split parts
        parts = [part + ')' if not part.endswith('))') else part for part in parts]
        parts = ['(' + part if not part.startswith('(') else part for part in parts]
        
        # Apply literal_eval to each part
        parsed_results = [ast.literal_eval(part) for part in parts]
        
        return parsed_results

    # Function to unbind tags for a specific range
    def unbind_tags_for_range(text_widget, start, end):
        for tag in text_widget.tag_names(start):
            text_widget.tag_remove(tag, start, end)
            text_widget.tag_unbind(tag, "<Any-Event>")  # Unbind all events for the tag

    def update_paths_nodes():
        global MyLora, MapMarkers, tlast, pingcount, overlay, dbconnection, mapview, map_oldnode, metrics_age, map_delete, max_lines, map_trail_age, root, MyLora_Lat, MyLora_Lon, zoomhome
        tnow = int(time.time())

        if MyLora_Lat != -8.0 and MyLora_Lon != -8.0 and zoomhome == False:
            zoomhome = True
            mapview.set_zoom(11)
            mapview.set_position(MyLora_Lat, MyLora_Lon)

        # Delete or check old heard nodes
        deloldheard(map_delete)

        # Let rework mHeard Lines
        with dbconnection:
            cursor = dbconnection.cursor()

            result = cursor.execute("SELECT * FROM node_info  WHERE (? - timerec) <= ? ORDER BY timerec DESC", (tnow, map_oldnode)).fetchall()
            for row in result:
                node_id = row[3]
                node_time = row[1]
                if node_id in MapMarkers:
                    if MapMarkers[node_id][6] != None and (tnow - node_time) >= 3:
                        MapMarkers[node_id][6].change_icon(7)

                    if MapMarkers[node_id][4] != None and MapMarkers[node_id][5] <= 0:
                        MapMarkers[node_id][4].delete()
                        MapMarkers[node_id][4] = None

                    if mapview.draw_trail:
                        positions = get_data_for_node('movement_log', node_id, days=1)
                        if len(positions) > 1 and tnow - node_time <= map_oldnode:
                            if MapMarkers[node_id][5] <= 0:
                                drawline = []
                                for position in positions:
                                    pos = (position[6], position[7])
                                    drawline.append(pos)
                                pos = (row[9], row[10])
                                drawline.append(pos)
                                MapMarkers[node_id][4] = mapview.set_path(drawline, color="#751919", width=2, name=node_id)
                                MapMarkers[node_id][5] = 30
                            else:
                                MapMarkers[node_id][5] -= 1
                        if tnow - node_time > map_oldnode and MapMarkers[node_id][4] != None:
                            MapMarkers[node_id][4].delete()
                            MapMarkers[node_id][4] = None
                            MapMarkers[node_id][5] = 0

            if tnow > tlast + 900:
                tlast = tnow
                updatesnodes()

                # Clear up text_box1 so it max has 1000 lines
                line_count = text_box1.count("1.0", "end-1c", "lines")[0]
                if line_count > max_lines:
                    delete_count = (line_count - max_lines) + 10
                    text_box1.configure(state="normal")

                    # Unbind tags for the specific range before deleting
                    unbind_tags_for_range(text_box1, "1.0", f"{delete_count}.0")

                    text_box1.delete("1.0", f"{delete_count}.0")
                    text_box1.configure(state="disabled")
                    print(f"Clearing Frame 1 ({delete_count} lines)")

                # Clear up text_box2 so it max has 1000 lines
                line_count = text_box2.count("1.0", "end-1c", "lines")[0]
                if line_count > max_lines:
                    delete_count = (line_count - max_lines) + 10
                    text_box2.configure(state="normal")

                    # Unbind tags for the specific range before deleting
                    unbind_tags_for_range(text_box2, "1.0", f"{delete_count}.0")

                    text_box2.delete("1.0", f"{delete_count}.0")
                    text_box2.configure(state="disabled")
                    print(f"Clearing Frame 2 ({delete_count} lines)")

                if overlay is None:
                    if has_open_figures():
                        logging.debug("Closing open figures failed?")

                # Delete entries older than metrics_age from each table and then Optimize/Vacuum the database
                tables = ['device_metrics', 'environment_metrics', 'chat_log', 'naibor_info']
                for table in tables:
                    query = f"DELETE FROM {table} WHERE DATETIME(timerec, 'auto') < DATETIME('now', '-{metrics_age} day');"
                    cursor.execute(query)
                query = f"DELETE FROM movement_log WHERE DATETIME(timerec, 'auto') < DATETIME('now', '-1 day');"
                cursor.execute(query)

                # Send weather update
                weather_update()

                gc.collect()

            cursor.close()

        if root.meshtastic_interface is not None:
            pingcount += 1
            if pingcount > 5:
                pingcount = 0
                try:
                    meshtastic_client.sendHeartbeat()
                except Exception as e:
                    logging.error(f"Error sending Ping: {e}")
                    print(f"Error sending Ping: {e}")

        root.after(1000, update_active_nodes)

    # A Litle Fun with Weather, using the json file from a weather station and sending it to mesh
    if config.get('meshtastic', 'weatherbeacon') == 'True':
        from urllib.request import urlopen
        from json import load as json_load
        from meshtastic.protobuf import portnums_pb2, telemetry_pb2, mesh_pb2

    # Under construction, not sure yet if this be correct; needs testing!
    # option to manually send NeighborInfo
    '''
    Kanaal 0 -> Primair -> MeshNet      Key : AQ==
    Kanaal 1 -> Sec     -> LongFast     Key : AQ==
    Kanaal 2 -> Sec     -> LongMod      Key : AQ==
    Kanaal 3 -> Sec     -> Longslow     Key : AQ==
    Kanaal 4 -> Sec     -> Privé        Key: ....
    '''
    def neighbors_update():
        global meshtastic_client, MyLoraID, MyLora, HeardDB
        tmp = 0
        text_raws = 'Node Neighborinfo'
        neighbors_data = mesh_pb2.NeighborInfo()
        neighbors_data.last_sent_by_id = MyLoraID
        for key in HeardDB.keys():
            if key[0] == MyLoraID and key[1] != MyLoraID:
                neighbor = neighbors_data.neighbors.add()
                neighbor.node_id = key[1]
                neighbor.snr = HeardDB[key][1]
                text_raws += '\n' + (' ' * 11) + str(HeardDB[key][3]) + ' (' + str(HeardDB[key][1]) + 'dB)'
                if HeardDB[key][0] > tmp:
                    tmp = HeardDB[key][0]
                    neighbors_data.last_sent_by_id = key[1]

        neighbors_data.node_id = MyLoraID
        neighbors_data.node_broadcast_interval_secs = (60 * 18)  # 18 minutes

        meshtastic_client.sendData(
            neighbors_data,
            destinationId = "^all",
            portNum = portnums_pb2.PortNum.NEIGHBORINFO_APP,
            wantResponse = False,
            channelIndex = 0,
            hopLimit = 3
        )
        insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + '] ' + unescape(f"{MyLora_SN} ({MyLora_LN})") + "\n", "#d1d1d1")
        insert_colored_text(text_box2, (' ' * 11) + text_raws + '\n', "#00c983")

    def weather_update():
        global meshtastic_client, MyLoraID, MyLora, dbconnection
        if config.get('meshtastic', 'weatherbeacon') == 'True':
            weatherurl = config.get('meshtastic', 'weatherjson')
            if weatherurl != '':
                try:
                    url = urlopen(weatherurl)
                    wjson = json_load(url)
                    # Send it to mesh
                    telemetry_data = telemetry_pb2.Telemetry()
                    telemetry_data.time = int(time.time())
                    telemetry_data.environment_metrics.temperature = round(wjson['tempc'], 2)
                    telemetry_data.environment_metrics.relative_humidity = int(wjson['humidity'])
                    telemetry_data.environment_metrics.barometric_pressure = round(wjson['baromabshpa'], 2)
                    meshtastic_client.sendData(
                        telemetry_data,
                        destinationId = "^all",
                        portNum = portnums_pb2.PortNum.TELEMETRY_APP,
                        wantResponse = False,
                        channelIndex = 0,
                        hopLimit = 3
                    )
                    # Lets add it to DB
                    cursor = dbconnection.cursor()
                    cursor.execute("INSERT INTO environment_metrics (node_hex, node_id, temperature, relative_humidity, barometric_pressure) VALUES (?, ?, ?, ?, ?)", (MyLora, MyLoraID, round(wjson['tempc'], 2), int(wjson['humidity']), round(wjson['baromabshpa'], 2)))
                    cursor.close()
                    # And finaly send to chatbox so we know it send to!
                    text_raws = 'Node Telemetry'
                    text_raws += '\n' + (' ' * 11) + 'Temperature: ' + str(round(wjson['tempc'], 1)) + '°C'
                    text_raws += ' Humidity: ' + str(wjson['humidity']) + '%'
                    text_raws += ' Pressure: ' + str(round(wjson['baromabshpa'], 2)) + 'hPa'
                    insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + '] ' + unescape(f"{MyLora_SN} ({MyLora_LN})") + "\n", "#d1d1d1")
                    insert_colored_text(text_box2, (' ' * 11) + text_raws + '\n', "#00c983")

                except Exception as e:
                    logging.error(f"Error sending Weather: {e}")
                    print(f"Error sending Weather: {e}")

    def start_mesh():
        global overlay, root, ok2Send, database, dbconnection
        playsound('Data' + os.path.sep + 'Button.mp3')
        if overlay is not None:
            destroy_overlay()
        # Maybe add this to a connect button later via a overlay window and button as no window is shown duuring connect
        root.meshtastic_interface = connect_meshtastic()
        if root.meshtastic_interface is None:
            insert_colored_text(text_box1, "\n*** Failed to connect to meshtastic did you edit the config.ini    ***", "#2bd5ff")
            insert_colored_text(text_box1, "\n*** and wrote down the correct ip for tcp or commport for serial ? ***", "#2bd5ff")
            logging.error("Failed to connect to meshtastic")
        else:
            # Request Admmin Metadata
            ok2Send = 15
            req_meta_thread = threading.Thread(target=req_meta)
            req_meta_thread.start()
            # mmtext ='“Have you ever noticed that anybody driving slower than you is an idiot, and anyone going faster than you is a maniac?”'
            get_messages()
            # add_message(text_box3, MyLora, mmtext, int(time.time()), private=False, msend=True)
            root.after(1000, update_active_nodes)  # Schedule the next update in 30 seconds

    # The Node Configuration Frame still a work in progress, for now the LoRa settings seem to be working; more to come
    def create_config_frame():
        global config_frame, meshtastic_client, ourNode, MyLora_LN, MyLora_SN, NIenabled
        style = ttk.Style()
        style.theme_use('classic')
        style.configure("TLabel", background="#242424", foreground="#d1d1d1", font=('Fixedsys', 10))
        style.configure("TEntry", background="#242424", foreground="#000000", borderwidth=0, border=0, highlightthickness=0, font=('Fixedsys', 10))
        style.configure("TCheckbutton", background="#242424", foreground="#d1d1d1", borderwidth=0, border=0, highlightthickness=0, font=('Fixedsys', 10))
        style.map('TCheckbutton', indicatorcolor=[('selected', 'green'), ('pressed', 'gray')], background = [('disabled', '#242424'), ('pressed', '!focus', '#242424'), ('active', '#242424')], foreground = [('disabled', '#d1d1d1'), ('pressed', '#d1d1d1'), ('active', '#d1d1d1')])
        style.configure("TButton", borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", compound="center", foreground='#000000', font=('Fixedsys', 10))
        config.notebook = ttk.Notebook(config_frame, style='TNotebook')
        config.notebook.pack(expand=True, fill='both')

        frameUser = Frame(config.notebook, bg="#242424", borderwidth=0, highlightthickness=0, highlightcolor="#d1d1d1", highlightbackground="#d1d1d1", padx=2, pady=2)
        config.notebook.add(frameUser, text='User')
        nodeuser = meshtastic_client.getMyNodeInfo()
        config.shortName = StringVar(value=nodeuser['user']['shortName'])
        config.longName = StringVar(value=nodeuser['user']['longName'])
        ttk.Label(frameUser, text="Short Name:").pack(pady=(10, 0))
        ttk.Entry(frameUser, textvariable=config.shortName, width=7, justify='center').pack(pady=(0, 10))
        ttk.Label(frameUser, text="Long Name:").pack(pady=(10, 0))
        ttk.Entry(frameUser, textvariable=config.longName, width=32, justify='center').pack(pady=(0, 10))
        ttk.Button(frameUser, text="Save", command=lambda: save_user_config(config)).pack(pady=(40, 0))

        # framePos = Frame(config.notebook, bg="#242424", borderwidth=0, highlightthickness=0, highlightcolor="#d1d1d1", highlightbackground="#d1d1d1", padx=2, pady=2)
        # config.notebook.add(framePos, text='Position')
        # print(ourNode.localConfig.position)

        frameLora = Frame(config.notebook, bg="#242424", borderwidth=0, highlightthickness=0, highlightcolor="#d1d1d1", highlightbackground="#d1d1d1", padx=2, pady=2)
        config.notebook.add(frameLora, text='LoRa')
        config.hop_limit = IntVar(value=ourNode.localConfig.lora.hop_limit)
        config.override_duty_cycle = BooleanVar(value=ourNode.localConfig.lora.override_duty_cycle)
        config.sx126x_rx_boosted_gain = BooleanVar(value=ourNode.localConfig.lora.sx126x_rx_boosted_gain)
        config.tx_enabled = BooleanVar(value=ourNode.localConfig.lora.tx_enabled)
        config.tx_power = IntVar(value=ourNode.localConfig.lora.tx_power) # watt = 10 ** (dbm / 10) * 1e-3
        config.config_ok_to_mqtt = BooleanVar(value=ourNode.localConfig.lora.config_ok_to_mqtt)
        ttk.Label(frameLora, text="Hop Limit:").pack(pady=(10, 0))
        ttk.Entry(frameLora, textvariable=config.hop_limit).pack(pady=(0, 10))
        ttk.Checkbutton(frameLora, text="Override Duty Cycle", variable=config.override_duty_cycle).pack(pady=(10, 0))
        ttk.Checkbutton(frameLora, text="RX Boosted Gain", variable=config.sx126x_rx_boosted_gain).pack(pady=(10, 0))
        ttk.Checkbutton(frameLora, text="TX Enabled", variable=config.tx_enabled).pack(pady=(10, 0))
        ttk.Label(frameLora, text="TX Power:").pack(pady=(10, 0))
        ttk.Entry(frameLora, textvariable=config.tx_power).pack(pady=(0, 10))
        ttk.Checkbutton(frameLora, text="Ok to mqtt", variable=config.config_ok_to_mqtt).pack(pady=(10, 0))
        ttk.Button(frameLora, text="Save", command=lambda: save_lora_config(config)).pack(pady=(40, 0))

        frameMQTT = Frame(config.notebook, bg="#242424", borderwidth=0, highlightthickness=0, highlightcolor="#d1d1d1", highlightbackground="#d1d1d1", padx=2, pady=2)
        config.notebook.add(frameMQTT, text='MQTT')
        config.mqttenabled = BooleanVar(value=ourNode.moduleConfig.mqtt.enabled)
        config.mqttaddress = StringVar(value=ourNode.moduleConfig.mqtt.address)
        config.mqttusername = StringVar(value=ourNode.moduleConfig.mqtt.username)
        config.mqttpassword = StringVar(value=ourNode.moduleConfig.mqtt.password)
        config.mqtttopic = StringVar(value=ourNode.moduleConfig.mqtt.root)
        ttk.Checkbutton(frameMQTT, text="Enabled", variable=config.mqttenabled).pack(pady=(10, 0))
        ttk.Label(frameMQTT, text="Address:").pack(pady=(10, 0))
        ttk.Entry(frameMQTT, textvariable=config.mqttaddress).pack(pady=(0, 10))
        ttk.Label(frameMQTT, text="Username:").pack(pady=(10, 0))
        ttk.Entry(frameMQTT, textvariable=config.mqttusername).pack(pady=(0, 10))
        ttk.Label(frameMQTT, text="Password:").pack(pady=(10, 0))
        ttk.Entry(frameMQTT, textvariable=config.mqttpassword, show='*').pack(pady=(0, 10))
        ttk.Label(frameMQTT, text="Topic:").pack(pady=(10, 0))
        ttk.Entry(frameMQTT, textvariable=config.mqtttopic).pack(pady=(0, 10))
        ttk.Button(frameMQTT, text="Save", command=lambda: save_mqtt_config(config)).pack(pady=(40, 0))

        frameNeighbor = Frame(config.notebook, bg="#242424", borderwidth=0, highlightthickness=0, highlightcolor="#d1d1d1", highlightbackground="#d1d1d1", padx=2, pady=2)
        config.notebook.add(frameNeighbor, text='Neightbor Info')
        config.nbenabled = BooleanVar(value=ourNode.moduleConfig.neighbor_info.enabled)
        config.nbinterval = IntVar(value=ourNode.moduleConfig.neighbor_info.update_interval)
        ttk.Checkbutton(frameNeighbor, text="Hardware Enabled", variable=config.nbenabled).pack(pady=(10, 0))
        ttk.Checkbutton(frameNeighbor, text="via LoraLog Enabled", variable=NIenabled).pack(pady=(10, 0))
        ttk.Label(frameNeighbor, text="Update Interval:").pack(pady=(10, 0))
        ttk.Entry(frameNeighbor, textvariable=config.nbinterval).pack(pady=(0, 10))
        ttk.Button(frameNeighbor, text="Save", command=lambda: save_neighbor_config(config)).pack(pady=(40, 0))

    def save_mqtt_config(config):
        prev = deepcopy(ourNode.moduleConfig.mqtt)
        ourNode.moduleConfig.mqtt.enabled = config.mqttenabled.get()
        ourNode.moduleConfig.mqtt.address = config.mqttaddress.get()
        ourNode.moduleConfig.mqtt.username = config.mqttusername.get()
        ourNode.moduleConfig.mqtt.password = config.mqttpassword.get()
        ourNode.moduleConfig.mqtt.root = config.mqtttopic.get()
        if prev != ourNode.moduleConfig.mqtt:
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
            insert_colored_text(text_box2, " Sending mqtt config to node...\n", "#db6544")
            ourNode.writeConfig('mqtt')
        toggle_frames()

    def save_neighbor_config(config):
        prev = deepcopy(ourNode.moduleConfig.neighbor_info)
        ourNode.moduleConfig.neighbor_info.enabled = config.nbenabled.get()
        ourNode.moduleConfig.neighbor_info.update_interval = config.nbinterval.get()
        if prev != ourNode.moduleConfig.neighbor_info:
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
            insert_colored_text(text_box2, " Sending neighbor info config to node...\n", "#db6544")
            ourNode.writeConfig('neighbor_info')
        toggle_frames()

    def save_user_config(config):
        global config_frame, meshtastic_client, ourNode
        if config.longName.get() != '' and config.shortName.get() != '' and (config.longName.get() != MyLora_LN or config.shortName.get() != MyLora_SN):
            ourNode.setOwner(long_name=config.longName.get(), short_name=config.shortName.get()[:4], is_licensed=False)
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
            insert_colored_text(text_box2, " Sending user config to node...\n", "#db6544")
        toggle_frames()

    def save_lora_config(config):
        global config_frame, meshtastic_client, ourNode
        prev = deepcopy(ourNode.localConfig.lora)
        ourNode.localConfig.lora.hop_limit = config.hop_limit.get()
        ourNode.localConfig.lora.override_duty_cycle = config.override_duty_cycle.get()
        ourNode.localConfig.lora.sx126x_rx_boosted_gain = config.sx126x_rx_boosted_gain.get()
        ourNode.localConfig.lora.tx_enabled = config.tx_enabled.get()
        ourNode.localConfig.lora.tx_power = config.tx_power.get()
        ourNode.localConfig.lora.config_ok_to_mqtt = config.config_ok_to_mqtt.get()
        if prev != ourNode.localConfig.lora:
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
            insert_colored_text(text_box2, " Sending lora config to node, this will reset the node...\n", "#db6544")
            ourNode.writeConfig('lora')
        toggle_frames()

    def toggle_frames():
        if frame.winfo_viewable():
            frame.grid_remove()
            config_frame.grid()
            create_config_frame()
        else:
            for widget in config_frame.winfo_children():
                widget.destroy()
            config_frame.grid_remove()
            frame.grid()

    root = CTk()
    root.title("Meshtastic Lora Logger")
    root.resizable(True, True)
    root.iconbitmap('Data' + os.path.sep + 'mesh.ico')
    root.protocol('WM_DELETE_WINDOW', on_closing)
    root.tk_setPalette("#242424")

    if root.winfo_screenwidth() > 1920 and root.winfo_screenheight() > 1080:
        root.geometry(f'1600x990') 
    else:
        root.geometry(f'{str(root.winfo_screenwidth() - 70)}x{str(root.winfo_screenheight() - 70)}')

    overlay = None

    # Map Marker Images
    btn_img = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'ui_button.png'))

    my_msg = StringVar()  # For the messages to be sent.
    my_msg.set("")
    my_chat = StringVar()
    my_chat.set("")
    chat_input = None

    frame = Frame(root, borderwidth=0, highlightthickness=1, highlightcolor="#121212", highlightbackground="#121212")
    frame.grid(row=0, column=0, padx=2, pady=2, sticky='nsew')

    # Configure grid layout for the main frame
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_rowconfigure(1, weight=1)
    frame.grid_rowconfigure(2, weight=1)
    frame.grid_rowconfigure(3, weight=0)
    frame.grid_columnconfigure(0, weight=0)
    frame.grid_columnconfigure(1, weight=1)
    frame.grid_columnconfigure(2, weight=0)

    # Configure grid layout for the root window
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    # Left Top Window
    text_box1 = create_text(frame, 0, 0, 25, 90)
    insert_colored_text(text_box1, "    __                     __\n   / /  ___  _ __ __ _    / /  ___   __ _  __ _  ___ _ __\n  / /  / _ \| '__/ _` |  / /  / _ \ / _` |/ _` |/ _ \ '__|\n / /__| (_) | | | (_| | / /__| (_) | (_| | (_| |  __/ |\n \____/\___/|_|  \__,_| \____/\___/ \__, |\__, |\___|_|\n                                    |___/ |___/ ", "#2bd5ff")
    insert_colored_text(text_box1, "//\ESHT/\ST/C\n", "#00c983")
    insert_colored_text(text_box1, "\n Meshtastic Lora Logger v 1.4.0 (Dec 2024) By Jara Lowell\n", "#2bd5ff")
    insert_colored_text(text_box1, " Meshtastic Python CLI : v" + meshtastic.version.get_active_version() + '\n', "#2bd5ff")
    text_box1.insert("end", "─" * 60 + "\n", '#414141')
    text_box1.tag_configure('#414141', foreground='#414141')

    insert_colored_text(text_box1, "\n", "#2bd5ff")
    text_box1.configure(state="disabled")

    # Left Middle Window
    text_box2 = create_text(frame, 1, 0, 10, 90)
    text_box2.configure(state="disabled")

    # Left Bottom Window
    style = ttk.Style()
    style.theme_use('classic') # classic
    style.layout("TNotebook", [])
    style.configure("TNotebook", background="#242424", tabposition='nw', borderwidth=1, highlightcolor="#121212", highlightbackground="#121212")
    style.configure("TNotebook.Tab", background="#242424", foreground="#d1d1d1", borderwidth=1, highlightbackground="#121212", highlightcolor="#121212")
    # style.configure('TFrame', background="#242424", borderwidth=0, highlightthickness=0)
    style.map("TNotebook.Tab", background=[("selected", "#242424")], foreground=[("selected", "#2bd5ff")], font=[("selected", ('Fixedsys', 10))])

    tabControl = ttk.Notebook(frame, style='TNotebook')
    tabControl.grid(row=2, column=0, padx=2, pady=2, sticky='nsew')
    text_boxes = {}
    tabControl.bind("<<NotebookTabChanged>>", reset_tab_highlight)

    # Left Box Chat input
    padding_frame = LabelFrame(frame, background="#242424", padx=0, pady=4, bg='#242424', fg='#999999', font=('Fixedsys', 10), borderwidth=0, highlightthickness=0, labelanchor='n') # text=my_label.get()
    padding_frame.grid(row=4, column=0, rowspan=1, columnspan=1, padx=0, pady=0, sticky="nsew")
    padding_frame.grid_rowconfigure(1, weight=1)
    padding_frame.grid_columnconfigure(0, weight=1)

    text_box4 = Entry(padding_frame, textvariable=my_msg, width=68, bg='#242424', fg='#eeeeee', font=('Fixedsys', 10))
    text_box4.grid(row=4, column=0, padx=(1, 0))
    send_box4 = Button(padding_frame, image=btn_img, command=lambda: prechat_chan(), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Send Message", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
    send_box4.grid(row=4, column=1, padx=(0, 18))

    text_box4.bind("<Return>", prechat_chan)

    # Middle Map Window
    frame_right = Frame(frame, bg="#242424", borderwidth=0, highlightthickness=0, highlightcolor="#242424", highlightbackground="#242424", padx=2, pady=2)
    frame_right.grid(row=0, column=1, rowspan=5, columnspan=1, padx=0, pady=0, sticky='nsew')
    frame_right.grid_rowconfigure(0, weight=1)
    frame_right.grid_columnconfigure(0, weight=1)
    database_path = None
    if config.has_option('meshtastic', 'map_cache') and config.get('meshtastic', 'map_cache') == 'True':
        print("Using offline map cache")
        database_path = 'DataBase' + os.path.sep + 'MapTiles.db3'
    mapview = TkinterMapView(frame_right, padx=0, pady=0, bg_color='#000000', corner_radius=6, database_path=database_path)
    mapview.pack(fill='both', expand=True) # grid(row=0, column=0, sticky='nsew')
    mapview.set_position(48.860381, 2.338594)
    mapview.set_tile_server(config.get('meshtastic', 'map_tileserver'), max_zoom=20)
    mapview.set_zoom(1)

    is_mapfullwindow = False
    def toggle_map(event=None):
        global is_mapfullwindow
        if is_mapfullwindow:
            # Restore mapview to frame_right
            mapview.pack_forget()
            mapview.pack(fill='both', expand=True)
            frame_right.grid(row=0, column=1, rowspan=5, columnspan=1, padx=0, pady=0, sticky='nsew')
        else:
            # Make mapview full screen
            mapview.pack_forget()
            mapview.pack(fill='both', expand=True)
            mapview.master.grid(row=0, column=0, rowspan=5, columnspan=3, padx=0, pady=0, sticky='nsew')
        is_mapfullwindow = not is_mapfullwindow
    root.bind('<F6>', toggle_map)

    # Config Window
    config_frame = None
    config_frame = Frame(root, borderwidth=0, highlightthickness=1, highlightcolor="#121212", highlightbackground="#121212") # was root
    config_frame.grid(row=0, column=0, padx=2, pady=2, sticky='nsew')
    config_frame.grid_remove()  # Hide the config frame initially
    config_frame.grid_rowconfigure(0, weight=1)
    config_frame.grid_columnconfigure(0, weight=1)

    root.bind('<F2>', lambda event: toggle_frames())

    def show_loradb():
        global dbconnection
        cursor = dbconnection.cursor()
        tmpnodes = cursor.execute("SELECT * FROM node_info ORDER BY timerec DESC").fetchall()
        cursor.close()

        # Create a new window
        new_window = Toplevel(root)
        new_window.title("LoraDB Nodes")
        new_window.geometry("1440x810")
        new_window.configure(bg="#242424")
        new_window.iconbitmap('Data' + os.path.sep + 'mesh.ico')

        # style = ttk.Style()
        # style.theme_use('default')
        # style.configure(".", font=('Fixedsys', 10))
        # style.configure("Treeview", background="#242424", foreground="#eeeeee", fieldbackground="#3d3d3d")
        # style.configure("Treeview.Heading", background="#242424", foreground="#eeeeee")
        tree = ttk.Treeview(new_window, columns=("nodeID", "timenow", "ShortName", "LongName", "latitude", "longitude", "altitude", "macaddr", "hardware", "timefirst", "rightbarstats", "mmqtt", "snr", "hops", "uptime"), show='headings')
        tree.heading("nodeID", text="Node ID")
        tree.column("nodeID", minwidth=75, width=75, anchor='center')
        tree.heading("timenow", text="Last Seen")
        tree.column("timenow", minwidth=140, width=140, anchor='center')
        tree.heading("ShortName", text="Short")
        tree.column("ShortName", minwidth=50, width=50, anchor='center')
        tree.heading("LongName", text="Long Name")
        tree.column("LongName", minwidth=260, width=260)
        tree.heading("latitude", text="Latitude")
        tree.column("latitude", minwidth=90, width=90, anchor='center')
        tree.heading("longitude", text="Longitude")
        tree.column("longitude", minwidth=90, width=90, anchor='center')
        tree.heading("altitude", text="Alt")
        tree.column("altitude", minwidth=40, width=40, anchor='center')
        tree.heading("macaddr", text="MAC Address")
        tree.column("macaddr", minwidth=90, width=90, anchor='center')
        tree.heading("hardware", text="Hardware")
        tree.column("hardware", minwidth=120, width=120)
        tree.heading("timefirst", text="First Seen")
        tree.column("timefirst", minwidth=95, width=95, anchor='center')
        tree.heading("rightbarstats", text="Status")
        tree.column("rightbarstats", minwidth=90, width=90, anchor='center')
        tree.heading("mmqtt", text="MQTT")
        tree.column("mmqtt", minwidth=90, width=90, anchor='center')
        tree.heading("snr", text="SNR")
        tree.column("snr", minwidth=85, width=85, anchor='center')
        tree.heading("hops", text="Hops")
        tree.column("hops", minwidth=40, width=40, anchor='center')
        tree.heading("uptime", text="Uptime")
        tree.column("uptime", minwidth=90, width=90)
        tree.tag_configure('oddrow', background='#242424', foreground="#eeeeee")
        tree.tag_configure('evenrow', background='#3d3d3d', foreground="#eeeeee")
        data = [None] * 14
        i = False
        for entry in tmpnodes:
            if entry[1] == None:
                data[0] = datetime.fromtimestamp(int(entry[13])).strftime('%d %b %y %H:%M')
            else:
                data[0] = datetime.fromtimestamp(int(entry[1])).strftime('%d %b %y %H:%M')
            data[1] = unescape(entry[5])
            data[2] = unescape(entry[4])
            data[3] = "%.6f" % entry[9] if entry[9] != -8.0 else 'N/A'
            data[4] = "%.6f" % entry[10] if entry[10] != -8.0 else 'N/A'
            data[5] = "%.0f" % entry[11]
            data[6] = entry[2]
            data[7] = entry[6]
            data[8] = datetime.fromtimestamp(int(entry[13])).strftime('%d %b %y')
            data[9] = str(entry[18]) + '%, ' + str("%.2f" % entry[19]) + 'v'
            data[10] = 'True' if entry[15] else 'False'
            data[11] = str(entry[16]) + 'dB'
            data[12] = entry[23]
            data[13] = entry[14]
            if i:
                tree.insert("", "end", values=('!' + str(entry[3]), *data), tags=('oddrow',))
            else:
                tree.insert("", "end", values=('!' + str(entry[3]), *data), tags=('evenrow',))
            i = not i
        tree.pack(fill='both', expand=True)
        tmpnodes = None
    root.bind('<F5>', lambda event: show_loradb())

    # Right Status Window
    frame_middle = Frame(frame, bg="#242424", borderwidth=0, highlightthickness=0, padx=0, pady=0)
    frame_middle.grid(row=0, column=2, rowspan=5, columnspan=1, padx=0, pady=0, sticky='nsew')
    frame_middle.grid_rowconfigure(0, weight=1)
    frame_middle.grid_columnconfigure(0, weight=0)
    text_box_middle = create_text(frame_middle, 0, 0, 0, 21)

    # Start OverLay window
    overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#999999', highlightthickness=1)
    overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame
    info_label = Text(overlay, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), width=51, height=8)
    info_label.pack(pady=2)
    insert_colored_text(info_label, '\n\nConnect to Meshtastic\n', "#d2d2d2", center=True)
    insert_colored_text(info_label, '─' * 34 + '\n', "#414141", center=True)
    insert_colored_text(info_label, 'Please connect to your Meshtastic device\n', "#d2d2d2")
    insert_colored_text(info_label, 'and press the Connect button\n\n', "#d2d2d2")
    connto = config.get('meshtastic', 'interface')
    if connto == 'serial':
        insert_colored_text(info_label, 'Connect to Serial Port : ' + config.get('meshtastic', 'serial_port') + '\n', "#2bd5ff", center=True)
    else:
        insert_colored_text(info_label, 'Connect to IP : ' + config.get('meshtastic', 'host') + '\n', "#2bd5ff", center=True)
    button = Button(overlay, image=btn_img, command=start_mesh, borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Connect", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
    button.pack(padx=8)

    try:
        root.mainloop()
    except Exception as e:
        safedatabase()
        logging.error("Error : ", str(e))
        exit()
