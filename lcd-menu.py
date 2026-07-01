#!/usr/bin/env python3
import sys
import os
import time
import qnaplcd
from collector import TruePanelCollector
from truepanel.pages.fans import fan_rpm_page, fan_pwm_page
import platform
import subprocess
import socket
import threading
import json

DISPLAY_TIMEOUT = 30    # seconds

PORT = '/dev/ttyS1'     # same as default
PORT_SPEED = 1200

lcd = None

lcd_timer = None
def lcd_on():
    global lcd_timer

    lcd.backlight(True)

    if lcd_timer:
        lcd_timer.cancel()

    lcd_timer = threading.Timer(DISPLAY_TIMEOUT, lambda: lcd.backlight(False))
    lcd_timer.start()

def shell(cmd):
    return subprocess.check_output(cmd, shell=True, universal_newlines=True).strip()


collector = TruePanelCollector()

def get_state(max_age=5):
    last = collector.state.get("last_updated")
    now = time.time()

    if last is None or now - last > max_age:
        collector.update()

    return collector.state


def show_version():
    sys_name = platform.node()
    sys_vers = f'{platform.system()} ({platform.machine()})'
    lcd.clear()
    lcd.write(0, [sys_name, sys_vers])

def show_truenas():
    if os.path.exists('/.dockerenv'):
        lines = ['TruePanel', 'Docker Mode']
    else:
        try:
            truenas = shell('cli -c \'system version\'')
            truenas = truenas.split('-')
            lines = ['-'.join(truenas[:-1]), truenas[-1]]
        except Exception:
            lines = ['TruePanel', 'Native Mode']

    lcd.clear()
    lcd.write(0, lines)

def show_uptime():
    uptime = shell('uptime').split(',')
    up = ' '.join(uptime[0].split()[2:]) + ' ' + uptime[1]
    load = os.getloadavg()
    lcd.clear()
    lcd.write(0, [f'Up  : {up}', f'Load: {load[0]} {load[1]}, {load[2]}'])




def show_cpu_ram():
    state = get_state()
    lcd.clear()
    lcd.write(0, [
        f'CPU: {state.get("cpu_percent", 0)}%',
        f'RAM: {state.get("ram_percent", 0)}%'
    ])


def show_pool_health():
    state = get_state()
    pools = state.get("pools", [])

    lcd.clear()

    if not pools:
        lcd.write(0, ['Pool Health', 'No Pool Data'])
        return

    bad = [p for p in pools if p.get("health") != "ONLINE"]

    if bad:
        pool = bad[0]
        lcd.write(0, ['Pool Alert', f'{pool["name"][:8]} {pool["health"][:7]}'])
    else:
        lcd.write(0, ['Pool Health', 'All Healthy'])

def add_ips_to_menu():
    def get_kind(iface):
        if 'linkinfo' in iface:
            if 'info_kind' in iface['linkinfo']:
                return iface['linkinfo']['info_kind']

        return ''

    def get_ipv4(iface):
        if 'addr_info' in iface:
            for addr in iface['addr_info']:
                if addr['family'] == 'inet':
                    return addr['local']

        return '0.0.0.0'

    ip_json = json.loads(shell('ip -details -json address show'))
    ip_addresses.clear()
    for iface in ip_json:
        if iface['link_type'] == 'loopback':
            continue

        if get_kind(iface) not in ['', 'tun']:
                continue

        ip_addresses.append(( iface['ifname'], get_ipv4(iface)))

    while show_ip in menu:
        menu.remove(show_ip)

    for _ in ip_addresses:
        menu.append(show_ip)

def show_ip():
    ip_index = 0
    for index in range(menu_item):
        if menu[index] == show_ip:
            ip_index += 1

    lcd.clear()
    lcd.write(0, [f'{ip_addresses[ip_index][0]}', f'{ip_addresses[ip_index][1]}'])

zfs_pools = []
ip_addresses = []
def add_zpools_to_menu():
    pools = shell('zpool list').split('\n')

    zfs_pools.clear()
    for pool in pools[1:]:
        zfs_pools.append(pool.split())

    # remove existing zfs pool menu items
    while show_zpool in menu:
        menu.remove(show_zpool)

    # add zfs pool menu items for discovered pools
    for _ in zfs_pools:
        menu.append(show_zpool)




def show_zpool():
    state = get_state()
    pools = state.get("pools", [])

    lcd.clear()

    if not pools:
        lcd.write(0, ['Storage', 'No Pool Data'])
        return

    pool = pools[menu_item % len(pools)]
    name = pool.get("name", "pool")
    health = pool.get("health", "UNKNOWN")
    capacity = pool.get("capacity", "0%")

    try:
        pct = int(str(capacity).strip('%'))
    except Exception:
        pct = 0

    filled = round((pct / 100) * 10)
    bar = '[' + ('#' * filled) + ('-' * (10 - filled)) + ']'

    lcd.write(0, [f'{name[:8]} {health[:7]}', f'{bar} {pct}%'])


def show_drive_temps():
    state = get_state()
    temps = state.get("temps", [])

    lcd.clear()

    if not temps:
        lcd.write(0, ['Drive Temps', 'No SMART Data'])
        return

    drive_info = temps[menu_item % len(temps)]
    drive = drive_info.get("drive", "disk")
    temp = drive_info.get("temp", 0)

    if temp >= 50:
        lcd.write(0, ['HOT DRIVE', f'{drive[:10]} {temp} C'])
    else:
        lcd.write(0, [f'Drive {drive[:10]}', f'Temp {temp} C'])


def show_fan_rpm():
    lcd.clear()
    lcd.write(0, fan_rpm_page())


def show_fan_pwm():
    lcd.clear()
    lcd.write(0, fan_pwm_page())

#
# Menu
#
menu_item = 0
menu = [
    show_truenas,
    show_version,
    show_uptime,
    show_cpu_ram,
    show_pool_health,
    show_zpool,
    show_drive_temps,
    show_fan_rpm,
    show_fan_pwm,
]

def response_handler(command, data):
    global menu_item, lcd_timeout
    prev_menu = menu_item

    #print(f'RECV: {command} - {data:#04x}')

    if command == 'Switch_Status':
        lcd_on()

        if data == 0x01: # up
            menu_item = (menu_item - 1) % len(menu)

        if data == 0x02: # down
            menu_item = (menu_item + 1) % len(menu)

    if prev_menu != menu_item:
        #print(f'SHOW: {menu_item}')
        menu[menu_item]()


def main():
    global lcd

    lcd = qnaplcd.QnapLCD(PORT, PORT_SPEED, response_handler)
    lcd_on()
    lcd.reset()
    lcd.clear()

    lcd.write(0, [platform.node(), 'System Ready...'])

    quit = False
    while not quit:
        add_ips_to_menu()
        # add_zpools_to_menu() disabled for Docker compatibility
        menu[menu_item]()

        print('sleep...')
        time.sleep(30)

    lcd.backlight(False)

main()
