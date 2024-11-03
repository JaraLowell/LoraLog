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
import yaml

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

def has_pairs(lst):
    return len(lst) != 0 and len(lst) % 2 == 0

config = ConfigParser()
config.read('config.ini')
telemetry_thread = None
position_thread  = None
trace_thread = None
MapMarkers = {}
ok2Send = 0
isConnect = False
MyLora = ''
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
    if idx in LoraDB:
        click_command(temp)
    else:
        logging.error(f'Node {idx} not in DB')

# Function to insert colored text
def insert_colored_text(text_widget, text, color, center=False, tag=None):
    global hr_img, MyLora
    parent_frame = str(text_widget.winfo_parent())
    if "frame5" not in parent_frame:
        text_widget.configure(state="normal")
        if color == '#d1d1d1': # and "frame3" not in parent_frame:
            text_widget.image_create("end", image=hr_img)
    text_widget.tag_configure(color, foreground=color)

    if tag: # and tag != MyLora:
        text_widget.tag_configure(tag, foreground=color, underline=False)
        text_widget.insert(tk.END, text, (color, tag))
        text_widget.tag_bind(tag, "<Button-1>", showLink)
    else:
        text_widget.insert(tk.END, text, color)

    if center:
        text_widget.tag_configure("center", justify='center')
        text_widget.tag_add("center", "1.0", "end")
    if "!frame5" not in parent_frame:
        text_widget.see(tk.END)
        text_widget.configure(state="disabled")

def add_message(text_widget, nodeid, mtext, msgtime, private=False, msend='all', ackn=True, bulk=False):
    label = LoraDB[nodeid][1] + " (" + LoraDB[nodeid][2] + ")"
    tcolor = "#00c983"
    if nodeid == MyLora: tcolor = "#02bae8"
    timestamp = datetime.fromtimestamp(msgtime).strftime("%Y-%m-%d %H:%M:%S")
    text_widget.image_create("end", image=hr_img)
    insert_colored_text(text_widget,'\n From ' + unescape(label),tcolor)
    if private:
            insert_colored_text(text_widget,' [Direct Message]', "#c9a500")
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
        add_message(text_box3, entry['nodeID'], unescape(entry['text']), entry['time'], private=entry['private'], msend=entry['send'], ackn=entry['ackn'], bulk=True)

#------------------------------------------------------------- Movment Tracker --------------------------------------------------------------------------
movement_log    = [] # movement_log = [{'nodeID': '1', 'time': 1698163200, 'latitude': 10.0, 'longitude': 20.0, 'altitude': 1000}, ...]
metrics_log     = [] # metrics_log  = [{'nodeID': '1', 'time': 1698163200, 'battery': 100, 'voltage': 3.7, 'utilization': 0.0, 'airutiltx': 0.0}, ...]
environment_log = [] # environment  = [{'nodeID': '1', 'time': 1698163200, 'temperature': 1.0, 'humidity': 20.0, 'pressure': 1010.0}, ...]
LoraDB          = {} # LoraDB       = {'nodeID': [timenow, ShortName, LongName, latitude, longitude, altitude, macaddr, hardware, timefirst, rightbarstats, mmqtt, snr, hops], ...}
chat_log        = [] # chat_log     = [{'nodeID': '1', 'time': 1698163200, 'private', True, 'send': 'nodeid or ch', 'ackn' : True, seen': False, 'text': 'Hello World!'}, ...]

# database_path = 'DataBase' + os.path.sep + "tiles.db"

LoraDBPath = 'DataBase' + os.path.sep + 'LoraDB.pkl'
if os.path.exists(LoraDBPath):
    with open(LoraDBPath, 'rb') as f:
        LoraDB = pickle.load(f)

MoveDBPath = 'DataBase' + os.path.sep + 'MoveDB.pkl'
if os.path.exists(MoveDBPath):
    with open(MoveDBPath, 'rb') as f:
        movement_log = pickle.load(f)

MetricsPath = 'DataBase' + os.path.sep + 'MetricsDB.pkl'
if os.path.exists(MetricsPath):
    with open(MetricsPath, 'rb') as f:
        metrics_log = pickle.load(f)

EnviPath = 'DataBase' + os.path.sep + 'EnviDB.pkl'
if os.path.exists(EnviPath):
    with open(EnviPath, 'rb') as f:
        environment_log = pickle.load(f)

ChatPath = 'DataBase' + os.path.sep + 'ChatDB.pkl'
if os.path.exists(ChatPath):
    with open(ChatPath, 'rb') as f:
        chat_log = pickle.load(f)

if len(LoraDB) > 1:
    logging.error("Loaded LoraDB with " + str(len(LoraDB)) + " entries")

def get_last_position(database, nodeID):
    for entry in reversed(database):
        if entry['nodeID'] == nodeID:
            return entry
    return None

def get_first_position(database, nodeID):
    for entry in database:
        if entry['nodeID'] == nodeID:
            return entry
    return None

def count_entries_for_node(database, nodeID):
    return len([entry for entry in database if entry['nodeID'] == nodeID])

def get_data_for_node(database, nodeID):
    data = [entry for entry in database if entry['nodeID'] == nodeID]
    return data

def safedatabase():
    global LoraDB, LoraDBPath, movement_log, MoveDBPath, metrics_log, MetricsPath, environment_log, EnviPath
    if not os.path.exists('DataBase'):
        os.makedirs('DataBase')
    with open(LoraDBPath, 'wb') as f:
        pickle.dump(LoraDB, f)
    with open(MoveDBPath, 'wb') as f:
        pickle.dump(movement_log, f)
    with open(MetricsPath, 'wb') as f:
        pickle.dump(metrics_log, f)
    with open(EnviPath, 'wb') as f:
        pickle.dump(environment_log, f)
    with open(ChatPath, 'wb') as f:
        pickle.dump(chat_log, f)
    logging.error("Database saved!")


#----------------------------------------------------------- Meshtastic Lora Con ------------------------------------------------------------------------
meshtastic_client = None
try:
    map_delete = int(config.get('meshtastic', 'map_delete_time')) * 60
    map_oldnode = int(config.get('meshtastic', 'map_oldnode_time')) * 60
    map_trail_age = int(config.get('meshtastic', 'map_trail_age')) * 60
    metrics_age = int(config.get('meshtastic', 'metrics_age')) * 60
except Exception as e :
    logging.error("Error loading databases: %s", str(e))
    map_delete = 2700
    map_oldnode = 86400
    map_trail_age = 43200
    metrics_age = 86400

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
    global meshtastic_client, MyLora, movement_log, loop, isLora, isConnect
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

    pub.subscribe(on_meshtastic_message, "meshtastic.receive", loop=asyncio.get_event_loop())
    pub.subscribe(on_meshtastic_connection, "meshtastic.connection.established")
    pub.subscribe(on_lost_meshtastic_connection,"meshtastic.connection.lost")

    print("MyLora: " + MyLora)
    root.wm_title("Meshtastic Lora Logger - " + unescape(LoraDB[MyLora][1]))

    logLora((nodeInfo['user']['id'])[1:], ['NODEINFO_APP', nodeInfo['user']['shortName'], nodeInfo['user']['longName'], nodeInfo['user']["macaddr"],nodeInfo['user']['hwModel']])

    nodeInfo = meshtastic_client.getNode('^local')
    # Lets get the Local Node's channels
    lora_config = nodeInfo.localConfig.lora
    modem_preset_enum = lora_config.modem_preset
    modem_preset_string = config_pb2._CONFIG_LORACONFIG_MODEMPRESET.values_by_number[modem_preset_enum].name
    channels = nodeInfo.channels
    if channels:
        for channel in channels:
            psk_base64 = base64.b64encode(channel.settings.psk).decode('utf-8')
            
            if channel.settings.name == '':
                mylorachan[channel.index] = str(channel.index)
            else:
                mylorachan[channel.index] = unidecode(channel.settings.name)
            
            if channel.index == 0 and mylorachan[channel.index] == '0':
                mylorachan[channel.index] = modem_preset_string

            if channel.index == 0:
                insert_colored_text(text_box1, " Lora Chat Channel 0 = " + mylorachan[0] + " using Key " + psk_base64 + "\n", "#00c983")
                padding_frame.config(text="Send a message to channel " + mylorachan[0])

    updatesnodes()
    return meshtastic_client

def req_meta():
    global meshtastic_client, loop
    try:
        meshtastic_client.localNode.getMetadata()
    except Exception as e:
        logging.error("Error requesting metadata: %s", str(e))
    finally:
        print(f"Finished requesting metadata")

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

def logLora(nodeID, info):
    global LoraDB
    tnow = int(time.time())
    if nodeID in LoraDB:
        LoraDB[nodeID][0] = tnow # time last seen
    else:
        LoraDB[nodeID] = [tnow, nodeID[-4:], '', -8.0, -8.0, 0, '', '', tnow, '0% 0.0v', '', '',-1, 0]
        insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
        insert_colored_text(text_box1, " New Node Logged [!" + nodeID + "]\n", "#e8643f", tag=nodeID)

    if info[0] == 'NODEINFO_APP':
        tmp = str(info[1].encode('ascii', 'xmlcharrefreplace'), 'ascii').replace("\n", "") # short name
        if tmp != '':
            LoraDB[nodeID][1] = tmp
        else:
            LoraDB[nodeID][1] = nodeID[-4:]
        tmp = str(info[2].encode('ascii', 'xmlcharrefreplace'), 'ascii').replace("\n", "") # long name
        if tmp != '':
            LoraDB[nodeID][2] = tmp
        else:
            LoraDB[nodeID][2] = '!' + nodeID
        LoraDB[nodeID][6] = info[3] # mac adress
        LoraDB[nodeID][7] = info[4] # hardware
    elif info[0] == 'POSITION_APP':
        LoraDB[nodeID][3] = info[1] # latitude
        LoraDB[nodeID][4] = info[2] # longitude
        LoraDB[nodeID][5] = info[3] # altitude

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

def on_meshtastic_message(packet, interface, loop=None):
    # print(yaml.dump(packet))
    global MyLora, MyLoraText1, MyLoraText2, LoraDB, MapMarkers, movement_log
    if MyLora == '':
        print('*** MyLora is empty ***\n' + yaml.dump(packet))
        return

    ischat = False
    tnow = int(time.time())
    rectime = tnow
    if 'rxTime' in packet:
        rectime = packet['rxTime']
    text_from = ''
    if 'fromId' in packet and packet['fromId'] is not None:
        text_from = packet.get('fromId', '')[1:]
    if text_from == '':
        text_from = idToHex(packet["from"])[1:]
    fromraw = text_from

    if "decoded" in packet:
        data = packet["decoded"]
        if text_from !='':
            viaMqtt = False
            text_msgs = ''
            if text_from in LoraDB:
                LoraDB[text_from][0] = tnow
                if LoraDB[text_from][1] != '':
                    text_from = LoraDB[text_from][1] + " (" + LoraDB[text_from][2] + ")"
            else:
                LoraDB[text_from] = [tnow, fromraw[-4:], '', -8.0, -8.0, 0, '', '', tnow, '0% 0.0v', '', '', -1, 0]
                insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                insert_colored_text(text_box1, " New Node Logged [!" + fromraw + "]\n", "#e8643f", tag=fromraw)
                playsound('Data' + os.path.sep + 'NewNode.mp3')

            if "viaMqtt" in packet:
                LoraDB[fromraw][10] = ' via mqtt'
                viaMqtt = True
            else:
                LoraDB[fromraw][10] = ''

            LoraDB[fromraw][12] = -1
            if "hopStart" in packet: LoraDB[fromraw][12] = packet['hopStart']

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
                        LoraDB[fromraw][9] = ''
                        text_raws += '\n' + (' ' * 11) + 'Battery: ' + str(device_metrics.get('batteryLevel', 0)) + '% '
                        if device_metrics.get('batteryLevel', 0) < 101:
                            LoraDB[fromraw][9] = str(device_metrics.get('batteryLevel', 0)) + '% '
                        text_raws += 'Power: ' + str(round(device_metrics.get('voltage', 0.00),2)) + 'v '
                        LoraDB[fromraw][9] += str(round(device_metrics.get('voltage', 0.00),2)) + 'v'
                        text_raws += 'ChUtil: ' + str(round(device_metrics.get('channelUtilization', 0.00),2)) + '% '
                        text_raws += 'AirUtilTX (DutyCycle): ' + str(round(device_metrics.get('airUtilTx', 0.00),2)) + '%'
                        if len(LoraDB[fromraw]) < 14:
                            LoraDB[fromraw].append(0)
                            logging.error(f"Node {fromraw} has no uptime and a length of {len(LoraDB[fromraw])}")
                        LoraDB[fromraw][13] = device_metrics.get('uptimeSeconds', 0)
                        text_raws += '\n' + (' ' * 11) + uptimmehuman(fromraw)
                        # Need store uptimme somwhere !
                        if MyLora == fromraw:
                            MyLoraText1 = (' ChUtil').ljust(13) + str(round(device_metrics.get('channelUtilization', 0.00),2)).rjust(6) + '%\n' + (' AirUtilTX').ljust(13) + str(round(device_metrics.get('airUtilTx', 0.00),2)).rjust(6) + '%\n' + (' Power').ljust(13) + str(round(device_metrics.get('voltage', 0.00),2)).rjust(6) + 'v\n' + (' Battery').ljust(13) + str(device_metrics.get('batteryLevel', 0)).rjust(6) + '%\n'
                        if 'batteryLevel' in device_metrics or 'voltage' in device_metrics or 'channelUtilization' in device_metrics or 'airUtilTx' in device_metrics:
                            metrics_log.append({'nodeID': fromraw, 'time': rectime, 'battery': device_metrics.get('batteryLevel', 0), 'voltage': round(device_metrics.get('voltage', 0.00),2), 'utilization': round(device_metrics.get('channelUtilization', 0.00),2), 'airutiltx': round(device_metrics.get('airUtilTx', 0.00),2)})
                    power_metrics = telemetry.get('powerMetrics', {})
                    if power_metrics:
                        text_raws += '\n' + (' ' * 11) + 'CH1 Voltage: ' + str(round(power_metrics.get('ch1_voltage', 'N/A'),2)) + 'v'
                        text_raws += ' CH1 Current: ' + str(round(power_metrics.get('ch1_current', 'N/A'),2)) + 'mA'
                        text_raws += ' CH2 Voltage: ' + str(round(power_metrics.get('ch2_voltage', 'N/A'),2)) + 'v'
                        text_raws += ' CH2 Current: ' + str(round(power_metrics.get('ch2_current', 'N/A'),2)) + 'mA'
                    environment_metrics = telemetry.get('environmentMetrics', {})
                    if environment_metrics:
                        text_raws += '\n' + (' ' * 11) + 'Temperature: ' + str(round(environment_metrics.get('temperature', 0.0),1)) + '°C'
                        text_raws += ' Humidity: ' + str(round(environment_metrics.get('relativeHumidity', 0.0),1)) + '%'
                        text_raws += ' Pressure: ' + str(round(environment_metrics.get('barometricPressure', 0.00),2)) + 'hPa'
                        if 'temperature' in environment_metrics or 'relativeHumidity' in environment_metrics or 'barometricPressure' in environment_metrics:
                            environment_log.append({'nodeID': fromraw, 'time': rectime, 'temperature': round(environment_metrics.get('temperature', 0.0),2), 'humidity': round(environment_metrics.get('relativeHumidity', 0.0),2), 'pressure': round(environment_metrics.get('barometricPressure', 0.00),2)})
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
                            text_chns = text_chns = str(mylorachan[0])

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
                text_msgs = 'Node Position '
                text_msgs += 'latitude ' + str(round(nodelat,4)) + ' '
                text_msgs += 'longitude ' + str(round(nodelon,4)) + ' '
                text_msgs += 'altitude ' + str(position.get('altitude', 0)) + ' meter\n' + (' ' * 11)
                if nodelat != -8.0 and nodelon != -8.0:
                    logLora(fromraw, ['POSITION_APP', nodelat, nodelon, position.get('altitude', 0)])
                    if MyLora != fromraw and LoraDB[fromraw][3] != -8.0 and LoraDB[fromraw][4] != -8.0:
                        text_msgs += "Distance: ±" + calc_gc(nodelat, nodelon, LoraDB[MyLora][3], LoraDB[MyLora][4]) + " "
                    if fromraw in MapMarkers:
                        MapMarkers[fromraw][0].set_position(nodelat, nodelon)
                        MapMarkers[fromraw][0].set_text(LoraDB[fromraw][1])
                    last_position = get_last_position(movement_log, fromraw)
                    if last_position and 'latitude' in position and 'longitude' in position:
                        if last_position['latitude'] != nodelat or last_position['longitude'] != nodelon:
                            movement_log.append({'nodeID': fromraw, 'time': rectime, 'latitude': nodelat, 'longitude': nodelon, 'altitude': position.get('altitude', 0)})
                            text_msgs += '(Moved!) '
                            if fromraw in MapMarkers and MapMarkers[fromraw][3] is not None:
                                MapMarkers[fromraw][3].delete()
                                MapMarkers[fromraw][3] = None
                        if fromraw in MapMarkers:
                            MapMarkers[fromraw][5] = 0
                    if 'precisionBits' in position and position.get('precisionBits', 0) > 0:
                        AcMeters = round(23905787.925008 * math.pow(0.5, position.get('precisionBits', 0)), 2)
                        if AcMeters > 1.0:
                            text_msgs += '(Accuracy ±' + print_range(AcMeters) + ') '
                            if fromraw in MapMarkers and AcMeters >= 30.0 and AcMeters <= 5000.0:
                                # Lets draw only a circle if distance bigger then 30m or smaller then 5km
                                if len(MapMarkers[fromraw]) == 7:
                                    MapMarkers[fromraw].append(None)
                                    MapMarkers[fromraw][7] = mapview.set_polygon(position=(nodelat, nodelon), range_in_meters=AcMeters ,fill_color="gray25")
                    if not last_position and 'latitude' in position and 'longitude' in position:
                        movement_log.append({'nodeID': fromraw, 'time': rectime, 'latitude': nodelat, 'longitude': nodelon, 'altitude': position.get('altitude', 0)})
                if "satsInView" in position:
                    text_msgs += '(' + str(position.get('satsInView', 0)) + ' satelites)'
                text_raws = text_msgs
            elif data["portnum"] == "NODEINFO_APP":
                node_info = packet['decoded'].get('user', {})
                if node_info:
                    lora_sn = str(node_info.get('shortName', str(fromraw)[:-4]).encode('ascii', 'xmlcharrefreplace'), 'ascii')
                    lora_ln = str(node_info.get('longName', 'N/A').encode('ascii', 'xmlcharrefreplace'), 'ascii')
                    lora_mc = node_info.get('macaddr', 'N/A')
                    lora_mo = node_info.get('hwModel', 'N/A')
                    logLora(fromraw, ['NODEINFO_APP', lora_sn, lora_ln, lora_mc, lora_mo])
                    if fromraw in MapMarkers:
                        MapMarkers[fromraw][0].set_text(unescape(lora_sn))
                    text_raws = "Node Info using hardware " + lora_mo
                    if 'isLicensed' in packet:
                        text_raws += " (Licensed)"
                    if 'role' in packet:
                        text_raws +=  " Role: " + node_info.get('role', 'N/A')
                    text_from = lora_sn + " (" + lora_ln + ")"
                else:
                    text_raws = 'Node Info No Data'
            elif data["portnum"] == "NEIGHBORINFO_APP":
                text_raws = 'Node Neighborinfo'
                listmaps = []
                if fromraw not in MapMarkers and fromraw in LoraDB:
                    if LoraDB[fromraw][3] != -8.0 and LoraDB[fromraw][4] != -8.0:
                        MapMarkers[fromraw] = [None, True, tnow, None, None, 0, None]
                        MapMarkers[fromraw][0] = mapview.set_marker(LoraDB[fromraw][3], LoraDB[fromraw][4], text=unescape(LoraDB[fromraw][1]), icon = tk_mqtt, text_color = '#02bae8', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                if fromraw in MapMarkers:
                    if len(MapMarkers[fromraw]) > 3 and MapMarkers[fromraw][3] is not None:
                        MapMarkers[fromraw][3].delete()
                        MapMarkers[fromraw][3] = None

                if "neighborinfo" in data and "neighbors" in data["neighborinfo"]:
                    text = data["neighborinfo"]["neighbors"]
                    if fromraw in MapMarkers and MapMarkers[fromraw][3] is not None:
                        MapMarkers[fromraw][3].delete()
                        MapMarkers[fromraw][3] = None
                    for neighbor in text:
                        nodeid = hex(neighbor["nodeId"])[2:]
                        if nodeid in LoraDB and LoraDB[nodeid][1] != '':
                            LoraDB[nodeid][0] = tnow
                            # Lets add to map ass well if we are not on map abd our db knows the station
                            if nodeid not in MapMarkers:
                                if LoraDB[nodeid][3] != -8.0 and LoraDB[nodeid][4] != -8.0:
                                    MapMarkers[nodeid] = [None, True, tnow, None, None, 0, None]
                                    MapMarkers[nodeid][0] = mapview.set_marker(LoraDB[nodeid][3], LoraDB[nodeid][4], text=unescape(LoraDB[nodeid][1]), icon = tk_mqtt, text_color = '#02bae8', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                            else:
                                MapMarkers[nodeid][2] = tnow
                            # Lets add to paths ass well if we are on map
                            if fromraw in MapMarkers:
                                if LoraDB[nodeid][3] != -8.0 and LoraDB[nodeid][4] != -8.0:
                                    listmaps = []
                                    pos = (LoraDB[fromraw][3], LoraDB[fromraw][4])
                                    listmaps.append(pos)
                                    pos = (LoraDB[nodeid][3], LoraDB[nodeid][4])
                                    listmaps.append(pos)
                                    MapMarkers[fromraw][3] = mapview.set_path(listmaps, color="#006642", width=2)
                            nodeid = LoraDB[nodeid][1]
                        else:
                            nodeid = '!' + nodeid
                        text_raws += '\n' + (' ' * 11) + nodeid
                        if "snr" in neighbor:
                            text_raws += ' (' + str(neighbor["snr"]) + 'dB)'
                else:
                    text_raws += ' No Data'
            elif data["portnum"] == "RANGE_TEST_APP":
                text_raws = 'Node RangeTest'
                payload = data.get('payload', b'')
                text_raws += '\n' + (' ' * 11) + 'Payload: ' + str(payload.decode())
            elif data["portnum"] == "TRACEROUTE_APP":
                TraceTo = idToHex(packet['to'])
                TraceFrom = idToHex(packet['from'])
                if TraceTo[1:] in LoraDB: TraceTo = LoraDB[TraceTo[1:]][1]
                if TraceFrom[1:] in LoraDB: TraceFrom = LoraDB[TraceFrom[1:]][1]

                route = packet['decoded']['traceroute'].get('route', [])
                snr = packet['decoded']['traceroute'].get('snrTowards', [])
                routeBack = packet['decoded']['traceroute'].get('routeBack', [])
                snrBack = packet['decoded']['traceroute'].get('snrBack', [])
                text_raws = 'Node Traceroute\n' + (' ' * 11) + 'From : ' + TraceTo + ' --> '
                index = 0
                if routeBack:
                    for nodeuuid in routeBack:
                        nodeidt = idToHex(nodeuuid)[1:]
                        if nodeidt in LoraDB:
                            text_raws += LoraDB[nodeidt][1]
                        else:
                            text_raws += '!' + nodeidt
                        if snrBack and snrBack[index] != -128 and snrBack[index] != 0:
                            text_raws += f" ({snrBack[index] / 4:.2f}dB)"
                        text_raws += ' --> '
                        index += 1
                text_raws += TraceFrom
                if snrBack and snrBack[index] != -128 and snrBack[index] != 0:
                    text_raws += f" ({snrBack[index] / 4:.2f}dB)"
                text_raws += '\n' + (' ' * 11) + 'Back : ' + TraceFrom + ' --> '
                index = 0
                if route:
                    for nodeuuid in route:
                        nodeidt = idToHex(nodeuuid)[1:]
                        if nodeidt in LoraDB:
                            text_raws += LoraDB[nodeidt][1]
                        else:
                            text_raws += '!' + nodeidt
                        if snr and snr[index] != -128 and snr[index] != 0:
                            text_raws += f" ({snr[index] / 4:.2f}dB)"
                        text_raws += ' --> '
                        index += 1
                text_raws += TraceTo
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

            if "snr" in packet and packet['snr'] is not None:
                LoraDB[fromraw][11] = str(packet['snr']) + 'dB'

            if "rxSnr" in packet and packet['rxSnr'] is not None:
                LoraDB[fromraw][11] = str(packet['rxSnr']) + 'dB'

            # Lets work the map
            if fromraw != MyLora:
                if fromraw in MapMarkers:
                    MapMarkers[fromraw][2] = tnow
                    if viaMqtt == True and MapMarkers[fromraw][1] == False:
                        MapMarkers[fromraw][1] = True
                        MapMarkers[fromraw][0].change_icon(tk_mqtt)
                    elif viaMqtt == False and MapMarkers[fromraw][1] == True:
                        MapMarkers[fromraw][1] = False
                        MapMarkers[fromraw][0].change_icon(tk_direct)
                elif LoraDB[fromraw][3] != -8.0 and LoraDB[fromraw][4] != -8.0 and viaMqtt == True:
                    MapMarkers[fromraw] = [None, True, tnow, None, None, 0, None]
                    MapMarkers[fromraw][0] = mapview.set_marker(LoraDB[fromraw][3], LoraDB[fromraw][4], text=unescape(LoraDB[fromraw][1]), icon = tk_mqtt, text_color = '#02bae8', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                    MapMarkers[fromraw][0].text_color = '#02bae8'
                elif LoraDB[fromraw][3] != -8.0 and LoraDB[fromraw][4] != -8.0 and viaMqtt == False:
                    MapMarkers[fromraw] = [None, False, tnow, None, None, 0, None]
                    MapMarkers[fromraw][0] = mapview.set_marker(LoraDB[fromraw][3], LoraDB[fromraw][4], text=unescape(LoraDB[fromraw][1]), icon = tk_direct, text_color = '#02bae8', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                    MapMarkers[fromraw][0].text_color = '#02bae8'

            # Lets add a indicator
            if fromraw in MapMarkers and MapMarkers[fromraw][6] == None and 'localstats_metrics' not in packet:
                MapMarkers[fromraw][6] = mapview.set_marker(LoraDB[fromraw][3], LoraDB[fromraw][4], icon = snd_icon, data=fromraw, command = click_command)

            # Cleanup and get ready to print
            text_from = unescape(text_from)
            text_raws = unescape(text_raws)
            if text_raws != '' and MyLora != fromraw:
                insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + ' [!' + fromraw + ']' + LoraDB[fromraw][10] + "\n", "#d1d1d1", tag=fromraw)
                if ischat == True:
                    prv = False
                    if text_chns == 'Private': prv = True
                    add_message(text_box3, fromraw, text_raws, tnow, private=prv)
                if viaMqtt == True:
                    insert_colored_text(text_box1, (' ' * 11) + text_raws + '\n', "#c9a500")
                else:
                    text_from = ''
                    if LoraDB[fromraw][12] > 0:
                        text_from = '\n' + (' ' * 11) + str(LoraDB[fromraw][12]) + ' hops '
                    if LoraDB[fromraw][11] != '' and MyLora != fromraw:
                        if text_from == '':
                            text_from = '\n' + (' ' * 11)
                        v = float(LoraDB[fromraw][11].replace('dB', ''))
                        text_from += f"{round(v,1)}dB {value_to_graph(v)}"

                    insert_colored_text(text_box1, (' ' * 11) + text_raws + text_from + '\n', "#00c983")
            elif text_raws != '' and MyLora == fromraw:
                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + LoraDB[fromraw][10] + "\n", "#d1d1d1", tag=fromraw)
                insert_colored_text(text_box2, (' ' * 11) + text_raws + '\n', "#00c983")
            else:
                insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] ' + text_from + ' [!' + fromraw + ']' + LoraDB[fromraw][10] + "\n", "#d1d1d1", tag=fromraw)
        else:
            logging.debug("No fromId in packet")
            insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + '] No fromId in packet\n', "#c24400")
    else:
        if text_from != '':
            if text_from in LoraDB:
                LoraDB[text_from][0] = tnow
                text_from = LoraDB[text_from][1] + " (" + LoraDB[text_from][2] + ") [!" + fromraw + "]"
            else:
                text_from = "Unknown Node [!" + fromraw + "]"
        insert_colored_text(text_box1, '[' + time.strftime("%H:%M:%S", time.localtime()) + ']', "#d1d1d1")
        insert_colored_text(text_box1, ' Encrypted packet from ' + text_from + '\n', "#db6544", tag=fromraw)

        if fromraw not in MapMarkers and fromraw in LoraDB:
            if LoraDB[fromraw][3] != -8.0 and LoraDB[fromraw][4] != -8.0:
                MapMarkers[fromraw] = [None, False, tnow, None, None, 0, None]
                MapMarkers[fromraw][0] = mapview.set_marker(LoraDB[fromraw][3], LoraDB[fromraw][4], text=unescape(LoraDB[fromraw][1]), icon = tk_old, text_color = '#aaaaaa', font = ('Fixedsys', 8), data=fromraw, command = click_command)
                MapMarkers[fromraw][0].text_color = '#aaaaaa'
                MapMarkers[fromraw][6] = mapview.set_marker(LoraDB[fromraw][3], LoraDB[fromraw][4], icon = snd_icon, data=fromraw, command = click_command)
        elif fromraw in MapMarkers and MapMarkers[fromraw][0] == None:
            MapMarkers[fromraw][6] = mapview.set_marker(LoraDB[fromraw][3], LoraDB[fromraw][4], icon = snd_icon, data=fromraw, command = click_command)

def updatesnodes():
    global LoraDB, MyLora, MapMarkers
    info = ''
    itmp = 0
    tnow = int(time.time())
    # a_while_back = tnow - int(timedelta(minutes=5).total_seconds())
    for nodes, info in meshtastic_client.nodes.items():
        if "user" in info:
            tmp = info['user']
            if "id" in tmp and tmp['id'] != '':
                # Only push to DB if we actually get a node ID
                nodeID = str(tmp['id'])[1:]
                if nodeID != '':
                    nodeLast = tnow
                    itmp = itmp + 1

                    if "lastHeard" in info and info["lastHeard"] is not None:
                        nodeLast = info['lastHeard']

                    if nodeID not in LoraDB:
                        LoraDB[nodeID] = [nodeLast, nodeID[-4:], '', -8.0, -8.0, 0, '', '', nodeLast, '0% 0.0v', '', '',-1, 0]
                        insert_colored_text(text_box1, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                        insert_colored_text(text_box1, " New Node Logged [!" + nodeID + "]\n", "#e8643f", tag=nodeID)

                    if "shortName" in tmp and "longName" in tmp:
                        lora_sn = str(tmp['shortName'].encode('ascii', 'xmlcharrefreplace'), 'ascii').replace("\n", "")
                        lora_ln = str(tmp['longName'].encode('ascii', 'xmlcharrefreplace'), 'ascii').replace("\n", "")
                        if lora_sn in lora_ln and "Meshtastic" in lora_ln:
                            if LoraDB[nodeID][1] == '': LoraDB[nodeID][1] = lora_ln
                            if LoraDB[nodeID][2] == '': LoraDB[nodeID][2] = lora_ln
                        else:
                            LoraDB[nodeID][1] = lora_sn
                            LoraDB[nodeID][2] = lora_ln
                    if "macaddr" in tmp: LoraDB[nodeID][6] = str(tmp['macaddr'])
                    if "hwModel" in tmp: LoraDB[nodeID][7] = str(tmp['hwModel'])
                    LoraDB[nodeID][12] = -1
                    if "hopsAway" in info: LoraDB[nodeID][12] = info['hopsAway']
                    if "position" in info and LoraDB[nodeID][3] == -8.0 and LoraDB[nodeID][4] == -8.0:
                        tmp2 = info['position']
                        if "latitude" in tmp2 and "longitude" in tmp2:
                            LoraDB[nodeID][3] = tmp2.get(round('latitude',6), -8.0)
                            LoraDB[nodeID][4] = tmp2.get(round('longitude',6), -8.0)
                        if "altitude" in tmp:
                            LoraDB[nodeID][5] = tmp2.get('altitude', 0)

                    if nodeID == MyLora:
                        LoraDB[MyLora][0] = tnow
                        if LoraDB[MyLora][3] != -8.0 and LoraDB[MyLora][4] != -8.0:
                            if MyLora not in MapMarkers:
                                MapMarkers[MyLora] = [None, False, tnow, None, None, 0, None]
                                MapMarkers[MyLora][0] = mapview.set_marker(LoraDB[MyLora][3], LoraDB[MyLora][4], text=unescape(LoraDB[MyLora][1]), icon = tk_icon, text_color = '#00c983', font = ('Fixedsys', 8), data=MyLora, command = click_command)
                                MapMarkers[MyLora][0].text_color = '#00c983'
                                mapview.set_position(LoraDB[MyLora][3], LoraDB[MyLora][4])
                        else:
                            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "]", "#d1d1d1")
                            insert_colored_text(text_box2, " My Node has no position !!\n", "#e8643f")

                    if "viaMqtt" in info: LoraDB[nodeID][10] = ' via mqtt'
                    if "snr" in info and info['snr'] is not None: LoraDB[nodeID][11] = str(info['snr']) + 'dB'

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

def uptimmehuman(node_id):
    tnow = int(time.time())
    days, remainder = divmod(LoraDB[node_id][13] + (tnow - LoraDB[node_id][0]), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    text = 'Uptime   : '
    if days > 0: text += str(days) + ' days, '
    text += str(hours) + ' hours and ' + str(minutes) + ' minutes'
    if tnow - LoraDB[node_id][0] >= map_delete: text += ' ? Seems offline'
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

    return f"{round(EARTH_R*c,1)}km"

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

def plot_metrics_log(metrics_log, node_id, frame, width=512, height=212):
    global MyLora
    metrics = get_data_for_node(metrics_log, node_id)
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
        return

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
    axs[0, 0].plot(times_resampled, battery_levels_smooth, label='Battery Level', color='#02bae8')
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
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        if total_hours > 11:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        else:
            ax.xaxis.set_major_locator(mdates.HourLocator())
        ax.title.set_color('white')
        ax.xaxis.label.set_color('white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.set(frame_on=False)
    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

def plot_environment_log(metrics_log, node_id, frame , width=512, height=184):
    metrics = get_data_for_node(metrics_log, node_id)
    df = DataFrame({
        'time': [datetime.fromtimestamp(entry['time']) for entry in metrics],
        'temperatures': [entry['temperature'] for entry in metrics],
        'humidities': [entry['humidity'] for entry in metrics],
        'pressures': [entry['pressure'] for entry in metrics],
    })
    resample_interval = len(df) // 80 or 5
    df_resampled = df.set_index('time').resample(f'{resample_interval}min').mean().dropna().reset_index()
    times = df_resampled['time'].tolist()
    temperatures_resampled = df_resampled['temperatures'].tolist()
    humidities_resampled = df_resampled['humidities'].tolist()
    pressures_resampled = df_resampled['pressures'].tolist()

    if len(temperatures_resampled) < 5 or len(humidities_resampled) < 5 or len(pressures_resampled) < 5:
        return

    temperatures = savgol_filter(temperatures_resampled, window_length=5, polyorder=2)
    humidities = savgol_filter(humidities_resampled, window_length=5, polyorder=2)
    pressures = savgol_filter(pressures_resampled, window_length=5, polyorder=2)

    total_hours = 0
    if len(times) > 1:
        total_hours = (times[-1] - times[0]).total_seconds() / 3600

    fig, ax1 = plt.subplots(figsize=(width/100, height/100))
    fig.patch.set_facecolor('#242424')

    ax1.set_facecolor('#242424')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
    if total_hours > 11:
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    else:
        ax1.xaxis.set_major_locator(mdates.HourLocator())
    ax1.plot(times, temperatures, '#c9a500', label='Temperature (°C)')
    ax1.plot(times, humidities, '#02bae8', label='Humidity (%)')
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
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

def plot_movment_curve(movement_log, node_id, frame, width=512, height=128):
    positions = get_data_for_node(movement_log, node_id)

    times = [entry['time'] for entry in positions]
    altitudes = [entry['altitude'] for entry in positions]
    dates = [datetime.fromtimestamp(time) for time in times]
    
    fig, ax = plt.subplots(figsize=(width/100, height/100))
    fig.patch.set_facecolor('#242424')
    ax.set_facecolor('#242424')
    ax.plot(dates, altitudes, marker='.', linestyle='-', color='#02bae8')

    ax.title.set_color('white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')
    ax.set(frame_on=False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.set_title('Altitude change in meters')
    ax.grid(True, color='#444444')

    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

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
        global isLora
        isLora = False
        if meshtastic_client is not None:
            meshtastic_client.close()
            safedatabase()
            logging.debug('Saved Databases')
        logging.debug("Closed Program")
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
        text_area = tk.Text(padding_frame, wrap=tk.WORD, width=frwidth, height=frheight, bg='#242424', fg='#dddddd', font=('Fixedsys', 10))
        text_area.grid(row=0, column=0, sticky='nsew')
        return text_area

    def send(event=None):
        text2send = my_msg.get().rstrip()
        if len(text2send.encode('utf-8')) > 220:
            # neeed check max, some seem to say 237 ?
            insert_colored_text(text_box3, "Text message to long, keep it under 220 bytes\n", "#d1d1d1")
        elif text2send != '':
            meshtastic_client.sendText(text2send)
            text_from = LoraDB[MyLora][1] + " (" + LoraDB[MyLora][2] + ")"
            add_message(text_box3, MyLora, text2send, int(time.time()), msend=str(mylorachan[0].encode('ascii', 'xmlcharrefreplace'), 'ascii'))
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
            insert_colored_text(text_box2, (' ' * 11) + '[to ' + str(mylorachan[0]) +'] ' + text2send + '\n', "#00c983")
            my_msg.set("")
            playsound('Data' + os.path.sep + 'NewChat.mp3')

    def send_position(nodeid):
        global meshtastic_client, loop, stop_thread
        print(f"Requesting Position Data from {nodeid}")
        try:
            meshtastic_client.sendPosition(destinationId=nodeid, wantResponse=True, channelIndex=0)
        except Exception as e:
            print(f"Error sending Position: {e}")
        finally:
            print(f"Finished sending Position")

    def send_telemetry(nodeid):
        global meshtastic_client, loop
        print(f"Requesting Telemetry Data from {nodeid}")
        try:
            meshtastic_client.sendTelemetry(destinationId=nodeid, wantResponse=True, channelIndex=0)
        except Exception as e:
            print(f"Error sending Telemetry: {e}")
        finally:
            print(f"Finished sending Telemetry")

    def send_trace(nodeid):
        global meshtastic_client, loop
        print(f"Requesting Traceroute Data from {nodeid}")
        try:
            meshtastic_client.sendTraceRoute(dest=nodeid, hopLimit=7, channelIndex=0)
        except Exception as e:
            print(f"Error sending Traceroute: {e}")
        finally:
            print(f"Finished sending Traceroute")

    def close_overlay():
        global overlay
        playsound('Data' + os.path.sep + 'Button.mp3')
        if has_open_figures():
            logging.debug("Closing open figures failed?")
        if overlay is not None:
            destroy_overlay()
        gc.collect()

    # Hadnle the buttons
    def buttonpress(info, nodeid):
        global ok2Send, telemetry_thread, position_thread, trace_thread
        text_from = LoraDB[MyLora][1] + " (" + LoraDB[MyLora][2] + ")"
        if ok2Send == 0:
            ok2Send = 15
            node_id = '!' + str(nodeid)
            if info == 'ReqInfo':
                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
                insert_colored_text(text_box2, (' ' * 11) + "Node Telemetry sending Telemetry request\n", "#02bae8")
                telemetry_thread = threading.Thread(target=send_telemetry, args=(node_id,))
                telemetry_thread.start()
            elif info == 'ReqPos':
                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
                insert_colored_text(text_box2, (' ' * 11) + "Node Position sending Position request\n", "#02bae8")
                position_thread = threading.Thread(target=send_position, args=(node_id,))
                position_thread.start()
            elif info == 'ReqTrace':
                insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
                insert_colored_text(text_box2, (' ' * 11) + "Node TraceRoute sending Trace Route request\n", "#02bae8")
                trace_thread = threading.Thread(target=send_trace, args=(node_id,))
                trace_thread.start()
        else:
            insert_colored_text(text_box2, "[" + time.strftime("%H:%M:%S", time.localtime()) + "] " + unescape(text_from) + "\n", "#d1d1d1")
            insert_colored_text(text_box2, (' ' * 11) + "Please wait before the next request, 30 secconds inbetween requests\n", "#02bae8")

    def chatbox(nodeid):
        global LoraDB, MyLora, overlay, my_chat, chat_input
        playsound('Data' + os.path.sep + 'Button.mp3')
        if has_open_figures():
            logging.debug("No fromId in packet")
        if overlay is not None:
            destroy_overlay()

        overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#999999', highlightthickness=1)
        overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame
        chat_label = tk.Label(overlay, text=unescape(LoraDB[nodeid][1]) + '\n' + unescape(LoraDB[nodeid][2]), font=('Fixedsys', 12), bg='#242424', fg='#02bae8')
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
            insert_colored_text(chat_box, f"[{timestamp}] {unescape(LoraDB[nodeid][1])}\n", "#d1d1d1")
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
        global LoraDB, MyLora, overlay, mapview
        # Destroy the existing overlay if it exists
        playsound('Data' + os.path.sep + 'Button.mp3')
        if has_open_figures():
            logging.debug("Closing open figures failed?")
        if overlay is not None:
           destroy_overlay()
        if marker.data not in LoraDB:
            logging.error(f"Node {marker.data} not in database")
            return
        overlay = Frame(root, bg='#242424', padx=3, pady=2, highlightbackground='#999999', highlightthickness=1)
        overlay.place(relx=0.5, rely=0.5, anchor='center')  # Center the frame

        info_label = tk.Text(overlay, bg='#242424', fg='#dddddd', font=('Fixedsys', 10), width=64, height=10)
        info_label.pack(pady=3)
        insert_colored_text(info_label, "⬢ ", "#" + marker.data[-6:],  center=True)

        if LoraDB[marker.data][2] != '':
            text_loc = unescape(LoraDB[marker.data][1]) + '\n' + unescape(LoraDB[marker.data][2]) + '\n'
        elif LoraDB[marker.data][1] != '':
            text_loc = unescape(LoraDB[marker.data][1]) + '\n'
        else:
            text_loc = '!' + marker.data + '\n'
        insert_colored_text(info_label, text_loc, "#02bae8",  center=True)
        if LoraDB[marker.data][3] == -8.0 and LoraDB[marker.data][4] == -8.0:
            text_loc = '  Position : Unknown\n'
        else:
            text_loc = '  Position : ' + str(LoraDB[marker.data][3]) + ' / ' + str(LoraDB[marker.data][4]) + ' (' + LatLon2qth(LoraDB[marker.data][3],LoraDB[marker.data][4])[:-2] + ')'
            text_loc += ' Altitude ' + str(LoraDB[marker.data][5]) + 'm\n'
        insert_colored_text(info_label, text_loc, "#d1d1d1")
        text_loc = '  HW Model : ' + str(LoraDB[marker.data][7]) + '\n'
        text_loc += '  Hex ID   : ' + '!' + str(marker.data).ljust(18)
        text_loc += 'MAC Addr  : ' + str(LoraDB[marker.data][6]) + '\n'
        # Add uptime back
        if LoraDB[marker.data][13] != 0:
            text_loc += '  ' + uptimmehuman(marker.data) + '\n'
        text_loc += '  Last SNR : ' + str(LoraDB[marker.data][11]).ljust(19)
        text_loc += 'Last Seen : ' + ez_date(int(time.time()) - LoraDB[marker.data][0]) + '\n'
        text_loc += '  Power    : ' + LoraDB[marker.data][9].ljust(19)
        text_loc += 'First Seen: ' + datetime.fromtimestamp(LoraDB[marker.data][8]).strftime('%b %#d \'%y') + '\n'
        if LoraDB[marker.data][3] != -8.0 and LoraDB[marker.data][3] != -8.0:
            text_loc += '  Distance : ' + calc_gc(LoraDB[marker.data][3], LoraDB[marker.data][4], LoraDB[MyLora][3], LoraDB[MyLora][4]).ljust(19)
        else:
            text_loc += '  Distance : ' + ('Unknown').ljust(19)
        if LoraDB[marker.data][12] > 0:
            text_loc += 'HopsAway  : ' + str(LoraDB[marker.data][12])
        insert_colored_text(info_label, text_loc, "#d1d1d1")

        if count_entries_for_node(metrics_log, marker.data) > 5:
            plot_metrics_log(metrics_log, marker.data, overlay)

        if count_entries_for_node(environment_log, marker.data) > 5:
            plot_environment_log(environment_log, marker.data, overlay)

        if count_entries_for_node(movement_log, marker.data) >= 2:
            plot_movment_curve(movement_log, marker.data, overlay)

        # Create a frame to hold the buttons
        if marker.data != MyLora:
            button_frame = Frame(overlay, bg='#242424')
            button_frame.pack(pady=2)

            button1 = tk.Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqInfo', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Request Info", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button1.pack(side=tk.LEFT, padx=1)

            button2 = tk.Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqPos', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Request Pos", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button2.pack(side=tk.LEFT, padx=1)

            button3 = tk.Button(button_frame, image=btn_img, command=lambda: buttonpress('ReqTrace', marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Trace Node", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
            button3.pack(side=tk.LEFT, padx=1)

        button_frame2 = Frame(overlay, bg='#242424')
        button_frame2.pack(pady=2)
        if LoraDB[marker.data][3] != -8.0 and LoraDB[marker.data][3] != -8.0:
            button4 = tk.Button(button_frame2, image=btn_img, command=lambda: mapview.set_position(LoraDB[marker.data][3], LoraDB[marker.data][4]), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Zoom", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        else:
            button4 = tk.Button(button_frame2, image=btn_img, borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Zoom", compound="center", fg='#616161', font=('Fixedsys', 10))
        button4.pack(side=tk.LEFT, padx=1)

        button5 = tk.Button(button_frame2, image=btn_img, command=lambda: close_overlay(), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Close", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        button5.pack(side=tk.LEFT, padx=1)

        button6 = tk.Button(button_frame2, image=btn_img, command=lambda: chatbox(marker.data), borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Chat", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
        button6.pack(side=tk.LEFT, padx=1)

    # Function to update the middle frame with the last 30 active nodes
    peekmem = 0

    def update_active_nodes():
        global MyLora, MyLoraText1, MyLoraText2, tlast, MapMarkers, LoraDB, ok2Send, movement_log, metrics_log, peekmem
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

        # sorted_nodes = sorted(LoraDB.items(), key=lambda item: item[1][0], reverse=True)

        sorted_nodes = sorted((item for item in LoraDB.items() if (tnow - item[1][0] <= map_oldnode)), key=lambda item: item[1][0], reverse=True)

        text_box_middle.delete("1.0", tk.END)

        insert_colored_text(text_box_middle, "\n " + LoraDB[MyLora][1] + "\n", "#ff8f8f", tag=MyLora)
        if MyLoraText1 != '':
            insert_colored_text(text_box_middle, MyLoraText1, "#c1c1c1")
        if MyLoraText2 != '':
            insert_colored_text(text_box_middle, MyLoraText2, "#c1c1c1")
        text_box_middle.mark_set(LoraDB[MyLora][1], "1.0")

        for node_id, node_info in sorted_nodes:
            node_time = node_info[0]

            if LoraDB[node_id][1] == '' or LoraDB[node_id][1] == ' ':
                LoraDB[node_id][1] = node_id[-4:]
            if LoraDB[node_id][0] == 0:
                LoraDB[node_id][0] = 1725865749
            if LoraDB[node_id][8] == 0: 
                LoraDB[node_id][8] = LoraDB[node_id][0]
            if 'v' not in LoraDB[node_id][9]:
                LoraDB[node_id][9] = '0% 0.0v'
            if len(node_info) < 14:
                LoraDB[node_id].append(0)
                logging.error(f"Node {node_id} has no uptime and a length of {len(node_info)}")
            if tnow - node_time >= map_oldnode and node_id != MyLora:
                if node_id in MapMarkers:
                    if MapMarkers[node_id][3] != None:
                        MapMarkers[node_id][3].delete()
                    if MapMarkers[node_id][4] != None:
                        MapMarkers[node_id][4].delete()
                    MapMarkers[node_id][0].delete()
                    del MapMarkers[node_id]
            elif tnow - node_time >= map_delete and node_id != MyLora:
                if node_id in MapMarkers:
                    if MapMarkers[node_id][0].text_color != '#aaaaaa':
                        if MapMarkers[node_id][3] is not None:
                            MapMarkers[node_id][3].delete()
                            MapMarkers[node_id][3] = None
                        if len(MapMarkers[node_id]) > 7:
                            MapMarkers[node_id][7].delete()
                            MapMarkers[node_id][7] = None
                            MapMarkers[node_id].pop()
                        MapMarkers[node_id][0].delete()
                        MapMarkers[node_id][0] = None
                        MapMarkers[node_id][0] = mapview.set_marker(LoraDB[node_id][3], LoraDB[node_id][4], text=unescape(LoraDB[node_id][1]), icon = tk_old, text_color = '#aaaaaa', font = ('Fixedsys', 8), data=node_id, command = click_command)
                        MapMarkers[node_id][0].text_color = '#aaaaaa'
                else:
                    if 'Meshtastic' in LoraDB[node_id][1]:
                        LoraDB[node_id][1] = (LoraDB[node_id][1])[-4:]
                    if LoraDB[node_id][3] != -8.0 and LoraDB[node_id][4] != -8.0:
                        MapMarkers[node_id] = [None, True, tnow, None, None, 0, None]
                        MapMarkers[node_id][0] = mapview.set_marker(LoraDB[node_id][3], LoraDB[node_id][4], text=unescape(LoraDB[node_id][1]), icon = tk_old, text_color = '#aaaaaa', font = ('Fixedsys', 8), data=node_id, command = click_command)
                        MapMarkers[node_id][0].text_color = '#aaaaaa'
            elif tnow - node_time < map_delete or node_id != MyLora:
                node_name = unescape(node_info[1]).ljust(9)
                node_wtime = ez_date(tnow - node_time).rjust(10)
                if LoraDB[node_id][3] != -8.0 and LoraDB[node_id][3] != -8.0:
                    node_dist = calc_gc(LoraDB[node_id][3], LoraDB[node_id][4], LoraDB[MyLora][3], LoraDB[MyLora][4]).ljust(9)
                else:
                    node_dist = ' '.ljust(9)
                node_sig = LoraDB[node_id][11].rjust(10)
                if MyLora != node_id:
                    if node_info[10] == ' via mqtt':
                        insert_colored_text(text_box_middle, ('─' * 14) + '\n', "#3d3d3d")
                        insert_colored_text(text_box_middle, f" {node_name}", "#c9a500", tag=node_id)
                        insert_colored_text(text_box_middle, f"{node_wtime}\n", "#9d9d9d")
                        insert_colored_text(text_box_middle, f" {node_dist}\n", "#9d9d9d")
                        if node_id not in MapMarkers:
                            if LoraDB[node_id][3] != -8.0 and LoraDB[node_id][4] != -8.0:
                                MapMarkers[node_id] = [None, True, tnow, None, None, 0, None]
                                MapMarkers[node_id][0] = mapview.set_marker(LoraDB[node_id][3], LoraDB[node_id][4], text=unescape(LoraDB[node_id][1]), icon = tk_mqtt, text_color = '#02bae8', font = ('Fixedsys', 8), data=node_id, command = click_command)
                                MapMarkers[node_id][0].text_color = '#02bae8'
                        elif MapMarkers[node_id][0].text_color != '#02bae8':
                            MapMarkers[node_id][0].delete()
                            MapMarkers[node_id][0] = None
                            MapMarkers[node_id][0] = mapview.set_marker(LoraDB[node_id][3], LoraDB[node_id][4], text=unescape(LoraDB[node_id][1]), icon = tk_mqtt, text_color = '#02bae8', font = ('Fixedsys', 8), data=node_id, command = click_command)
                            MapMarkers[node_id][0].text_color = '#02bae8'
                    else:
                        insert_colored_text(text_box_middle, ('─' * 14) + '\n', "#3d3d3d")
                        insert_colored_text(text_box_middle, f" {node_name}","#00c983", tag=node_id)
                        insert_colored_text(text_box_middle, f"{node_wtime}\n", "#9d9d9d")
                        insert_colored_text(text_box_middle, f" {node_dist}{node_sig}\n", "#9d9d9d")
                        if node_id not in MapMarkers:
                            if LoraDB[node_id][3] != -8.0 and LoraDB[node_id][4] != -8.0:
                                MapMarkers[node_id] = [None, False, tnow, None, None, 0, None]
                                MapMarkers[node_id][0] = mapview.set_marker(LoraDB[node_id][3], LoraDB[node_id][4], text=unescape(LoraDB[node_id][1]), icon = tk_direct, text_color = '#02bae8', font = ('Fixedsys', 8), data=node_id, command = click_command)
                                MapMarkers[node_id][0].text_color = '#02bae8'
                        elif MapMarkers[node_id][0].text_color != '#02bae8':
                            MapMarkers[node_id][0].delete()
                            MapMarkers[node_id][0] = None
                            MapMarkers[node_id][0] = mapview.set_marker(LoraDB[node_id][3], LoraDB[node_id][4], text=unescape(LoraDB[node_id][1]), icon = tk_direct, text_color = '#02bae8', font = ('Fixedsys', 8), data=node_id, command = click_command)
                            MapMarkers[node_id][0].text_color = '#02bae8'

        # Just some stats for checks
        insert_colored_text(text_box_middle, '\n' + ('─' * 14), "#3d3d3d")
        time1 = (time.perf_counter() - start) * 1000
        insert_colored_text(text_box_middle, f'\n Update  : {time1:.2f}ms', "#9d9d9d")
        # tmp2 = threading.active_count()
        # insert_colored_text(text_box_middle, f"\n Threads : {tmp2}", "#9d9d9d")
        tmp2 = int(psutil.Process(os.getpid()).memory_info().rss)
        time1 = round(tmp2 / 1024 / 1024 * 100,2) / 100
        if peekmem < time1:
            peekmem = time1
        insert_colored_text(text_box_middle, f"\n Mem     : {time1:.1f}MB\n", "#9d9d9d")
        insert_colored_text(text_box_middle, f" Mem Max : {peekmem:.1f}MB\n\n", "#9d9d9d")

        insert_colored_text(text_box_middle, " F5 View node DB\n F6 Map Extend Mode\n", "#9d9d9d")

        text_box_middle.yview_moveto(current_view[0])
        text_box_middle.configure(state="disabled")

        root.after(1000, update_paths_nodes)
    ### end

    def update_paths_nodes():
        global MyLora, LoraDB, movement_log, MapMarkers, tlast, pingcount, isConnect
        tnow = int(time.time())
        sorted_nodes = sorted((item for item in LoraDB.items() if (tnow - item[1][0] <= map_oldnode)), key=lambda item: item[1][0], reverse=True)
        for node_id, node_info in sorted_nodes:
            if node_id in MapMarkers:
                node_time = node_info[0]

                if MapMarkers[node_id][6] != None and (tnow - node_time) >= 3:
                    MapMarkers[node_id][6].delete()
                    MapMarkers[node_id][6] = None

                positions = get_data_for_node(movement_log, node_id)
                if MapMarkers[node_id][4] != None and MapMarkers[node_id][5] <= 0:
                    MapMarkers[node_id][4].delete()
                    MapMarkers[node_id][4] = None
                if len(positions) > 1 and tnow - node_info[0] <= map_oldnode:
                    if MapMarkers[node_id][5] <= 0:
                        drawline = []
                        # index = len(positions)
                        for position in positions:
                            # index -= 1 round(LoraDB[nodeid][3],6)
                            pos = (position['latitude'], position['longitude'])
                            drawline.append(pos)
                            # if index != 0:
                            #     MapMarkers[node_id][4] = mapview.set_marker(position['latitude'], position['longitude'], icon = tk_dot)
                            #     marker = MapMarkers[node_id][4]
                            #     mapview.canvas.lower(marker.canvas_icon, "marker")
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

            if has_open_figures():
                logging.debug("Closing open figures failed?")

            cutoff_time = tnow - map_trail_age
            movement_log[:] = [entry for entry in movement_log if not (entry['time'] < cutoff_time)]
            cutoff_time = tnow - metrics_age
            metrics_log[:] = [entry for entry in metrics_log if not (entry['time'] < cutoff_time)]
            environment_log[:] = [entry for entry in environment_log if not (entry['time'] < cutoff_time)]

            safedatabase()
            gc.collect()

        root.after(1000, update_active_nodes)

    def start_mesh():
        global overlay, root, ok2Send
        playsound('Data' + os.path.sep + 'Button.mp3')
        if overlay is not None:
            destroy_overlay()
        # Maybe add this to a connect button later via a overlay window and button as no window is shown duuring connect
        root.meshtastic_interface = connect_meshtastic()
        if root.meshtastic_interface is None:
            insert_colored_text(text_box1, "\n*** Failed to connect to meshtastic did you edit the config.ini    ***", "#02bae8")
            insert_colored_text(text_box1, "\n*** and wrote down the correct ip for tcp or commport for serial ? ***", "#02bae8")
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

    root = customtkinter.CTk()
    root.title("Meshtastic Lora Logger")
    root.geometry(f'1440x810')
    root.resizable(True, True)
    root.iconbitmap('Data' + os.path.sep + 'mesh.ico')
    root.protocol('WM_DELETE_WINDOW', on_closing)
    overlay = None

    # Map Marker Images
    tk_icon = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'marker.png'))
    tk_direct = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'marker-green.png'))
    tk_mqtt = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'marker-orange.png'))
    tk_old = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'marker-grey.png'))
    tk_dot = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'dot.png'))
    btn_img = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'ui_button.png'))
    hr_img = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'hr.png'))
    snd_icon = ImageTk.PhotoImage(Image.open('Data' + os.path.sep + 'signal.png'))

    my_msg = tk.StringVar()  # For the messages to be sent.
    my_msg.set("")
    my_label = tk.StringVar()
    my_label.set("Send a message to channel")
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
    insert_colored_text(text_box1,  "    __                     __\n   / /  ___  _ __ __ _    / /  ___   __ _  __ _  ___ _ __\n  / /  / _ \| '__/ _` |  / /  / _ \ / _` |/ _` |/ _ \ '__|\n / /__| (_) | | | (_| | / /__| (_) | (_| | (_| |  __/ |\n \____/\___/|_|  \__,_| \____/\___/ \__, |\__, |\___|_|\n                                    |___/ |___/ ", "#02bae8")
    insert_colored_text(text_box1, "//\ESHT/\ST/C\n", "#00c983")
    insert_colored_text(text_box1, "\n Meshtastic Lora Logger v 1.36 By Jara Lowell\n", "#02bae8")
    insert_colored_text(text_box1, " Meshtastic Lybrary : v" + meshtastic.version.get_active_version() + '\n', "#02bae8")
    text_box1.image_create("end", image=hr_img)
    insert_colored_text(text_box1, "\n", "#02bae8")
    text_box1.configure(state="disabled")

    # Left Middle Window
    text_box2 = create_text(frame, 1, 0, 10, 90)
    text_box2.configure(state="disabled")
    # Left Bottom Window
    text_box3 = create_text(frame, 2, 0, 15, 90)
    text_box3.configure(state="disabled")

    # Left Box Chat input
    padding_frame = tk.LabelFrame(frame, background="#242424", padx=0, pady=4, text=my_label.get(), bg='#242424', fg='#999999', font=('Fixedsys', 10), borderwidth=0, highlightthickness=0, labelanchor='n')
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

    mapview = TkinterMapView(frame_right, padx=0, pady=0, bg_color='#000000', corner_radius=6) # database_path=database_path, use_database_only=True
    mapview.pack(fill=tk.BOTH, expand=True) # grid(row=0, column=0, sticky='nsew')
    mapview.set_position(48.860381, 2.338594)
    mapview.set_tile_server(config.get('meshtastic', 'map_tileserver'), max_zoom=20)
    mapview.set_zoom(10)

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

    def show_loradb():
        global LoraDB
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
        insert_colored_text(info_label, 'Connect to Serial Port : ' + config.get('meshtastic', 'serial_port') + '\n', "#02bae8", center=True)
    else:
        insert_colored_text(info_label, 'Connect to IP : ' + config.get('meshtastic', 'host') + '\n', "#02bae8", center=True)
    button = tk.Button(overlay, image=btn_img, command=start_mesh, borderwidth=0, border=0, bg='#242424', activebackground='#242424', highlightthickness=0, highlightcolor="#242424", text="Connect", compound="center", fg='#d1d1d1', font=('Fixedsys', 10))
    button.pack(padx=8)

    try:
        root.mainloop()
    except Exception as e:
        safedatabase()
        logging.error("Error : ", str(e))
        sys.exit()
