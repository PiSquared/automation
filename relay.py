#!/usr/bin/python3
import re
import time
import serial
import Queue
import config
import threading
import requests
import gpiozero
from flask import Flask

relays = [gpiozero.LED(x) for x in [4, 22, 6, 26]]
outlets = ["a"]
power_switch = "http://10.0.0.23/outlet{}?{}"
app = Flask(__name__)

state = "off"
state_enter_time = 0
commands = Queue.Queue()
display_status = {}
for i in config.DISPLAYS:
  display_status[i] = {}

def delayThread():
  global state
  global state_enter_time
  while True:
    if state == "boot_wait":
      for i in display_status.keys():
        if display_status[i]["DISPLAY.POWER"] != "ON":
          if time.time() - state_enter_time > 60:
            state = "off"
            state_enter_time = time.time()
            print("Failed to turn on display, timed out.")
          break
      else:
        state = "on"
        state_enter_time = time.time()
        for i in display_status.keys():
          serialCommand("DISPLAY.POWER", selected=i)
    elif state == "on":
      for i in display_status.keys():
        serialCommand("DISPLAY.POWER", selected=i)
    time.sleep(15)

def update_status(display, key, value):
  if not display in display_status.keys():
    print("Unknown display {} ({}={})".format(display, key, value))
    return
  if key in display_status[display].keys():
    if display_status[display][key] == value:
      return
  display_status[display][key] = value
  print("Updated {} ({}={})".format(display, key, value))
  if state == "boot_wait":
    if key == "SYSTEM.STATE":
      if value == "READY":
        serialCommand("DISPLAY.POWER", value="ON", selected=display)
      else:
        serialCommand("SYSTEM.STATE", selected=display)
  if state == "on":
    if key == "DISPLAY.POWER":
      if value == "OFF":
        serialCommand("DISPLAY.POWER", value="ON", selected=display)

def serialThread():
  pending = []
  with serial.Serial(config.SERIAL_PORT, config.SERIAL_BAUDRATE, timeout=1) as port:
    resp = bytearray()
    while True:
      try:
        while True:
          command = commands.get(block=False)
          for i in pending:
            if i[0] == command:
              break
          else:
            pending.append([command, time.time()])
            port.write(command)
            time.sleep(0.1)
      except Queue.Empty:
        pass
      now = time.time()
      for i in pending:
        if i[1] < now - 3:
          port.write(i[0])
          i[1] = now
          time.sleep(0.1)

      char = port.read()
      if char == '\r':
        try:
          string = resp.decode('ASCII')
          resp = bytearray()
        except UnicodeDecodeError:
          resp = bytearray()
          continue
        pattern = re.compile(r'(OP|KY|ST)([A-Z]\d)([A-Z\d\.]+)=(.+)')
        match = pattern.match(string)
        if match:
          if match.group(1) == "OP":
            target = match.group(2)
            key = match.group(3)
            value = match.group(4)
            pending = [x for x in pending if not x[0].startswith("OP{}{}".format(target, key))]
            update_status(target, key, value)
        else:
          print("Unmatched: {}".format(string))
      else:
        if char:
          resp.append(char)

def serialCommand(command, value="", cmd_type="OP", selected="A1", target=""):
  cmd = "{}{}{}".format(cmd_type, selected, command)
  if target:
      cmd += "({})".format(target)
  if value:
      cmd += "={}\r".format(value)
  else:
      cmd += "?\r"
  commands.put(cmd.encode('ASCII'))

@app.route("/status")
def get_status():
  return state

@app.route("/on")
def on():
  global state
  global state_enter_time
  state = "boot_wait"
  state_enter_time = time.time()
  for i in display_status.keys():
    display_status[i]["DISPLAY.POWER"] = "UNKNOWN"
    serialCommand("SYSTEM.STATE", selected=i)
  for i in relays:
    i.on()
  for i in outlets:
    requests.get(power_switch.format('on', i), auth=('admin', 'admin'))
  return "success"

@app.route("/off")
def off():
  global state
  global state_enter_time
  state = "off"
  state_enter_time = time.time()
  for i in relays:
    i.off()
  for i in outlets:
    requests.get(power_switch.format('off', i), auth=('admin', 'admin'))
  return "success"

off()

serialThreadHandle = threading.Thread(target=serialThread)
serialThreadHandle.daemon = True
serialThreadHandle.start()

delayThreadHandle = threading.Thread(target=delayThread)
delayThreadHandle.daemon = True
delayThreadHandle.start()
