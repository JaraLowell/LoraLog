# Batch config for Meshtastic nodes by KubaMiszcz
# From https://github.com/KubaMiszcz/Batch-import-default-config-to-meshtastic-node
# Seeing if we can make this work for our project

from asyncio import sleep
from copy import deepcopy
from enum import Enum
import os
import subprocess
import sys
import time
from types import SimpleNamespace
import meshtastic
import meshtastic.ble_interface
import meshtastic.serial_interface
import meshtastic.tcp_interface


class LALO_ENUM(Enum):
    COM = 1
    IP = 2
    BLE = 3


##################################################################################
# # example use from CLI, params are optional
# python set-my-defaults-pythonapi -tgt=COM4 -ln=JB_MOB_4 -sn=JBM4
# python set-my-defaults-pythonapi -tgt=ip:192.168.1.171 -ln=JB_MOB_Tak4 -sn=JBM4
# if no params defaults form below are used
##################################################################################
targetName = "COM3"  # options: COM1 | COM2 | COM3 ... etc
# targetName = "IP:192.168.1.172" # options: IP:xxx.xxx.xxx.xxx
# targetName = "BLE:JBR2_54f4"  # options: BLE:nodename
# targetName = "BLE:Meshtastic_54f4"  # options: BLE:nodename or MAC


vno = 3  # debugonly, otherwise set to 0

customSettings = SimpleNamespace(
    longName="JB_MOB_TAK4@2.5.7",
    shortName="JBM4",
    # options: ENABLED | DISABLED | NOT_PRESENT
    gpsMode=meshtastic.config_pb2.Config.PositionConfig.GpsMode.ENABLED,
    # !!!SENSITIVE_DATA!!! # it this link is embedded lora settings which are overrided below
    channelUrl=r'https://meshtastic.org/e/#CgMSAQESCAgBOAtAA0gB',
    bluetoothPIN=111000,  # !!!SENSITIVE_DATA!!! # max 6 digits
    # options: ['CLIENT', 'CLIENT_MUTE', 'ROUTER', 'ROUTER_CLIENT', 'REPEATER', 'TRACKER', 'SENSOR', 'TAK', 'CLIENT_HIDDEN', 'LOST_AND_FOUND', 'TAK_TRACKER']
    nodeRole=meshtastic.config_pb2.Config.DeviceConfig.Role.TAK,
    fixedLatitude=55.060981,
    fixedLongitude=23.982287,
    fixedAltitude=170,  # integers only
)

wifiNetworkParams = SimpleNamespace(
    enabled=True,
    dns=16885952,  # "192.168.1.1"
    gateway=16885952,  # "192.168.1.1"
    # you can get this from online calculators but enter like 172.1.168.192
    ip=2919344320,  # "192.168.1.174"
    subnet=16777215,  # "255.255.255.0"
    wifi_ssid="passw0rd",  # !!!SENSITIVE_DATA!!!
    wifi_psk="grzybnia",  # !!!SENSITIVE_DATA!!!
)


##########################################
########### BEGIN SCRIPT DATA ############

OKlbl = f"\033[30m\033[42mOK  :\033[0m "
SUCCESSlbl = f"\033[30m\033[42mSUCCESS:\033[0m "
INFOlbl = f"\033[30m\033[44mINFO:\033[0m "
WARNlbl = f"\033[30m\033[43mWARN:\033[0m "
ERRORlbl = f"\033[30m\033[41mERROR:\033[0m "
SAFETURNOFFlbl = f"\n\033[30m\033[44m  It’s now safe to turn off your computer...  \033[0m"


def ExtractParams(argv):
    if len(argv) > 1:
        argv = argv[1:]

        tgt = list(filter(lambda s: s.startswith('-tgt='), argv))
        tgt = tgt[0].split('=')[1] if len(tgt) > 0 else targetName

        ln = list(filter(lambda s: s.startswith('-ln='), argv))
        customSettings.longName = ln[0].split('=')[1] if len(
            ln) > 0 else customSettings.longName

        sn = list(filter(lambda s: s.startswith('-sn='), argv))
        customSettings.shortName = sn[0].split('=')[1][:4] if len(
            sn) > 0 else customSettings.shortName


def ConnectToNode(targetName):
    try:
        print(f"{INFOlbl}lookin for interface at: {targetName}")
        if targetName.startswith(LALO_ENUM.COM.name):
            interface = meshtastic.serial_interface.SerialInterface(
                devPath=targetName)
        elif targetName.startswith(LALO_ENUM.IP.name):
            ip = targetName.split(':')[1]
            interface = meshtastic.tcp_interface.TCPInterface(hostname=ip)
        elif targetName.startswith(LALO_ENUM.BLE.name):
            name = targetName.split(':')[1]
            # name = targetName[4:1024]
            interface = meshtastic.ble_interface.BLEInterface(address=name)
        else:
            raise
        print(f"{OKlbl}interface found at: {targetName}")
        return interface
    except:
        print(f"{ERRORlbl} interface {targetName} not found, exiting")
        exit(1)


#####################################
########### SCRIPT START ############

# extract params
ExtractParams(sys.argv)


loopNo = 1
while True:
    loopDirty = ''
    print('')
    print(f'{INFOlbl}start loop [{
          loopNo}] of updating preferences... {vno}')
    
    print(f'{INFOlbl}debugValue {vno}')


    interface = ConnectToNode(targetName)
    ourNode = interface.getNode('^local')
    # print(f'{INFOlbl}Our node existing localConfig {vno}:{ourNode.localConfig}')
    # print(f'{INFOlbl}Our node existing moduleConfig {vno}:{ourNode.moduleConfig}')

    # in this link is embedded lora settings which are overrided below
    # it needs to be set before lora due to changed lora settings modifies this link
    configName = 'channelUrl'
    prev = ourNode.getURL()
    if prev != customSettings.channelUrl:
        loopDirty += (f'[{configName}], ')
        print(f'{INFOlbl}update {
              configName} with new one https://meshtastic.org/e/...{customSettings.channelUrl[-4:]} ...')
        ourNode.setURL(customSettings.channelUrl)

    # localConfigs
    print(f'{INFOlbl}updating preferences, start loop [{loopNo}]')
    print(f'{INFOlbl}\tupdate localConfig...')
    # ourNode.beginSettingsTransaction()

    # bluetooth
    if not (targetName.startswith('BLE')):
        configName = 'bluetooth'
        # False if wifiNetworkParams.enabled else True
        prev = deepcopy(ourNode.localConfig.bluetooth)
        ourNode.localConfig.bluetooth.enabled = True
        ourNode.localConfig.bluetooth.fixed_pin = int(  # max 6 digits , add trail zeros if less
            str(customSettings.bluetoothPIN)[:6].ljust(6, '0'))
        ourNode.localConfig.bluetooth.mode = ourNode.localConfig.bluetooth.FIXED_PIN
        if prev != ourNode.localConfig.bluetooth:
            loopDirty += (f'[{configName}], ')
            print(f'{INFOlbl}\t  > update {configName}...')
            ourNode.writeConfig(configName)
    else:
        print(f'{WARNlbl}\tconnected by BLE - bluetooth cant be changed...')

    # device
    configName = 'device'
    prev = deepcopy(ourNode.localConfig.device)
    ourNode.localConfig.device.node_info_broadcast_secs = 3600 + vno
    ourNode.localConfig.device.rebroadcast_mode = ourNode.localConfig.device.LOCAL_ONLY
    ourNode.localConfig.device.role = customSettings.nodeRole
    ourNode.localConfig.device.serial_enabled = True
    if prev != ourNode.localConfig.device:
        loopDirty += (f'[{configName}], ')
        print(f'{INFOlbl}\t  > update {configName}...')
        ourNode.writeConfig(configName)

    # display
    configName = 'display'
    prev = deepcopy(ourNode.localConfig.display)
    ourNode.localConfig.display.gps_format = ourNode.localConfig.display.MGRS
    ourNode.localConfig.display.screen_on_secs = 60 + vno
    ourNode.localConfig.display.units = ourNode.localConfig.display.METRIC
    if prev != ourNode.localConfig.display:
        loopDirty += (f'[{configName}], ')
        print(f'{INFOlbl}\t  > update {configName}...')
        ourNode.writeConfig(configName)

    # lora
    configName = 'lora'
    prev = deepcopy(ourNode.localConfig.lora)
    ourNode.localConfig.lora.hop_limit = 7
    ourNode.localConfig.lora.override_duty_cycle = True
    ourNode.localConfig.lora.region = ourNode.localConfig.lora.NZ_865
    ourNode.localConfig.lora.sx126x_rx_boosted_gain = True
    ourNode.localConfig.lora.tx_enabled = True
    ourNode.localConfig.lora.tx_power = 20 + vno
    ourNode.localConfig.lora.use_preset = True
    ourNode.localConfig.lora.override_frequency = 433.625
    if prev != ourNode.localConfig.lora:
        loopDirty += (f'[{configName}], ')
        print(f'{INFOlbl}\t  > update {configName}...')
        ourNode.writeConfig(configName)
        customSettings.channelUrl = ourNode.getURL()

    # network
    configName = 'network'
    prev = deepcopy(ourNode.localConfig.network)
    ourNode.localConfig.network.address_mode = ourNode.localConfig.network.STATIC
    ourNode.localConfig.network.ipv4_config.dns = wifiNetworkParams.dns
    ourNode.localConfig.network.ipv4_config.gateway = wifiNetworkParams.gateway
    ourNode.localConfig.network.ipv4_config.ip = wifiNetworkParams.ip
    ourNode.localConfig.network.ipv4_config.subnet = wifiNetworkParams.subnet
    ourNode.localConfig.network.wifi_psk = wifiNetworkParams.wifi_psk
    ourNode.localConfig.network.wifi_ssid = wifiNetworkParams.wifi_ssid
    ourNode.localConfig.network.wifi_enabled = wifiNetworkParams.enabled  # True | False
    if prev != ourNode.localConfig.network:
        loopDirty += (f'[{configName}], ')
        print(f'{INFOlbl}\t  > update {configName}...')
        ourNode.writeConfig(configName)

    # position
    configName = 'position'
    prev = deepcopy(ourNode.localConfig.position)
    if customSettings.gpsMode == ourNode.localConfig.position.GpsMode.ENABLED:
        # mobile node
        ourNode.localConfig.position.gps_mode = ourNode.localConfig.position.GpsMode.ENABLED
        ourNode.localConfig.position.position_broadcast_secs = 3600 + vno
        ourNode.localConfig.position.position_broadcast_smart_enabled = True
        ourNode.localConfig.position.broadcast_smart_minimum_distance = 100 + vno
        ourNode.localConfig.position.broadcast_smart_minimum_interval_secs = 30 + vno
        ourNode.localConfig.position.fixed_position = False
        ourNode.localConfig.position.gps_update_interval = 120 + vno
    elif (customSettings.gpsMode == ourNode.localConfig.position.GpsMode.DISABLED
          ) or (customSettings.gpsMode == ourNode.localConfig.position.GpsMode.NOT_PRESENT):
        # stationary node
        ourNode.localConfig.position.gps_mode = ourNode.localConfig.position.GpsMode.DISABLED
        ourNode.localConfig.position.position_broadcast_secs = 86400 + vno
        ourNode.localConfig.position.fixed_position = True

    if prev != ourNode.localConfig.position:
        loopDirty += (f'[{configName}], ')
        print(f'{INFOlbl}\t  > update {configName}...')
        ourNode.writeConfig(configName)

    # moduleConfigs
    print(f'{INFOlbl}\tupdate moduleConfigs...')

    # neighbor_info
    configName = 'neighbor_info'
    prev = deepcopy(ourNode.moduleConfig.neighbor_info)
    ourNode.moduleConfig.neighbor_info.enabled = True
    ourNode.moduleConfig.neighbor_info.update_interval = 600 + vno
    if prev != ourNode.moduleConfig.neighbor_info:
        loopDirty += (f'[{configName}], ')
        print(f'{INFOlbl}\t  > update {configName}...')
        ourNode.writeConfig(configName)

    # update longname, shortname, islicensed
    print(f'{INFOlbl}update owner... {vno}')
    ourNode.setOwner(customSettings.longName,
                     customSettings.shortName[:4],
                     is_licensed=False)

    if customSettings.gpsMode == ourNode.localConfig.position.GpsMode.DISABLED:
        # dont move it to config position - it crashed there
        print(f'{INFOlbl}update fixedPosition...')
        ourNode.setFixedPosition(customSettings.fixedLatitude +
                                 vno, customSettings.fixedLongitude + vno,
                                 int(customSettings.fixedAltitude) + vno)

    # ourNode.commitSettingsTransaction()

    print(f'{INFOlbl}... finished loop [{
          loopNo}] of updating preferences {vno}')

    if len(loopDirty) > 0:
        print(f'{INFOlbl}\tthere were differences in configs: {loopDirty}')
        print(f'{INFOlbl}\tto ensure, running the next loop is needed')
        print(f'{INFOlbl}\tnode should reboots now, wait for reconnect...')
        loopNo += 1
        interface.close()
        time.sleep(5)
    else:
        print(f'{SUCCESSlbl}\tall compared, and all settings are up to date now')
        print(f'{INFOlbl}\tdue to loraConfig is updated, new channelUrl is now:')
        customSettings.channelUrl = ourNode.getURL()
        print(f'{INFOlbl}{customSettings.channelUrl}')
        print(f'{INFOlbl}node should reboots now')
        print(f'{SAFETURNOFFlbl}')
        break

# print(f'{INFOlbl}Our node updated localConfig {vno}:{ourNode.localConfig}')
# print(f'{INFOlbl}Our node updated moduleConfig {vno}:{ourNode.moduleConfig}')

# time.sleep(20)
# print(f'{INFOlbl} get setting from node...')
# os.popen("meshtastic --port COM4 --export-config > TBEAM-MOB-config.yaml")
# print(f'{INFOlbl} ... and save them')
# uncomment it to prevent immediately closing console window
# os.system("pause")

################################ EXAMPLE FOR TKINTER ################################

import tkinter as tk
from tkinter import ttk
from copy import deepcopy

# Assuming ourNode and customSettings are already defined and imported
# from LoraConfig import ourNode, customSettings, wifiNetworkParams

ourNode = interface.getNode('^local')

class LoraConfigApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lora Configuration")
        self.geometry("400x300")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both')

        self.create_device_tab()
        self.create_display_tab()
        self.create_lora_tab()
        self.create_network_tab()

    def create_device_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text='Device')

        self.node_info_broadcast_secs = tk.IntVar(value=ourNode.localConfig.device.node_info_broadcast_secs)
        self.rebroadcast_mode = tk.StringVar(value=ourNode.localConfig.device.rebroadcast_mode)
        self.role = tk.StringVar(value=customSettings.nodeRole)
        self.serial_enabled = tk.BooleanVar(value=ourNode.localConfig.device.serial_enabled)

        ttk.Label(frame, text="Node Info Broadcast Secs:").pack()
        ttk.Entry(frame, textvariable=self.node_info_broadcast_secs).pack()

        ttk.Label(frame, text="Rebroadcast Mode:").pack()
        ttk.Entry(frame, textvariable=self.rebroadcast_mode).pack()

        ttk.Label(frame, text="Role:").pack()
        ttk.Entry(frame, textvariable=self.role).pack()

        ttk.Checkbutton(frame, text="Serial Enabled", variable=self.serial_enabled).pack()

        ttk.Button(frame, text="Save", command=self.save_device_config).pack()

    def save_device_config(self):
        prev = deepcopy(ourNode.localConfig.device)
        ourNode.localConfig.device.node_info_broadcast_secs = self.node_info_broadcast_secs.get()
        ourNode.localConfig.device.rebroadcast_mode = self.rebroadcast_mode.get()
        ourNode.localConfig.device.role = self.role.get()
        ourNode.localConfig.device.serial_enabled = self.serial_enabled.get()
        if prev != ourNode.localConfig.device:
            print(f'Updating device config...')
            ourNode.writeConfig('device')

    def create_display_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text='Display')

        self.gps_format = tk.StringVar(value=ourNode.localConfig.display.gps_format)
        self.screen_on_secs = tk.IntVar(value=ourNode.localConfig.display.screen_on_secs)
        self.units = tk.StringVar(value=ourNode.localConfig.display.units)

        ttk.Label(frame, text="GPS Format:").pack()
        ttk.Entry(frame, textvariable=self.gps_format).pack()

        ttk.Label(frame, text="Screen On Secs:").pack()
        ttk.Entry(frame, textvariable=self.screen_on_secs).pack()

        ttk.Label(frame, text="Units:").pack()
        ttk.Entry(frame, textvariable=self.units).pack()

        ttk.Button(frame, text="Save", command=self.save_display_config).pack()

    def save_display_config(self):
        prev = deepcopy(ourNode.localConfig.display)
        ourNode.localConfig.display.gps_format = self.gps_format.get()
        ourNode.localConfig.display.screen_on_secs = self.screen_on_secs.get()
        ourNode.localConfig.display.units = self.units.get()
        if prev != ourNode.localConfig.display:
            print(f'Updating display config...')
            ourNode.writeConfig('display')

    def create_lora_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text='Lora')

        self.hop_limit = tk.IntVar(value=ourNode.localConfig.lora.hop_limit)
        self.override_duty_cycle = tk.BooleanVar(value=ourNode.localConfig.lora.override_duty_cycle)
        self.region = tk.StringVar(value=ourNode.localConfig.lora.region)
        self.sx126x_rx_boosted_gain = tk.BooleanVar(value=ourNode.localConfig.lora.sx126x_rx_boosted_gain)
        self.tx_enabled = tk.BooleanVar(value=ourNode.localConfig.lora.tx_enabled)
        self.tx_power = tk.IntVar(value=ourNode.localConfig.lora.tx_power)
        self.use_preset = tk.BooleanVar(value=ourNode.localConfig.lora.use_preset)
        self.override_frequency = tk.DoubleVar(value=ourNode.localConfig.lora.override_frequency)

        ttk.Label(frame, text="Hop Limit:").pack()
        ttk.Entry(frame, textvariable=self.hop_limit).pack()

        ttk.Checkbutton(frame, text="Override Duty Cycle", variable=self.override_duty_cycle).pack()

        ttk.Label(frame, text="Region:").pack()
        ttk.Entry(frame, textvariable=self.region).pack()

        ttk.Checkbutton(frame, text="RX Boosted Gain", variable=self.sx126x_rx_boosted_gain).pack()

        ttk.Checkbutton(frame, text="TX Enabled", variable=self.tx_enabled).pack()

        ttk.Label(frame, text="TX Power:").pack()
        ttk.Entry(frame, textvariable=self.tx_power).pack()

        ttk.Checkbutton(frame, text="Use Preset", variable=self.use_preset).pack()

        ttk.Label(frame, text="Override Frequency:").pack()
        ttk.Entry(frame, textvariable=self.override_frequency).pack()

        ttk.Button(frame, text="Save", command=self.save_lora_config).pack()

    def save_lora_config(self):
        prev = deepcopy(ourNode.localConfig.lora)
        ourNode.localConfig.lora.hop_limit = self.hop_limit.get()
        ourNode.localConfig.lora.override_duty_cycle = self.override_duty_cycle.get()
        ourNode.localConfig.lora.region = self.region.get()
        ourNode.localConfig.lora.sx126x_rx_boosted_gain = self.sx126x_rx_boosted_gain.get()
        ourNode.localConfig.lora.tx_enabled = self.tx_enabled.get()
        ourNode.localConfig.lora.tx_power = self.tx_power.get()
        ourNode.localConfig.lora.use_preset = self.use_preset.get()
        ourNode.localConfig.lora.override_frequency = self.override_frequency.get()
        if prev != ourNode.localConfig.lora:
            print(f'Updating lora config...')
            ourNode.writeConfig('lora')
            customSettings.channelUrl = ourNode.getURL()

    def create_network_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text='Network')

        self.address_mode = tk.StringVar(value=ourNode.localConfig.network.address_mode)
        self.dns = tk.StringVar(value=wifiNetworkParams.dns)
        self.gateway = tk.StringVar(value=wifiNetworkParams.gateway)
        self.ip = tk.StringVar(value=wifiNetworkParams.ip)
        self.subnet = tk.StringVar(value=wifiNetworkParams.subnet)
        self.wifi_psk = tk.StringVar(value=wifiNetworkParams.wifi_psk)
        self.wifi_ssid = tk.StringVar(value=wifiNetworkParams.wifi_ssid)

        ttk.Label(frame, text="Address Mode:").pack()
        ttk.Entry(frame, textvariable=self.address_mode).pack()

        ttk.Label(frame, text="DNS:").pack()
        ttk.Entry(frame, textvariable=self.dns).pack()

        ttk.Label(frame, text="Gateway:").pack()
        ttk.Entry(frame, textvariable=self.gateway).pack()

        ttk.Label(frame, text="IP:").pack()
        ttk.Entry(frame, textvariable=self.ip).pack()

        ttk.Label(frame, text="Subnet:").pack()
        ttk.Entry(frame, textvariable=self.subnet).pack()

        ttk.Label(frame, text="WiFi PSK:").pack()
        ttk.Entry(frame, textvariable=self.wifi_psk).pack()

        ttk.Label(frame, text="WiFi SSID:").pack()
        ttk.Entry(frame, textvariable=self.wifi_ssid).pack()

        ttk.Button(frame, text="Save", command=self.save_network_config).pack()

    def save_network_config(self):
        prev = deepcopy(ourNode.localConfig.network)
        ourNode.localConfig.network.address_mode = self.address_mode.get()
        ourNode.localConfig.network.ipv4_config.dns = self.dns.get()
        ourNode.localConfig.network.ipv4_config.gateway = self.gateway.get()
        ourNode.localConfig.network.ipv4_config.ip = self.ip.get()
        ourNode.localConfig.network.ipv4_config.subnet = self.subnet.get()
        ourNode.localConfig.network.wifi_psk = self.wifi_psk.get()
        ourNode.localConfig.network.wifi_ssid = self.wifi_ssid.get()
        if prev != ourNode.localConfig.network:
            print(f'Updating network config...')
            ourNode.writeConfig('network')

if __name__ == "__main__":
    app = LoraConfigApp()
    app.mainloop()