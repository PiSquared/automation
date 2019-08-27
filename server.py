import os
import json
import time
import psutil
import signal
import subprocess
import mimetypes
import requests
from flask import Flask, render_template, jsonify, send_file
app = Flask(__name__)
import config

mimetypes.add_type('text/javascript', '.js')

@app.route("/api/display/<action>")
def display(action):
    if action == "on":
        requests.get("http://10.0.0.22/on")
    elif action == "off":
        requests.get("http://10.0.0.22/off")
    elif action == "status":
        resp = requests.get("http://10.0.0.22/status")
        return jsonify(success=True, result=resp.text, reason="")
    else:
        return jsonify(success=False, result=False, reason="Unknown Command")

def check_lock():
    if not os.path.isfile(config.APP_LOCK):
        return False
    with open(config.APP_LOCK, "r") as LOCK:
        lock_data = json.loads(LOCK.read())
    if psutil.pid_exists(lock_data['pid']):
        return lock_data
    else:
        os.remove(config.APP_LOCK)
        return False

def get_app_dir(application):
    if not application in os.listdir(config.APP_DIR):
        return False
    app_dir = os.path.join(config.APP_DIR, application)
    if not os.path.isdir(app_dir):
        return False
    return app_dir

@app.route("/api/app/launch/<application>")
def app_launch(application):
    if check_lock():
        return jsonify(success=False, reason="An application is already active.")
    app_dir = get_app_dir(application)
    if not app_dir:
        return jsonify(success=False, reason="Application not found.")
    launch_file = os.path.join(app_dir, "launch.bat")
    print("Launching {}".format(launch_file))
    if not os.path.isfile(launch_file):
        return jsonify(success=False, reason="Launcher not found.")
    proc = subprocess.Popen(launch_file, cwd=app_dir)
    print(proc)
    lock_data = {
        "pid": proc.pid,
        "app": application
    }
    with open(config.APP_LOCK, "w") as LOCK:
        LOCK.write(json.dumps(lock_data))
    return jsonify(success=True)

@app.route("/api/app/status")
def app_status():
    lock_data = check_lock()
    if lock_data:
        return jsonify(active=True, application=lock_data['app'])
    return jsonify(active=False, application="")

def kill_proc_tree(pid, sig=signal.SIGTERM, include_parent=True, timeout=None, on_terminate=None):
    parent = psutil.Process(pid)
    children = parent.children(recursive=True)
    if include_parent:
        children.append(parent)
    for p in children:
        p.send_signal(sig)
    psutil.wait_procs(children, timeout=timeout, callback=on_terminate)

@app.route("/api/app/list")
def app_list():
    apps = os.listdir(config.APP_DIR)
    apps = [x for x in apps if os.path.isdir(os.path.join(config.APP_DIR, x))]
    app_data = {}
    for application in apps:
        json_file = os.path.join(config.APP_DIR, application, "app.json")
        if os.path.isfile(json_file):
            with open(json_file, "r") as JSON:
                app_json = json.loads(JSON.read())
            app_data[application] = app_json
        else:
            app_data[application] = {
                "name": application,
                "description": "Sample Application"
            }
    return jsonify(app_data)

@app.route("/api/app/stop")
def app_stop():
    lock_data = check_lock()
    if lock_data:
        kill_proc_tree(lock_data['pid'])
        return jsonify(success=True)
    return jsonify(success=True)

@app.route("/api/app/icon/<application>")
def app_icon(application):
    app_dir = get_app_dir(application)
    if app_dir:
        icon_file = os.path.join(app_dir, "app.png")
        if os.path.isfile(icon_file):
            return send_file(icon_file)
    return app.send_static_file("app.png")

@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/sw.js")
def sw():
    return send_file("static/sw.js")
