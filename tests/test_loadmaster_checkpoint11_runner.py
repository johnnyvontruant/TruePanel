"""Fail-closed Checkpoint 11 runner tests; no GPIO, mount or USB writes."""
from __future__ import annotations
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import CargoAction, CargoScope
from tools import loadmaster_spare_bidirectional_live_fire as runner
from tools import loadmaster_checkpoint11_prepare as prepare

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.scope = CargoScope('spare-lab', runner.SPARE_UUID, runner.SPARE_SERIAL, (
            CargoAction(*runner.EXPORT, 1024, 'a'*64),
            CargoAction(*runner.INGEST, 2048, 'b'*64)))

    @patch.object(runner,'_preflight')
    def test_read_only_preview_does_not_start_any_hardware(self, p):
        p.return_value=self.scope
        with patch.object(runner, '_start_guard') as watchdog, \
             patch.object(runner, 'FintekCopyButtonReader') as gpio, \
             patch.object(runner, 'execute_supervised_bidirectional_batch') as actor:
            self.assertEqual(runner.execute(live=False,operator_present=False,recover_verified=False),0)
            watchdog.assert_not_called();gpio.assert_not_called();actor.assert_not_called()

    @patch.object(runner,'_preflight')
    @patch.object(runner,'_private_folder')
    def test_no_operator_never_starts_actuation(self, private,p):
        p.return_value=self.scope
        with patch.object(runner,'_start_guard') as guard:
            with self.assertRaises(BackupExecutionError):
                runner.execute(live=True,operator_present=False,recover_verified=False)
            guard.assert_not_called()

    @patch.object(runner,'_preflight')
    @patch.object(runner,'_private_folder')
    @patch.object(runner,'_service_active')
    def test_running_production_service_blocks_gpio(self, active, private,p):
        p.return_value=self.scope
        active.return_value=True
        with patch.object(runner, 'FintekCopyButtonReader') as gpio:
            with self.assertRaises(BackupExecutionError):
                runner.execute(live=True,operator_present=True,recover_verified=False)
            gpio.assert_not_called()

    @patch.object(runner,'_preflight')
    @patch.object(runner,'_private_folder')
    def test_missing_rescue_program_blocks_gpio(self, private,p):
        p.return_value=self.scope
        with patch.object(runner,'_service_active',return_value=False),\
             patch.object(Path,'is_file',return_value=False), \
             patch.object(runner,'FintekCopyButtonReader') as gpio:
            with self.assertRaises(BackupExecutionError):
                runner.execute(live=True,operator_present=True,recover_verified=False)
            gpio.assert_not_called()

    @patch.object(runner,'_preflight')
    @patch.object(runner,'_private_folder')
    def test_guard_before_actuator_and_verified_ro(self, private,p):
        p.return_value=self.scope
        timeline=[]
        with patch.object(runner, '_service_active', side_effect=lambda unit: unit=='truepanel-mission-control.service'), \
             patch.object(Path, 'is_file',return_value=True), \
             patch.object(runner,'HostOwnershipGuard') as own, \
             patch.object(runner,'FintekCopyButtonReader') as gpio, \
             patch.object(runner,'LoadmasterCopyButtonService') as service, \
             patch.object(runner,'HostBidirectionalApprovalSession'), \
             patch.object(runner,'LoadmasterHostSessionBridge') as bridge, \
             patch.object(runner,'_start_guard',side_effect=lambda scope,folder: (timeline.append('guard') or ('unit',lambda:True))), \
             patch.object(runner,'execute_supervised_bidirectional_batch',side_effect=lambda **kw: (timeline.append('actuator') or {'state':'HOST_BIDIRECTIONAL_VERIFIED'})), \
             patch.object(runner, 'mount_mode',return_value='ro'):
            bridge.return_value.confirmed=True
            bridge.return_value.prepare_and_arm.return_value={'plan_digest':self.scope.digest,'backup_files':2}
            result=runner.execute(live=True,operator_present=True,recover_verified=False)
            self.assertEqual(result,0)
            self.assertEqual(timeline,['guard','actuator'])
            own.return_value.release.assert_called_once()
            bridge.return_value.disarm.assert_called_once()
            service.return_value.stop.assert_called_once()
            gpio.return_value.close.assert_called_once()

    @patch.object(runner,'mount_mode',return_value='ro')
    @patch.object(runner,'owner_start_ticks',return_value=999)
    @patch.object(runner,'verify_independent_guard',return_value=True)
    @patch.object(runner,'_state_unit_fields',return_value={'ActiveState':'active','LoadState':'loaded'})
    def test_guard_uses_host_namespace_and_separate_ro_rescue(self, *mocks):
        commands=[]
        with patch.object(runner,'_call',side_effect=lambda c,**k: commands.append(c) or 'Running as unit'):
            unit,verified=runner._start_guard(self.scope,runner.STATE/'checkpoint11-acceptance')
        self.assertTrue(verified())
        self.assertTrue(unit.startswith('loadmaster-ro-guard-'))
        self.assertEqual(len(commands),2)
        self.assertIn('--lease-seconds', commands[0]);self.assertIn('90',commands[0])
        self.assertFalse(any('ProtectSystem=' in x for x in commands[0]))
        self.assertIn('--rescue', commands[1])
        self.assertIn('--on-active=120s',commands[1])

    def test_state_directory_outside_private_root_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(BackupExecutionError):
                runner._private_folder(Path(td))

class PrepareTests(unittest.TestCase):
    def test_ssd_only_fixture_and_repeat_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);nas=root/'nas'; usb=root/'usb'
            ingest=usb/runner.INGEST[1];ingest.parent.mkdir(parents=True)
            ingest.write_bytes(b'usb-content')
            with patch.object(prepare,'NAS',nas),patch.object(prepare,'USB',usb),\
                 patch.object(prepare,'pinned_spare_identity',return_value=('UUID','SERIAL',True)),\
                 patch.object(prepare.os,'geteuid',return_value=0):
                self.assertEqual(prepare.prepare(write_ssd=False)['state'],'SSD_PREPARE_DRY_RUN')
                self.assertFalse(nas.exists())
                output=prepare.prepare(write_ssd=True)
                self.assertEqual(output['state'],'CHECKPOINT11_SSD_ONLY_PREPARED')
                self.assertEqual((nas/runner.EXPORT[1]).read_bytes(),prepare.PAYLOAD)
                self.assertEqual(ingest.read_bytes(),b'usb-content')
                self.assertEqual(prepare.prepare(write_ssd=True)['state'],'CHECKPOINT11_SSD_ONLY_PREPARED')
                (nas/runner.EXPORT[1]).write_bytes(b'changed')
                with self.assertRaises(BackupExecutionError):
                    prepare.prepare(write_ssd=True)

    def test_existing_ingest_target_refuses_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);nas=root/'nas'; usb=root/'usb'
            ingest=usb/runner.INGEST[1];ingest.parent.mkdir(parents=True)
            ingest.write_bytes(b'usb-content')
            output=nas/runner.INGEST[1];output.parent.mkdir(parents=True)
            output.write_bytes(b'existing-data')
            with patch.object(prepare,'NAS',nas),patch.object(prepare,'USB',usb),\
                 patch.object(prepare,'pinned_spare_identity',return_value=('UUID','SERIAL',True)),\
                 patch.object(prepare.os,'geteuid',return_value=0):
                with self.assertRaises(BackupExecutionError):
                    prepare.prepare(write_ssd=True)
                self.assertEqual(output.read_bytes(),b'existing-data')
                self.assertFalse((nas/runner.EXPORT[1]).exists())

if __name__=='__main__':unittest.main()
