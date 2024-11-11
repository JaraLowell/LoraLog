#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
from datetime import datetime
import sys
import asyncio
import gc
import psutil
import math
from unidecode import unidecode
from configparser import ConfigParser
import pickle
from html import unescape
from pygame import mixer
import threading
import copy
import sqlite3
# import yaml

# Tkinter imports
from PIL import Image, ImageTk
import tkinter as tk
import customtkinter
from tkinter import Frame, LabelFrame, ttk
from tkintermapview2 import TkinterMapView
import textwrap

# Meshtastic imports
import base64
from pubsub import pub
import meshtastic.remote_hardware
import meshtastic.version
import meshtastic.tcp_interface
import meshtastic.serial_interface
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
logging.basicConfig(filename='LoraLog.log', level=logging.ERROR, format='%(asctime)s : %(message)s', datefmt='%m-%d %H:%M', filemode='w')
logging.error("Startin Up")

telemetry_thread = None
position_thread  = None
trace_thread = None
MapMarkers = {}
ok2Send = 0
isConnect = False
chan2send = ''
MyLora = ''
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

def showLink(event):
    idx= event.widget.tag_names("current")[1]
    temp = type('temp', (object,), {})()
    temp.data = idx
    click_command(temp)

# Function to insert colored text
def insert_colored_text(text_widget, text, color, center=False, tag=None):
    global hr_img, MyLora
    parent_frame = str(text_widget.winfo_parent())
    if "frame5" not in parent_frame:
        text_widget.configure(state="normal")
        if color == '#d1d1d1': # and "frame3" not in parent_frame:
            text_widget.image_create("end", image=hr_img)

    if tag != None: # and tag != MyLora:
        text_widget.tag_configure(tag, foreground=color, underline=False)
        text_widget.insert(tk.END, text, (color, tag))
        text_widget.tag_bind(tag, "<Button-1>", showLink)
    else:
        text_widget.insert(tk.END, text, color)

    text_widget.tag_configure(color, foreground=color)

    if center:
        text_widget.tag_configure("center", justify='center')
        text_widget.tag_add("center", "1.0", "end")
    if "!frame5" not in parent_frame:
        text_widget.see(tk.END)
        text_widget.configure(state="disabled")

def add_message(nodeid, mtext, msgtime, private=False, msend='all', ackn=True, bulk=False):
    global dbconnection
    dbcursor = dbconnection.cursor()
    result = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ?", (nodeid,)).fetchone()
    dbcursor.close()
    if result is None:
        logging.error(f"Node {nodeid} not in database")
        return

    if str(private) in text_boxes:
        text_widget = text_boxes[str(private)]
    else:
        text_widget = text_boxes['Direct Message']

    label = result[5] + " (" + result[4] + ")"
    tcolor = "#00c983"
    if nodeid == MyLora: tcolor = "#2bd5ff"
    timestamp = datetime.fromtimestamp(msgtime).strftime("%Y-%m-%d %H:%M:%S")
    text_widget.image_create("end", image=hr_img)
    insert_colored_text(text_widget,'\n From ' + unescape(label),tcolor)
    if private:
        insert_colored_text(text_widget,' [' + private + ']', "#c9a500")
    ptext = unescape(mtext).strip()
    ptext = textwrap.fill(ptext, 87)
    tcolor = "#d2d2d2"
    if bulk == True:
        tcolor = "#a1a1a1"
    ptext = textwrap.indent(text=ptext, prefix='  ', predicate=lambda line: True)
    insert_colored_text(text_widget, '\n' + ptext + '\n', tcolor)
    insert_colored_text(text_widget,timestamp.rjust(89) + '\n', "#818181")
    if bulk == False:
        # We might have to html it so we dont get any ' and " in text that would break the the db
        chat_log.append({'nodeID': nodeid, 'time': msgtime, 'private': private, 'send': msend, 'ackn': ackn, 'seen': False, 'text': str(mtext.encode('ascii', 'xmlcharrefreplace'), 'ascii')})

    # url escape for save storage > str(text.encode('ascii', 'xmlcharrefreplace'), 'ascii')
    # and back to normal > unescape(text_from)
    # Do wee need to send ackn back to the sender after we seen the message ? 

def get_messages():
    sorted_data = chat_log[-10:] # for now retrieve only the last 10 messages
    for entry in sorted_data:
        add_message(entry['nodeID'], unescape(entry['text']), entry['time'], private=entry['private'], msend=entry['send'], ackn=entry['ackn'], bulk=True)

#------------------------------------------------------------- Movment Tracker --------------------------------------------------------------------------
chat_log        = [] # chat_log     = [{'nodeID': '1', 'time': 1698163200, 'private', True, 'send': 'nodeid or ch', 'ackn' : True, seen': False, 'text': 'Hello World!'}, ...]

# SQLite Database
if not os.path.exists('DataBase'):
    os.makedirs('DataBase')

database = 'DataBase' + os.path.sep + 'LoraLog.db3'
dbconnection = sqlite3.connect(database, timeout=250, check_same_thread=False)
dbcursor = dbconnection.cursor()
create_tmp = """CREATE TABLE IF NOT EXISTS node_info (
                            "node_id" integer NOT NULL PRIMARY KEY, 
                            "time" TIMESTAMP,
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

create_tmp = """CREATE TABLE IF NOT EXISTS naibor_info ("node_id" integer NOT NULL PRIMARY KEY, "hex_id" text, "time" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "neighbor_text" text );"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS device_metrics ("node_hex" text, "node_id" integer, "time" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "battery_level" integer DEFAULT 0, "voltage" real DEFAULT 0.0, "channel_utilization" real DEFAULT 0.0, "air_util_tx" real DEFAULT 0.0, "snr" real DEFAULT 0.0, "rssi" integer DEFAULT 0);"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS environment_metrics ("node_hex" text, "node_id" integer, "time" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "temperature" real DEFAULT 0.0, "relative_humidity" real DEFAULT 0.0, "barometric_pressure" real DEFAULT 0.0, "gas_resistance" real DEFAULT 0.0, iaq integer DEFAULT 0);"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS chat_log ("node_hex" text, "node_id" integer, "to_id" integer, "to_hex" text, "time" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "private" text, "send" text, "ackn" integer DEFAULT False, "seen" integer DEFAULT False, "text" text);"""
dbcursor.execute(create_tmp)

create_tmp = """CREATE TABLE IF NOT EXISTS movement_log ("node_hex" text, "node_id" integer, "time" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "from_latitude" real DEFAULT -8.0, "from_longitude" real DEFAULT -8.0, "from_altitude" integer DEFAULT 0, "to_latitude" real DEFAULT -8.0, "to_longitude" real DEFAULT -8.0, "to_altitude" integer DEFAULT 0);"""
dbcursor.execute(create_tmp)

dbcursor.execute("PRAGMA journal_mode=OFF")
dbcursor.connection.commit()
dbcursor.close()

# Load the databases
ChatPath = 'DataBase' + os.path.sep + 'ChatDB.pkl'
if os.path.exists(ChatPath):
    with open(ChatPath, 'rb') as f:
        chat_log = pickle.load(f)

def get_data_for_node(database, nodeID):
    global dbconnection
    cursor = dbconnection.cursor()
    query = f"SELECT *, strftime('%s', time) as time_epoch FROM {database} WHERE node_hex = ? ORDER BY time DESC"
    result = cursor.execute(query, (nodeID,)).fetchall()
    cursor.close()
    return result

def safedatabase():
    global ChatPath, chat_log
    with open(ChatPath, 'wb') as f:
        pickle.dump(chat_log, f)
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

#----------------------------------------------------------- Meshtastic Lora Con ------------------------------------------------------------------------    
meshtastic_client = None

mixer.init()
sound_cache = {}
def playsound(soundfile):
    if soundfile not in sound_cache:
        sound_cache[soundfile] = mixer.Sound(soundfile)
    sound_cache[soundfile].play()

def value_to_graph(value, min_value=-19, max_value=1, graph_length=12):
    value = max(min_value, min(max_value, value))
    position = int((value - min_value) / (max_value - min_value) * (graph_length - 1))
    position0 = int((0 - min_value) / (max_value - min_value) * (graph_length - 1))
    graph = ['─'] * graph_length
    graph[position0] = '┴'
    graph[position] = '╥'
    return '└' + ''.join(graph) + '┘'

def connect_meshtastic(force_connect=False):
    global meshtastic_client, MyLora, loop, isLora, isConnect, MyLora_Lat, MyLora_Lon, MyLora_SN, MyLora_LN, mylorachan, chan2send
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

    meshtastic_client = None
    # Initialize Meshtastic interface
    retry_limit = 3
    attempts = 1
    successful = False
    target_host = config.get('meshtastic', 'host')
    comport = config.get('meshtastic', 'serial_port')
    cnto = target_host
    if config.get('meshtastic', 'interface') != 'tcp':
        cnto = comport
    logging.debug("Connecting to meshtastic on " + cnto + "...")
    
    insert_colored_text(text_box1, " Connecting to meshtastic on " + cnto + "...\n", "#00c983")
    while not successful and attempts <= retry_limit:
        try:
            if config.get('meshtastic', 'interface') == 'tcp':
                meshtastic_client = meshtastic.tcp_interface.TCPInterface(hostname=target_host)
            else:
                meshtastic_client = meshtastic.serial_interface.SerialInterface(comport)
            successful = True
        except Exception as e:
            attempts += 1
            if attempts <= retry_limit:
                logging.error("Connect re-try: ", str(e))
                time.sleep(3)
            else:
                logging.error("Could not connect: s", str(e))
                isLora = False
                return None
    isConnect = True
    nodeInfo = meshtastic_client.getMyNodeInfo()
    logging.debug("Connected to " + nodeInfo['user']['id'] + " > "  + nodeInfo['user']['shortName'] + " / " + nodeInfo['user']['longName'] + " using a " + nodeInfo['user']['hwModel'])
    insert_colored_text(text_box1, " Connected to " + nodeInfo['user']['id'] + " > "  + nodeInfo['user']['shortName'] + " / " + nodeInfo['user']['longName'] + " using a " + nodeInfo['user']['hwModel'] + "\n", "#00c983")
    MyLora = (nodeInfo['user']['id'])[1:]
    MyLora_SN = nodeInfo['user']['shortName']
    MyLora_LN = nodeInfo['user']['longName']

    pub.subscribe(on_meshtastic_message, "meshtastic.receive", loop=asyncio.get_event_loop())
    pub.subscribe(on_meshtastic_connection, "meshtastic.connection.established")
    pub.subscribe(on_lost_meshtastic_connection,"meshtastic.connection.lost")

    print("MyLora: " + MyLora)
    root.wm_title("Meshtastic Lora Logger - " + unescape(MyLora_SN))

    # logLora((nodeInfo['user']['id'])[1:], ['NODEINFO_APP', nodeInfo['user']['shortName'], nodeInfo['user']['longName'], nodeInfo['user']["macaddr"],nodeInfo['user']['hwModel']])
    ## NEED AD MY SELF TO LOG 1ST TIME

    if 'position' in nodeInfo and 'latitude' in nodeInfo['position']:
        MyLora_Lat = round(nodeInfo['position']['latitude'],6)
        MyLora_Lon = round(nodeInfo['position']['longitude'],6)

    nodeInfo = meshtastic_client.getNode('^local')
    # Lets get the Local Node's channels
    lora_config = nodeInfo.localConfig.lora
    modem_preset_enum = lora_config.modem_preset
    modem_preset_string = config_pb2._CONFIG_LORACONFIG_MODEMPRESET.values_by_number[modem_preset_enum].name
    channels = nodeInfo.channels
    addtotab = False
    mylorachan = {}
    if channels:
        for channel in channels:
            psk_base64 = base64.b64encode(channel.settings.psk).decode('utf-8')
            
            if channel.settings.name == '':
                mylorachan[channel.index] = str(channel.index)
                addtotab = False
            else:
                mylorachan[channel.index] = channame(channel.settings.name)
                addtotab = True
            
            if channel.index == 0 and mylorachan[channel.index] == '0':
                mylorachan[channel.index] = channame(modem_preset_string)
                addtotab = True

            if channel.index == 0:
                insert_colored_text(text_box1, " Lora Chat Channel 0 = " + mylorachan[0] + " using Key " + psk_base64 + "\n", "#00c983")
                chan2send = mylorachan[0]

            # Need add to tabs for each channel
            if mylorachan[channel.index] != '' and addtotab:
                if mylorachan[channel.index] not in text_boxes: # Reconnected ?
                    tab = tk.Frame(tabControl, background="#121212", padx=0, pady=0, borderwidth=0) # ttk.Frame(tabControl, style='TFrame', padding=0, borderwidth=0)
                    tab.grid_rowconfigure(0, weight=1)
                    tab.grid_columnconfigure(0, weight=1)
                    tabControl.add(tab, text=mylorachan[channel.index], padding=(0, 0, 0, 0))
                    text_area = tk.Text(tab, wrap=tk.WORD, width=90, height=15, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), undo=False, borderwidth=1, highlightthickness=0)
                    text_area.grid(sticky='nsew')
                    text_area.configure(state="disabled")
                    text_boxes[mylorachan[channel.index]] = text_area

    if 'Direct Message' not in text_boxes:
        tab = tk.Frame(tabControl, background="#121212", padx=0, pady=0, borderwidth=0) # ttk.Frame(tabControl, style='TFrame', padding=0, borderwidth=0)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        tabControl.add(tab, text='Direct Message', padding=(0, 0, 0, 0))
        text_area = tk.Text(tab, wrap=tk.WORD, width=90, height=15, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), undo=False, borderwidth=1, highlightthickness=0)
        text_area.grid(sticky='nsew')
        text_area.configure(state="disabled")
        text_boxes['Direct Message'] = text_area

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
    selected_tab = event.widget.tab('current')['text']
    chan2send = selected_tab

def req_meta():
    global meshtastic_client, loop, ok2Send
    try:
        meshtastic_client.localNode.getMetadata()
    except Exception as e:
        logging.error("Error requesting metadata: %s", str(e))
    finally:
        print(f"Finished requesting metadata")
        ok2Send = 0

def on_lost_meshtastic_connection(interface):
    global root, loop, telemetry_thread, position_thread, trace_thread, isConnect
    safedatabase()
    isConnect = False
    logging.error("Lost connection to Meshtastic Node.")
    if telemetry_thread != None and telemetry_thread.is_alive():
        telemetry_thread.join()
    if  position_thread != None and position_thread.is_alive():
        position_thread.join()
    if  trace_thread != None and trace_thread.is_alive():
        trace_thread.join()

    pub.unsubscribe(on_meshtastic_message, "meshtastic.receive")
    pub.unsubscribe(on_meshtastic_connection, "meshtastic.connection.established")
    pub.unsubscribe(on_lost_meshtastic_connection, "meshtastic.connection.lost")

    insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
    insert_colored_text(text_box1, " Lost connection to node!", "#db6544")

    root.meshtastic_interface = None
    if isLora:
        logging.error("Trying to re-connect...")
        insert_colored_text(text_box1, ", Trying to re-connect...\n", "#db6544")
        time.sleep(3)
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
    in_hex = hex(nodeId)
    if len(in_hex)%2: in_hex = in_hex.replace("0x","0x0") # Need account for leading zero, wish hex removes if it has one
    return f"!{in_hex[2:]}"

def MapMarkerDelete(node_id):
    global MapMarkers
    if node_id in MapMarkers:
        # Mheard
        if MapMarkers[node_id][3] != None:
            MapMarkers[node_id][3].delete()
            MapMarkers[node_id][3] = None
        # Move Trail
        if MapMarkers[node_id][4] != None:
            MapMarkers[node_id][4].delete()
            MapMarkers[node_id][4] = None
        # Check Trail
        MapMarkers[node_id][5] = 0
        # Range Circle
        if len(MapMarkers[node_id]) == 8:
            if MapMarkers[node_id][7] != None:
                MapMarkers[node_id][7].delete()
                MapMarkers[node_id][7] = None
            MapMarkers[node_id].pop()

def on_meshtastic_message(packet, interface, loop=None):
    # print(yaml.dump(packet))
    global MyLora, MyLoraText1, MyLoraText2, MapMarkers, dbconnection
    if MyLora == '':
        print('*** MyLora is empty ***\n')
        return

    ischat = False
    viaMqtt = False
    hopStart = -1

    tnow = int(time.time())
    rectime = tnow

    if 'rxTime' in packet: rectime = packet['rxTime']
    text_from = ''
    if 'fromId' in packet and packet['fromId'] is not None:
        text_from = packet.get('fromId', '')[1:]
    if text_from == '':
        text_from = idToHex(packet["from"])[1:]
    fromraw = text_from

    with dbconnection:
        if "viaMqtt" in packet:
                viaMqtt = True

        if "hopStart" in packet:
            hopStart = packet.get('hopStart', -1)

        dbcursor = dbconnection.cursor()
        if text_from != '':
            result = dbcursor.execute("SELECT * FROM node_info WHERE node_id = ?", (packet["from"],)).fetchone()
            if result is None:
                print(f"on_message > Node !{text_from} not in DB")
                sn = str(fromraw[-4:])
                ln = "Meshtastic " + sn
                dbcursor.execute("INSERT INTO node_info (node_id, time, hex_id, ismqtt, last_snr, last_rssi, timefirst, short_name, long_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (packet["from"], tnow, text_from, viaMqtt, packet.get('rxSnr', 0), packet.get('rxRssi', 0), tnow, sn, ln))
                result = dbcursor.execute("SELECT * FROM node_info WHERE node_id = ?", (packet["from"],)).fetchone()
                insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                insert_colored_text(text_box1, " New Node Logged [!" + fromraw + "]\n", "#e8643f", tag=fromraw)
                playsound('Data' + os.path.sep + 'NewNode.mp3')
            else:
                # Added timefirst here for now to so we can sync up the 2 databases
                if result[5] == '': result[5] = str(fromraw[-4:])
                if result[4] == '': result[4] = "Meshtastic " + str(fromraw[-4:])
                text_from = unescape(result[5]) + " (" + unescape(result[4]) + ")"
                dbcursor.execute("UPDATE node_info SET time = ?, ismqtt = ?, last_snr = ?, last_rssi = ?, hopstart = ? WHERE node_id = ?", (tnow, viaMqtt, packet.get('rxSnr', 0), packet.get('rxRssi', 0), hopStart, packet["from"]))

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
                                MyLoraText1 = (' ChUtil').ljust(13) + str(round(device_metrics.get('channelUtilization', 0.00),2)).rjust(6) + '%\n' + (' AirUtilTX').ljust(13) + str(round(device_metrics.get('airUtilTx', 0.00),2)).rjust(6) + '%\n' + (' Power').ljust(13) + str(round(device_metrics.get('voltage', 0.00),2)).rjust(6) + 'v\n' + (' Battery').ljust(13) + str(device_metrics.get('batteryLevel', 0)).rjust(6) + '%\n'
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
                            if device_metrics.get('numTxRelay', 0) > 0:
                                text_raws += '\n' + (' ' * 11) + 'TxRelay: ' + str(localstats_metrics.get('numTxRelay', 0))
                            if device_metrics.get('numRxDupe', 0) > 0:
                                text_raws += ' RxDupe: ' + str(localstats_metrics.get('numRxDupe', 0))
                            if device_metrics.get('numTxRelayCanceled', 0) > 0:
                                text_raws += ' TxCanceled: ' + str(localstats_metrics.get('numTxRelayCanceled', 0))
                            text_raws += ' Nodes: ' + str(localstats_metrics.get('numOnlineNodes', 0)) + '/' + str(localstats_metrics.get('numTotalNodes', 0))
                            if MyLora == fromraw:
                                MyLoraText2 = (' PacketsTx').ljust(13) + str(localstats_metrics.get('numPacketsTx', 0)).rjust(7) + '\n' + (' PacketsRx').ljust(13) + str(localstats_metrics.get('numPacketsRx', 0)).rjust(7) + '\n' + (' Rx Bad').ljust(13) + str(localstats_metrics.get('numPacketsRxBad', 0)).rjust(7) + '\n' + (' Nodes').ljust(13) + (str(localstats_metrics.get('numOnlineNodes', 0)) + '/' + str(localstats_metrics.get('numTotalNodes', 0))).rjust(7) + '\n'
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
                        text_chns = 'Private'
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
                    extra = ''
                    if nodelat != -8.0 and nodelon != -8.0:
                        if (result[9] != nodelat or result[10] != nodelon or result[11] != nodealt) and result[9] != -8.0 and result[10] != -8.0:
                            # We moved add to movement log ?
                            dbcursor.execute("INSERT INTO movement_log (node_hex, node_id, time, from_latitude, from_longitude, from_altitude, to_latitude, to_longitude, to_altitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (fromraw, packet["from"], tnow, result[9], result[10], result[11], nodelat, nodelon, nodealt))
                            extra = '(Moved!) '
                            MapMarkerDelete(fromraw)
                        node_dist = calc_gc(nodelat, nodelon, MyLora_Lat, MyLora_Lon)
                        dbcursor.execute("UPDATE node_info SET latitude = ?, longitude = ?, altitude = ?, precision_bits = ?, last_sats = ?, distance = ? WHERE node_id = ?", (nodelat, nodelon, position.get('altitude', 0), position.get('precisionBits', 0), position.get('satsInView', 0), node_dist, packet["from"]))
                    text_msgs = 'Node Position '
                    text_msgs += 'latitude ' + str(round(nodelat,4)) + ' '
                    text_msgs += 'longitude ' + str(round(nodelon,4)) + ' '
                    text_msgs += 'altitude ' + str(nodealt) + ' meter\n' + (' ' * 11)
                    if nodelat != -8.0 and nodelon != -8.0:
                        if MyLora != fromraw and nodelat != -8.0 and nodelon != -8.0:
                            text_msgs += "Distance: ±" + str(node_dist) + "km "
                        if fromraw in MapMarkers and MapMarkers[fromraw][0] != None:
                            MapMarkers[fromraw][0].set_position(nodelat, nodelon)
                            MapMarkers[fromraw][0].set_text(result[5])
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
                    listmaps = []
                    if fromraw not in MapMarkers:
                        if result[9] != -8.0 and result[10] != -8.0:
                            MapMarkers[fromraw] = [None, True, tnow, None, None, 0, None]
                            MapMarkers[fromraw][0] = mapview.set_marker(result[9], result[10], text=unescape(result[5]), icon_index=3, text_color = '#2bd5ff', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                    if fromraw in MapMarkers:
                        if len(MapMarkers[fromraw]) > 3 and MapMarkers[fromraw][3] is not None:
                            MapMarkers[fromraw][3].delete()
                            MapMarkers[fromraw][3] = None
                    if "neighborinfo" in data and "neighbors" in data["neighborinfo"]:
                        text = data["neighborinfo"]["neighbors"]
                        tosql = ''
                        is_mqtt = True
                        if fromraw == MyLora:
                            is_mqtt = False
                        if fromraw in MapMarkers and MapMarkers[fromraw][3] is not None:
                            MapMarkers[fromraw][3].delete()
                            MapMarkers[fromraw][3] = None
                        for neighbor in text:
                            nodeid = idToHex(neighbor["nodeId"])[1:]
                            tmp = dbcursor.execute("SELECT * FROM node_info WHERE hex_id = ? AND latitude != -8 AND longitude != -8", (nodeid,)).fetchone()
                            nbNide = '!' + nodeid
                            if tmp is not None:
                                nbNide = unescape(tmp[5])
                                if nodeid not in MapMarkers:
                                    MapMarkers[nodeid] = [None, True, tnow, None, None, 0, None]
                                    MapMarkers[nodeid][0] = mapview.set_marker(tmp[9], tmp[10], text=unescape(nbNide), icon_index=3, text_color = '#2bd5ff', font = ('Fixedsys', 8), data=nodeid, command = click_command)
                                if fromraw in MapMarkers:
                                    listmaps = []
                                    pos = (result[9], result[10])
                                    listmaps.append(pos)
                                    pos = (tmp[9], tmp[10])
                                    listmaps.append(pos)
                                    MapMarkers[fromraw][3] = mapview.set_path(listmaps, color="#006642", width=2)
                                    if fromraw == MyLora: viaMqtt = False # We missed the initial packet so we need to log it
                                dbcursor.execute("UPDATE node_info SET time = ?, ismqtt = ? WHERE hex_id = ?", (tnow, is_mqtt, nodeid))
                                nodeid = tmp[5]
                            else:
                                nodeid = '!' + nodeid
                            text_raws += '\n' + (' ' * 11) + nodeid
                            if "snr" in neighbor:
                                text_raws += ' (' + str(neighbor["snr"]) + 'dB)'
                            tmp = neighbor.get('snr', 0)
                            tosql += '(' + nbNide
                            if tmp != 0: tosql += ',' + str(neighbor["snr"]) 
                            tosql += '),'
                        if tosql != '':
                            tosql = tosql[:-1]
                            dbcursor.execute("INSERT OR REPLACE INTO naibor_info (node_id, hex_id, time, neighbor_text) VALUES (?, ?, ?, ?)", (packet["from"], fromraw, tnow, tosql))
                    else:
                        text_raws += ' No Data'
                elif data["portnum"] == "RANGE_TEST_APP":
                    text_raws = 'Node RangeTest'
                    payload = data.get('payload', b'')
                    text_raws += '\n' + (' ' * 11) + 'Payload: ' + str(payload.decode())
                elif data["portnum"] == "TRACEROUTE_APP":
                    ## !!!!!!!!!!!!!!!! TOFDO !! Fix with SQLite3 !!!!!!!!!!!!!!!!!!!!!
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
                    # Unknown Packet
                    if 'portnum' in data:
                        text_raws = 'Node ' + (data["portnum"].split('_APP', 1)[0]).title()
                    else:
                        text_raws = 'Node Unknown Packet'

                nodesnr = 0
                if "rxSnr" in packet and packet['rxSnr'] is not None:
                    # we want rxRssi / rxSnr
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

                # Cleanup and get ready to print
                text_from = unescape(text_from)
                text_raws = unescape(text_raws)
                text_via = ''
                if viaMqtt == True:
                    text_via = ' via mqtt'
                if text_raws != '' and MyLora != fromraw:
                    insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + ' [!' + fromraw + ']' + text_via + "\n", "#d1d1d1", tag=fromraw)
                    if ischat == True:
                        add_message(fromraw, text_raws, tnow, private=text_chns)
                    if viaMqtt == True:
                        insert_colored_text(text_box1, (' ' * 11) + text_raws + '\n', "#c9a500")
                    else:
                        text_from = ''
                        if hopStart > 0:
                            text_from = '\n' + (' ' * 11) + str(hopStart) + ' hops '
                        if nodesnr != 0 and MyLora != fromraw:
                            if text_from == '':
                                text_from = '\n' + (' ' * 11)
                            text_from += f"{round(nodesnr,1)}dB {value_to_graph(nodesnr)}"

                        insert_colored_text(text_box1, (' ' * 11) + text_raws + text_from + '\n', "#00c983")
                elif text_raws != '' and MyLora == fromraw:
                    insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + text_via + "\n", "#d1d1d1")
                    insert_colored_text(text_box2, (' ' * 11) + text_raws + '\n', "#00c983")
                else:
                    insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + ' [!' + fromraw + ']' + text_via + "\n", "#d1d1d1", tag=fromraw)
            else:
                logging.debug("No fromId in packet")
                insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] No fromId in packet\n', "#c24400")
        else:
            insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + ']', "#d1d1d1")
            insert_colored_text(text_box1, ' Encrypted packet from ' + text_from + '\n', "#db6544", tag=fromraw)

            if fromraw not in MapMarkers:
                if result[9] != -8.0 and result[10] != -8.0:
                    MapMarkers[fromraw] = [None, False, tnow, None, None, 0, None]
                    MapMarkers[fromraw][0] = mapview.set_marker(result[9], result[10], text=unescape(result[5]), icon_index=4, text_color = '#aaaaaa', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                    MapMarkers[fromraw][0].text_color = '#aaaaaa'
                    MapMarkers[fromraw][6] = mapview.set_marker(result[9], result[10], icon_index=5, data=fromraw, command = click_command)
            elif fromraw in MapMarkers and MapMarkers[fromraw][0] == None:
                MapMarkers[fromraw][6] = mapview.set_marker(result[9], result[10], icon_index=5, data=fromraw, command = click_command)
        dbcursor.close()

def updatesnodes():
    global MyLora, MapMarkers, dbconnection, MyLora_Lat, MyLora_Lon, MyLora_SN
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
                cursor.execute("INSERT INTO node_info (node_id, hex_id, short_name, long_name, timefirst) VALUES (?, ?, ?, ?. ?)", (info["num"], nodeID,nodeID[-4:],'Meshtastic ' + nodeID[-4:], tnow))
                insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                insert_colored_text(text_box1, " New Node Logged [!" + nodeID + "]\n", "#e8643f", tag=nodeID)
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
                                cursor.execute("UPDATE node_info SET mac_id = ?, long_name = ?, short_name = ?, hw_model_id = ?, is_licensed = ? WHERE hex_id = ?", (tmp.get('macaddr', 'N/A'), lora_ln, lora_sn, tmp.get('hwModel', 'N/A'), tmp.get('isLicensed', False) ,nodeID))

                        if "position" in info:
                            tmp2 = info['position']
                            nodelat = round(tmp2.get('latitude', -8.0),6)
                            nodelon = round(tmp2.get('longitude', -8.0),6)
                            nodealt = tmp2.get('altitude', 0)
                            if nodelat != -8.0 and nodelon != -8.0:
                                cursor.execute("UPDATE node_info SET latitude = ?, longitude = ?, altitude = ?, hopstart = ? WHERE hex_id = ?", (nodelat, nodelon, nodealt, info.get('hopsAway', -1), nodeID))

                        if nodeID == MyLora:
                            if MyLora_Lat != -8.0 and MyLora_Lon != -8.0:
                                if MyLora not in MapMarkers:
                                    mapview.set_zoom(11)
                                    MapMarkers[MyLora] = [None, False, tnow, None, None, 0, None]
                                    MapMarkers[MyLora][0] = mapview.set_marker(MyLora_Lat, MyLora_Lon, text=unescape(MyLora_SN), icon_index=1, text_color = '#e67a7f', font = ('Fixedsys', 8), data=MyLora, command = click_command)
                                    MapMarkers[MyLora][0].text_color = '#e67a7f'
                                    mapview.set_position(MyLora_Lat, MyLora_Lon)
                            else:
                                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                                insert_colored_text(text_box2, " My Node has no position !!\n", "#e8643f")

                        if "viaMqtt" in info:
                            cursor.execute("UPDATE node_info SET ismqtt = ? WHERE hex_id = ?", (info.get('viaMqtt', False), nodeID))

        cursor.close()

#-------------------------------------------------------------- Side Functions ---------------------------------------------------------------------------

def ez_date(d):
    ts = d
    if ts > 31536000:
        temp = int(round(ts / 31536000, 0))
        val = f"{temp} year{'s' if temp > 1 else ''}"
    elif ts > 2419200:
        temp = int(round(ts / 2419200, 0))
        val = f"{temp} month{'s' if temp > 1 else ''}"
    elif ts > 604800:
        temp = int(round(ts / 604800, 0))
        val = f"{temp} week{'s' if temp > 1 else ''}"
    elif ts > 86400:
        temp = int(round(ts / 86400, 0))
        val = f"{temp} day{'s' if temp > 1 else ''}"
    elif ts > 3600:
        temp = int(round(ts / 3600, 0))
        val = f"{temp} hour{'s' if temp > 1 else ''}"
    elif ts > 60:
        temp = int(round(ts / 60, 0))
        val = f"{temp} minute{'s' if temp > 1 else ''}"
    else:
        temp = int(ts)
        val = "Just now"
    return val

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
    start_lat = math.radians(start_lat)
    start_long = math.radians(start_long)
    end_lat = math.radians(end_lat)
    end_long = math.radians(end_long)

    d_lat = math.fabs(start_lat - end_lat)
    d_long = math.fabs(start_long - end_long)

    EARTH_R = 6372.8

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
    global MyLora, dbconnection

    metrics = []
    result = get_data_for_node('device_metrics', node_id)
    if result:
        metrics = [{'time': int(row[9]), 'snr': row[7], 'rssi': row[8]} for row in result]

    if len(metrics) < 5:
        return None

    df = DataFrame({
        'time': [datetime.fromtimestamp(entry['time']) for entry in metrics],
        'snr': [entry['snr'] for entry in metrics],
        'rssi': [entry['rssi'] for entry in metrics],
    })
    resample_interval = len(df) // 60 or 5
    df_resampled = df.set_index('time').resample(f'{resample_interval}min').mean().dropna().reset_index()
    times_resampled = df_resampled['time'].tolist()
    snr_resampled = df_resampled['snr'].tolist()
    rssi_levels_resampled = df_resampled['rssi'].tolist()

    if all(value == 0 for value in snr_resampled):
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
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        elif total_hours <= 24:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
            ax.xaxis.set_major_locator(mdates.HourLocator())
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
    # canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    return canvas.get_tk_widget()

def plot_metrics_log(node_id, frame, width=512, height=162):
    global MyLora, dbconnection

    metrics = []
    result = get_data_for_node('device_metrics', node_id)
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
    resample_interval = len(df) // 60 or 5
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
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        elif total_hours <= 24:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
            ax.xaxis.set_major_locator(mdates.HourLocator())
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
    # canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    return canvas.get_tk_widget()

def plot_environment_log(node_id, frame , width=512, height=106):
    metrics = []
    result = get_data_for_node('environment_metrics', node_id)
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
    resample_interval = len(df) // 80 or 5
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
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    elif total_hours <= 24:
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        ax1.xaxis.set_major_locator(mdates.HourLocator())
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
    ax1.set_ylim(min(min_temp, min_humidity) - 10, max(max_temp, max_humidity) + 10)

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
    # canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    return canvas.get_tk_widget()

def plot_movment_curve(node_id, frame, width=512, height=102):
    positions = []
    result = get_data_for_node('movement_log', node_id)
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
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    elif total_hours <= 24:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        ax.xaxis.set_major_locator(mdates.HourLocator())
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
    # canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
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

    isLora = True

    def on_closing():
        global isLora, meshtastic_client, mapview, root, dbconnection
        isLora = False
        safedatabase()
        logging.debug('Saved Databases (Exit)')
        if meshtastic_client is not None:
            meshtastic_client.close()
        if dbconnection is not None:
            try:
                dbconnection.execute("VACUUM")
                dbconnection.close()
            except sqlite3.Error as e:
                logging.error("Error closing database connection: ", str(e))
        mapview.destroy()
        logging.debug("Exit :: Closed Program, Bye!")
        root.quit()
        sys.exit()

    # Initialize the main window
    def create_text(frame, row, column, frheight, frwidth):
        # Create a frame with a black background to simulate padding color
        padding_frame = tk.Frame(frame, background="#121212", padx=2, pady=2)
        padding_frame.grid(row=row, column=column, rowspan=1, columnspan=1, padx=0, pady=0, sticky='nsew')
        
        # Configure grid layout for the padding frame
        padding_frame.grid_rowconfigure(0, weight=1)
        padding_frame.grid_columnconfigure(0, weight=1)
        
        # Create a text widget inside the frame
        text_area = tk.Text(padding_frame, wrap=tk.WORD, width=frwidth, height=frheight, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), undo=False)
        text_area.grid(row=0, column=0, sticky='nsew')
        return text_area

    def send(event=None):
        text2send = my_msg.get().rstrip()
        if len(text2send.encode('utf-8')) > 220:
            # neeed check max, some seem to say 237 ?
            insert_colored_text(text_box2, "Text message to long, keep it under 220 bytes\n", "#d1d1d1")
        elif text2send != '':
            meshtastic_client.sendText(text2send)
            text_from = MyLora_SN + " (" + MyLora_Lon + ")"
            add_message(MyLora, text2send, int(time.time()), msend=str(mylorachan[0].encode('ascii', 'xmlcharrefreplace'), 'ascii'))
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
            insert_colored_text(text_box2, (' ' * 11) + '[to ' + str(mylorachan[0]) +'] ' + text2send + '\n', "#00c983")
            my_msg.set("")
            playsound('Data' + os.path.sep + 'NewChat.mp3')

    def send_position(nodeid):
        global meshtastic_client, loop, ok2Send
        print(f"Requesting Position Data from {nodeid}")
        try:
            meshtastic_client.sendPosition(destinationId=nodeid, wantResponse=True, channelIndex=0)
        except Exception as e:
            print(f"Error sending Position: {e}")
        finally:
            print(f"Finished sending Position")
            ok2Send = 0

    def send_telemetry(nodeid):
        global meshtastic_client, loop, ok2Send
        print(f"Requesting Telemetry Data from {nodeid}")
        try:
            meshtastic_client.sendTelemetry(destinationId=nodeid, wantResponse=True, channelIndex=0)
        except Exception as e:
            print(f"Error sending Telemetry: {e}")
        finally:
            print(f"Finished sending Telemetry")
            ok2Send = 0

    def send_trace(nodeid):
        global meshtastic_client, loop, ok2Send
        print(f"Requesting Traceroute Data from {nodeid}")
        try:
            meshtastic_client.sendTraceRoute(dest=nodeid, hopLimit=7, channelIndex=0)
        except Exception as e:
            print(f"Error sending Traceroute: {e}")
        finally:
            print(f"Finished sending Traceroute")
            ok2Send = 0

    def close_overlay():
        global overlay
        playsound('Data' + os.path.sep + 'Button.mp3')
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

    def chatbox(nodeid, nodesn, nodeln):
        global MyLora, overlay, my_chat, chat_input
        playsound('Data' + os.path.sep + 'Button.mp3')
        if overlay is not None:
            destroy_overlay()
        if has_open_figures():
            logging.debug("No fromId in packet")

        overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#999999', highlightthickness=1)
        overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame
        chat_label = tk.Label(overlay, text=unescape(nodesn) + '\n' + unescape(nodeln), font=('Fixedsys', 12), bg='#242424', fg='#2bd5ff')
        chat_label.pack(side="top", fill="x", pady=3)
        chat_box = tk.Text(overlay, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), width=64, height=12)
        chat_box.pack_propagate(False)  # Prevent resizing based on the content
        chat_box.pack(side="top", fill="both", expand=True, padx=10, pady=3)

        # And here we need use and utalize chat_log
        # chat_log     = [{'nodeID': '1', 'time': 1698163200, 'private', True, 'sendto': True, 'ackn' : True, 'text': 'Hello World!'}, ...]
        # node_text = [entry for entry in chat_log if entry['nodeID'] == nodeID]
        node_text = [entry for entry in chat_log if (entry['nodeID'] == nodeid or entry['send'] == nodeid) and entry['private'] == True]
        node_text.sort(key=lambda x: x['time']) # might be , reverse=True
        # Insert sorted entries into chat_box
        for entry in node_text:
            # datetime.fromtimestamp(msgtime).strftime("%Y-%m-%d %H:%M:%S")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry['time']))
            insert_colored_text(chat_box, f"[{timestamp}] {unescape(nodesn)}\n", "#d1d1d1")
            insert_colored_text(chat_box, f" {unescape(entry['text'])}\n", "#818181")

        insert_colored_text(chat_box, "\n  Not yet working, Working on it !!\n", "#dddddd")

        chat_input = tk.Entry(overlay, textvariable=my_chat, width=50, bg='#242424', fg='#eeeeee', font=('Fixedsys', 10))
        chat_input.pack(side="top", fill="x", padx=10, pady=3)
        button_frame = Frame(overlay, bg='#242424')
        button_frame.pack(pady=12)
        send_button = tk.Button(button_frame, image=btn_img, command=lambda: send_message(chat_input.get(), nodeid), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Send Message", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        send_button.pack(side=tk.LEFT, padx=2)
        clear_button = tk.Button(button_frame, image=btn_img, command=lambda: print("Button Clear clicked"), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Clear Chat", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        clear_button.pack(side=tk.LEFT, padx=2)
        close_button = tk.Button(button_frame, image=btn_img, command=lambda: close_overlay(), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Close Chat", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        close_button.pack(side=tk.LEFT, padx=2)

    def send_message(message, nodeid):
        global my_chat
        playsound('Data' + os.path.sep + 'Button.mp3')
        my_chat.set("")
        # !! Under Construction !! 
        print("Sending "+ nodeid + " message: " + message)

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

        overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#999999', highlightthickness=1, takefocus=True)
        overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame

        info_label = tk.Text(overlay, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), width=64, height=13)
        info_label.grid(row=0, column=0, columnspan=2, padx=1, pady=1, sticky='nsew')

        insert_colored_text(info_label, "⬢ ", "#" + marker.data[-6:],  center=True)
        if result[4] != '':
            text_loc = unescape(result[5]) + '\n' + unescape(result[4]) + '\n'
        else:
            text_loc = unescape(result[5]) + '\n'
        insert_colored_text(info_label, text_loc, "#2bd5ff",  center=True)
        if result[9] != -8.0 and result[10] != -8.0:
            text_loc = '\n  Position : ' + str(result[9]) + ' / ' + str(result[10]) + ' (' + LatLon2qth(result[9],result[10])[:-2] + ')'
            text_loc += ' Altitude ' + str(result[11]) + 'm\n'
        else:
            text_loc = '\n  Position : Unknown\n'
        insert_colored_text(info_label, text_loc, "#d1d1d1",  center=True)
        text_loc = '\n  HW Model : ' + str(result[6]) + '\n'
        text_loc += '  Hex ID   : ' + '!' + str(result[3]).ljust(18)
        text_loc += 'MAC Addr  : ' + str(result[2]) + '\n'
        # Add uptime back
        if result[14] and int(result[14]) != 0:
            text_loc += '  ' + uptimmehuman(int(result[14]), int(result[1])) + '\n'
        text_loc += '  Last SNR : ' + str(result[16]).ljust(19)
        text_loc += 'Last Seen : ' + ez_date(int(time.time()) - result[1]) + '\n'
        text_loc += '  Power    : ' + str(result[19]).ljust(19)
        text_loc += 'First Seen: ' + datetime.fromtimestamp(result[13]).strftime('%b %#d \'%y') + '\n'
        if result[24] != 0.0:
            text_loc += '  Distance : ' + (str(result[24]) + 'km').ljust(19)
        else:
            text_loc += '  Distance : ' + ('Unknown').ljust(19)

        if result[23] > 0:
            text_loc += 'HopsAway  : ' + str(result[23])

        dbcursor = dbconnection.cursor()
        yada = dbcursor.execute("SELECT * FROM naibor_info WHERE hex_id = ?", (marker.data,)).fetchone()
        dbcursor.close()
        if yada is not None:
            text_loc += '\n  Naibors  :' + yada[3].replace(')', 'dB').replace('(', ' ')

        insert_colored_text(info_label, text_loc, "#d1d1d1")

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
            button1 = tk.Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqInfo', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Request Info", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button1.grid(row=0, column=0, padx=(0, 1), sticky='e')
            button2 = tk.Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqPos', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Request Pos", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button2.grid(row=0, column=1, padx=(0, 0), sticky='ew')
            button3 = tk.Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqTrace', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Trace Node", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button3.grid(row=0, column=2, padx=(1, 0), sticky='w')

        button_frame2 = Frame(overlay, bg='#242424')
        button_frame2.grid(row=3, column=0, columnspan=2, pady=2, sticky='nsew')

        button4 = tk.Button(button_frame2, image=btn_img, command=lambda: mapview.set_position(result[9], result[10]) if result[9] != -8.0 and result[10] != -8.0 else None, borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Zoom", compound="center", fg='#d1d1d1' if result[9] != -8.0 and result[10] != -8.0 else '#616161', font=('Fixedsys', 10))
        button4.grid(row=0, column=0, padx=(0, 1), sticky='e')
        button5 = tk.Button(button_frame2, image=btn_img, command=lambda: close_overlay(), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Close", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        button5.grid(row=0, column=1, padx=(0, 0), sticky='ew')
        button6 = tk.Button(button_frame2, image=btn_img, command=lambda: chatbox(result[3], result[5], result[4]), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Chat", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
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
                            MapMarkers[node_id][0].delete()
                            MapMarkers[node_id][0] = None
                            MapMarkers[node_id][0] = mapview.set_marker(lat, lon, text=nodesn, icon_index=icon, text_color = color, font = ('Fixedsys', 8), data=node_id, command = click_command)
                            MapMarkers[node_id][0].text_color = color
                    else:
                        MapMarkers[node_id][0].delete()
                        MapMarkers[node_id][0] = None
                        MapMarkers[node_id][0] = mapview.set_marker(lat, lon, text=nodesn, icon_index=icon, text_color = color, font = ('Fixedsys', 8), data=node_id, command = click_command)
                        MapMarkers[node_id][0].text_color = color
                else:
                    MapMarkers[node_id][0] = mapview.set_marker(lat, lon, text=nodesn, icon_index=icon, text_color = color, font = ('Fixedsys', 8), data=node_id, command = click_command)
                    MapMarkers[node_id][0].text_color = color
            else:
                if MapMarkers[node_id][0] != None:
                    MapMarkers[node_id][0].delete()
                    MapMarkers[node_id][0] = None
                if MapMarkers[node_id][3] != None:
                    MapMarkers[node_id][3].delete()
                    MapMarkers[node_id][3] = None
            MapMarkers[node_id][1] = tmp
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
        global MyLora, MyLoraText1, MyLoraText2, tlast, MapMarkers, ok2Send, peekmem, dbconnection, MyLora_Lat, MyLora_Lon
        start = time.perf_counter()
        tnow = int(time.time())

        text_box_middle.configure(state="normal")
        current_view = text_box_middle.yview()
        
        # Unbind all tags from text_box_middle
        for tag in text_box_middle.tag_names():
            text_box_middle.tag_unbind(tag, "<Button-1>")
        text_box_middle.delete("1.0", tk.END)

        insert_colored_text(text_box_middle, "\n " + MyLora_SN + "\n", "#e67a7f", tag=MyLora)
        if MyLoraText1:
            insert_colored_text(text_box_middle, MyLoraText1, "#c1c1c1")
        if MyLoraText2:
            insert_colored_text(text_box_middle, MyLoraText2, "#c1c1c1")

        try:
            cursor = dbconnection.cursor()
            result = cursor.execute(
                "SELECT * FROM node_info WHERE (? - time) <= ? ORDER BY time DESC",
                (tnow, map_oldnode)
            ).fetchall()
            cursor.close()
            
            drawoldnodes = mapview.draw_oldnodes
            nodes_to_delete = []
            nodes_to_update = []

            for row in result:
                node_id = row[3]
                node_time = row[1]
                node_name = unescape(row[5]).strip()
                timeoffset = tnow - node_time

                if timeoffset >= map_oldnode and node_id != MyLora:
                    if node_id in MapMarkers:
                        nodes_to_delete.append(node_id)
                elif timeoffset < map_delete and node_id != MyLora:
                    nodes_to_update.append((node_id, node_time, node_name, row))

            # Batch delete nodes
            for node_id in nodes_to_delete:
                MapMarkerDelete(node_id)
                MapMarkers[node_id][0].delete()
                MapMarkers[node_id][0] = None
                del MapMarkers[node_id]

            # Batch update nodes
            for node_id, node_time, node_name, row in nodes_to_update:
                node_wtime = ez_date(tnow - node_time).rjust(10)
                node_dist = ' '
                if row[24] != 0.0:
                    node_dist = f"{row[24]}km"
                insert_colored_text(text_box_middle, ('─' * 14) + '\n', "#3d3d3d")
                if row[15]:
                    insert_colored_text(text_box_middle, f" {node_name.ljust(9)}", "#c9a500", tag=str(node_id))
                    insert_colored_text(text_box_middle, f"{node_wtime}\n", "#9d9d9d")
                    insert_colored_text(text_box_middle, f" {node_dist.ljust(9)}\n", "#9d9d9d")
                    checknode(node_id, 3, '#2bd5ff', row[9], row[10], node_name, drawoldnodes)
                else:
                    node_sig = (' ' + str(row[16]) + 'dB').rjust(10)
                    insert_colored_text(text_box_middle, f" {node_name.ljust(9)}", "#00c983", tag=str(node_id))
                    insert_colored_text(text_box_middle, f"{node_wtime}\n", "#9d9d9d")
                    insert_colored_text(text_box_middle, f" {node_dist.ljust(9)}{node_sig}\n", "#9d9d9d")
                    checknode(node_id, 2, '#2bd5ff', row[9], row[10], node_name, drawoldnodes)
        except Exception as e:
            logging.error(f"Error updating active nodes: {e}")

        # Just some stats for checks
        insert_colored_text(text_box_middle, '\n' + ('─' * 14), "#3d3d3d")
        time1 = (time.perf_counter() - start) * 1000
        insert_colored_text(text_box_middle, f'\n Update  : {time1:.2f}ms', "#9d9d9d")
        tmp2 = int(psutil.Process(os.getpid()).memory_info().rss)
        time1 = round(tmp2 / 1024 / 1024 * 100,2) / 100
        if peekmem < time1: peekmem = time1
        insert_colored_text(text_box_middle, f"\n Mem     : {time1:.1f}MB\n", "#9d9d9d")
        insert_colored_text(text_box_middle, f" Mem Max : {peekmem:.1f}MB\n\n", "#9d9d9d")

        insert_colored_text(text_box_middle, " F6 Map Extend Mode\n", "#9d9d9d")

        text_box_middle.yview_moveto(current_view[0])
        text_box_middle.configure(state="disabled")

        root.after(1000, update_paths_nodes)
    ### end

    def update_paths_nodes():
        global MyLora, MapMarkers, tlast, pingcount, isConnect, overlay, dbconnection, mapview, map_oldnode, metrics_age, map_delete, max_lines, map_trail_age
        tnow = int(time.time())
        try:
            cursor = dbconnection.cursor()
            result = cursor.execute("SELECT * FROM node_info  WHERE (? - time) <= ? ORDER BY time DESC", (tnow, map_oldnode)).fetchall()
            cursor.close()
            for row in result:
                node_id = row[3]
                node_time = row[1]
                if node_id in MapMarkers:
                    # Lets remove mheard if time bigger then 15 minutes
                    if tnow - node_time >= 900 and MapMarkers[node_id][3] != None:
                        MapMarkers[node_id][3].delete()
                        MapMarkers[node_id][3] = None

                    if MapMarkers[node_id][6] != None and (tnow - node_time) >= 3:
                        MapMarkers[node_id][6].delete()
                        MapMarkers[node_id][6] = None

                    if MapMarkers[node_id][4] != None and MapMarkers[node_id][5] <= 0:
                        MapMarkers[node_id][4].delete()
                        MapMarkers[node_id][4] = None

                    if mapview.draw_trail:
                        positions = get_data_for_node('movement_log', node_id)
                        if len(positions) > 1 and tnow - node_time <= map_oldnode:
                            if MapMarkers[node_id][5] <= 0:
                                drawline = []
                                for position in positions:
                                    pos = (position[6], position[7])
                                    drawline.append(pos)
                                MapMarkers[node_id][4] = mapview.set_path(drawline, color="#751919", width=2)
                                MapMarkers[node_id][5] = 30
                            else:
                                MapMarkers[node_id][5] -= 1
                        # Lets delete some old mars and paths if we to old...
                        if tnow - node_time > map_delete and MapMarkers[node_id][3] != None:
                            MapMarkers[node_id][3].delete()
                            MapMarkers[node_id][3] = None
                        if tnow - node_time > map_oldnode and MapMarkers[node_id][4] != None:
                            MapMarkers[node_id][4].delete()
                            MapMarkers[node_id][4] = None
                            MapMarkers[node_id][5] = 0
        except Exception as e:
            logging.error(f"Error updating paths and nodes: {e}")   

        if isConnect:
            pingcount += 1
            if pingcount > 5:
                pingcount = 0
                try:
                    meshtastic_client.sendHeartbeat()
                except Exception as e:
                    logging.error(f"Error sending Ping: {e}")
                    print(f"Error sending Ping: {e}")

        if tnow > tlast + 900:
            tlast = tnow
            updatesnodes()

            # Clear up text_box1 so it max has 1000 lines
            line_count = text_box1.count("1.0", "end-1c", "lines")[0]
            if line_count > max_lines:
                delete_count = (line_count - max_lines) + 10
                text_box1.configure(state="normal")
                text_box1.delete("1.0", f"{delete_count}.0")
                text_box1.configure(state="disabled")
                print(f"Clearing Frame 1 ({delete_count} lines)")

            # Clear up text_box2 so it max has 1000 lines
            line_count = text_box2.count("1.0", "end-1c", "lines")[0]
            if line_count > max_lines:
                delete_count = (line_count - max_lines) + 10
                text_box2.configure(state="normal")
                text_box2.delete("1.0", f"{delete_count}.0")
                text_box2.configure(state="disabled")
                print(f"Clearing Frame 2 ({delete_count} lines)")

            if overlay is None:
                if has_open_figures():
                    logging.debug("Closing open figures failed?")

            # Delete entries older than metrics_age from each table and then Optimize/Vacuum the database
            with dbconnection:
                tables = ['naibor_info', 'device_metrics', 'environment_metrics', 'chat_log']

                cursor = dbconnection.cursor()
                for table in tables:
                    query = f"DELETE FROM {table} WHERE time <= date('now','-{metrics_age} day')"
                    cursor.execute(query)

                # Lets clean up movement_log a bit
                query = f"DELETE FROM movement_log WHERE time <= date('now', '-{map_trail_age} hour')"
                cursor.execute(query)
                cursor.close()

            safedatabase()
            gc.collect()

        root.after(1000, update_active_nodes)

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
            '''
            with dbconnection:
                dbcursor = dbconnection.cursor()
                result = dbcursor.execute("SELECT * FROM node_info ORDER BY time DESC").fetchall()
                if result:
                    for row in result:
                        if row[9] != -8.0 and row[10] != -8.0:
                            node_dist = calc_gc(row[9], row[10], MyLora_Lat, MyLora_Lon)
                            dbcursor.execute("UPDATE node_info SET distance = ? WHERE node_id = ?", (node_dist, row[0]))
                            print(f"Updated distance for {row[3]} to {node_dist}")
                dbcursor.close()
            '''
            ok2Send = 15
            req_meta_thread = threading.Thread(target=req_meta)
            req_meta_thread.start()
            # mmtext ='“Have you ever noticed that anybody driving slower than you is an idiot, and anyone going faster than you is a maniac?”'
            get_messages()
            # add_message(text_box3, MyLora, mmtext, int(time.time()), private=False, msend=True)
            root.after(1000, update_active_nodes)  # Schedule the next update in 30 seconds

    root = customtkinter.CTk()
    root.title("Meshtastic Lora Logger")
    root.geometry(f'1440x810')
    root.resizable(True, True)
    root.iconbitmap('Data' + os.path.sep + 'mesh.ico')
    root.protocol('WM_DELETE_WINDOW', on_closing)
    root.tk_setPalette("#242424")
    overlay = None

    # Map Marker Images
    btn_img = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'ui_button.png'))
    hr_img = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'hr.png'))

    my_msg = tk.StringVar()  # For the messages to be sent.
    my_msg.set("")
    # my_label = tk.StringVar()
    # my_label.set("Send a message to channel")
    my_chat = tk.StringVar()
    my_chat.set("")
    chat_input = None

    frame = tk.Frame(root, borderwidth=0, highlightthickness=1, highlightcolor="#121212", highlightbackground="#121212")
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
    insert_colored_text(text_box1,  "    __                     __\n   / /  ___  _ __ __ _    / /  ___   __ _  __ _  ___ _ __\n  / /  / _ \| '__/ _` |  / /  / _ \ / _` |/ _` |/ _ \ '__|\n / /__| (_) | | | (_| | / /__| (_) | (_| | (_| |  __/ |\n \____/\___/|_|  \__,_| \____/\___/ \__, |\__, |\___|_|\n                                    |___/ |___/ ", "#2bd5ff")
    insert_colored_text(text_box1, "//\ESHT/\ST/C\n", "#00c983")
    insert_colored_text(text_box1, "\n Meshtastic Lora Logger v 1.37.b2 By Jara Lowell\n", "#2bd5ff")
    insert_colored_text(text_box1, " Meshtastic Lybrary : v" + meshtastic.version.get_active_version() + '\n', "#2bd5ff")
    text_box1.image_create("end", image=hr_img)
    insert_colored_text(text_box1, "\n", "#2bd5ff")
    text_box1.configure(state="disabled")

    # Left Middle Window
    text_box2 = create_text(frame, 1, 0, 10, 90)
    text_box2.configure(state="disabled")

    # Left Bottom Window
    style = ttk.Style()
    style.theme_use('classic') # classic
    style.layout("TNotebook", [])
    style.configure("TNotebook", background="#242424", tabposition=tk.NW, borderwidth=1, highlightcolor="#121212", highlightbackground="#121212")
    style.configure("TNotebook.Tab", background="#242424", foreground="#d1d1d1", borderwidth=1, highlightbackground="#121212", highlightcolor="#121212")
    # style.configure('TFrame', background="#242424", borderwidth=0, highlightthickness=0)
    style.map("TNotebook.Tab", background=[("selected", "#242424")], foreground=[("selected", "#2bd5ff")], font=[("selected", ('Fixedsys', 10))])

    tabControl = ttk.Notebook(frame, style='TNotebook')
    tabControl.grid(row=2, column=0, padx=2, pady=2, sticky='nsew')
    text_boxes = {}
    tabControl.bind("<<NotebookTabChanged>>", reset_tab_highlight)

    # Left Box Chat input
    padding_frame = tk.LabelFrame(frame, background="#242424", padx=0, pady=4, bg='#242424', fg='#999999', font=('Fixedsys', 10), borderwidth=0, highlightthickness=0, labelanchor='n') # text=my_label.get()
    padding_frame.grid(row=4, column=0, rowspan=1, columnspan=1, padx=0, pady=0, sticky="nsew")
    padding_frame.grid_rowconfigure(1, weight=1)
    padding_frame.grid_columnconfigure(0, weight=1)

    text_box4 = tk.Entry(padding_frame, textvariable=my_msg, width=68, bg='#242424', fg='#eeeeee', font=('Fixedsys', 10))
    text_box4.grid(row=4, column=0, padx=(1, 0))
    send_box4 = tk.Button(padding_frame, image=btn_img, command=lambda: send(), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Send Message", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
    send_box4.grid(row=4, column=1, padx=(0, 18))

    # Middle Map Window
    frame_right = tk.Frame(frame, bg="#242424", borderwidth=0, highlightthickness=0, highlightcolor="#242424", highlightbackground="#242424", padx=2, pady=2)
    frame_right.grid(row=0, column=1, rowspan=5, columnspan=1, padx=0, pady=0, sticky='nsew')
    frame_right.grid_rowconfigure(0, weight=1)
    frame_right.grid_columnconfigure(0, weight=1)
    database_path = None
    if config.has_option('meshtastic', 'map_cache') and config.get('meshtastic', 'map_cache') == 'True':
        print("Using offline map cache")
        database_path = 'DataBase' + os.path.sep + 'MapTiles.db3'
    mapview = TkinterMapView(frame_right, padx=0, pady=0, bg_color='#000000', corner_radius=6, database_path=database_path)
    mapview.pack(fill=tk.BOTH, expand=True) # grid(row=0, column=0, sticky='nsew')
    mapview.set_position(48.860381, 2.338594)
    mapview.set_tile_server(config.get('meshtastic', 'map_tileserver'), max_zoom=20)
    mapview.set_zoom(1)

    is_mapfullwindow = False
    def toggle_map(event=None):
        global is_mapfullwindow
        if is_mapfullwindow:
            # Restore mapview to frame_right
            mapview.pack_forget()
            mapview.pack(fill=tk.BOTH, expand=True)
            frame_right.grid(row=0, column=1, rowspan=5, columnspan=1, padx=0, pady=0, sticky='nsew')
        else:
            # Make mapview full screen
            mapview.pack_forget()
            mapview.pack(fill=tk.BOTH, expand=True)
            mapview.master.grid(row=0, column=0, rowspan=5, columnspan=3, padx=0, pady=0, sticky='nsew')
        is_mapfullwindow = not is_mapfullwindow
    root.bind('<F6>', toggle_map)
    '''
    def show_loradb():

        global dbconnection
        # Create a new window
        new_window = tk.Toplevel(root)
        new_window.title("LoraDB Nodes")
        new_window.geometry("1440x810")
        new_window.configure(bg="#242424")
        style = ttk.Style()
        style.theme_use('default')
        # style.configure(".", font=('Fixedsys', 10))
        style.configure("Treeview", background="#242424", foreground="#eeeeee", fieldbackground="#3d3d3d")
        style.configure("Treeview.Heading", background="#242424", foreground="#eeeeee")
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
        tree.tag_configure('oddrow', background='#242424')
        tree.tag_configure('evenrow', background='#3d3d3d')
        tmpnodes = copy.deepcopy(LoraDB)
        tmpnodes = dict(sorted(tmpnodes.items(), key=lambda item: item[1][0], reverse=True))
        i = False
        for nodeID, data in tmpnodes.items():
            data[0] = datetime.fromtimestamp(int(data[0])).strftime('%d %b %y %H:%M')
            data[1] = unescape(data[1])
            data[2] = unescape(data[2])
            data[3] = data[3]
            data[4] = data[4]
            data[8] = datetime.fromtimestamp(int(data[8])).strftime('%d %b %y')
            if i:
                tree.insert("", "end", values=(nodeID, *data), tags=('oddrow',))
            else:
                tree.insert("", "end", values=(nodeID, *data), tags=('evenrow',))
            i = not i
        tree.pack(fill=tk.BOTH, expand=True)
        tmpnodes = None
    root.bind('<F5>', lambda event: show_loradb())
    '''
    # Right Status Window
    frame_middle = tk.Frame(frame, bg="#242424", borderwidth=0, highlightthickness=0, padx=0, pady=0)
    frame_middle.grid(row=0, column=2, rowspan=5, columnspan=1, padx=0, pady=0, sticky='nsew')
    frame_middle.grid_rowconfigure(0, weight=1)
    frame_middle.grid_columnconfigure(0, weight=0)
    text_box_middle = create_text(frame_middle, 0, 0, 0, 21)

    # Start OverLay window
    overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#999999', highlightthickness=1)
    overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame
    info_label = tk.Text(overlay, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), width=51, height=8)
    info_label.pack(pady=2)
    insert_colored_text(info_label, '\nConnect to Meshtastic\n\n', "#d1d1d1", center=True)
    insert_colored_text(info_label, 'Please connect to your Meshtastic device\n', "#d1d1d1", center=True)
    insert_colored_text(info_label, 'and press the Connect button\n\n', "#d1d1d1", center=True)
    connto = config.get('meshtastic', 'interface')
    if connto == 'serial':
        insert_colored_text(info_label, 'Connect to Serial Port : ' + config.get('meshtastic', 'serial_port') + '\n', "#2bd5ff", center=True)
    else:
        insert_colored_text(info_label, 'Connect to IP : ' + config.get('meshtastic', 'host') + '\n', "#2bd5ff", center=True)
    button = tk.Button(overlay, image=btn_img, command=start_mesh, borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Connect", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
    button.pack(padx=8)

    try:
        root.mainloop()
    except Exception as e:
        safedatabase()
        logging.error("Error : ", str(e))
        sys.exit()
