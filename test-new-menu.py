#!/usr/bin/env python3
import time
import qnaplcd

from truepanel.menu.engine import MenuEngine
from truepanel.pages.basic import AboutPage, HostPage
from truepanel.pages.fan_pages import FanRPMPage, FanPWMPage

PORT = "/dev/ttyS1"
PORT_SPEED = 1200

lcd = qnaplcd.QnapLCD(PORT, PORT_SPEED)

menu = MenuEngine()
menu.register(AboutPage())
menu.register(HostPage())
menu.register(FanRPMPage())
menu.register(FanPWMPage())

for _ in range(8):
    lcd.clear()
    lcd.write(0, menu.render())
    menu.next()
    time.sleep(3)

lcd.clear()
lcd.write(0, ["TruePanel", "Test Done"])
