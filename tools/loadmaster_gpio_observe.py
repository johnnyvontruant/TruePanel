#!/usr/bin/env python3
"""Read-only QNAP Copy-button GPIO observation; never arms Loadmaster."""
import json
import time
from truepanel.hardware.fintek_gpio import FintekCopyButtonReader
from truepanel.host.ownership import HostOwnershipGuard

owner = HostOwnershipGuard('loadmaster-gpio-readonly-diagnostic')
owner.acquire()
try:
    with FintekCopyButtonReader() as reader:
        started = time.monotonic()
        baseline = reader.read_level()
        print(json.dumps({'event':'GPIO_DIAGNOSTIC_READY',
                          'baseline':baseline,'pressed_level':0,
                          'index_port':reader.runtime_index_port,
                          'data_port':reader.runtime_data_port}),flush=True)
        previous=baseline
        samples=0
        while time.monotonic()-started<75:
            value=reader.read_level()
            samples+=1
            if value!=previous:
                print(json.dumps({'event':'GPIO_EDGE','level':value,
                                  'seconds':round(time.monotonic()-started,3)}),flush=True)
                previous=value
            time.sleep(0.02)
        print(json.dumps({'event':'GPIO_DIAGNOSTIC_COMPLETE',
                          'samples':samples,'last_level':previous}),flush=True)
finally:
    owner.release()
