#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
import os
import stat
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("skills/bambu-labs/scripts")

import bambu_lan_print as bambu


def write_gcode(path: Path, body: str = "M104 S220\nM140 S65\nG1 X1 Y1 Z0.2 E0.1\n") -> None:
    path.write_text(body, encoding="utf-8")


def write_sliced_3mf(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("Metadata/plate_1.gcode", "; plate 1\nG1 X1\n")


def write_fake_bambox(path: Path) -> None:
    script = textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import sys
        import zipfile
        from pathlib import Path

        args = sys.argv[1:]
        if args[0] == "pack":
            output = Path(args[args.index("-o") + 1])
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("Metadata/plate_1.gcode", "G1 X1 E0.1\\n")
            print(json.dumps({"packed": str(output)}))
            raise SystemExit(0)
        if args[0] == "validate":
            print(json.dumps({"ok": True}))
            raise SystemExit(0)
        raise SystemExit(2)
        """
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class BambuLanPrintTests(unittest.TestCase):
    def test_new_printer_onboarding_reference_is_linked_and_specific(self) -> None:
        skill_root = repo_path("skills/bambu-labs")
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        onboarding_path = skill_root / "references" / "new-printer-onboarding.md"
        onboarding = onboarding_path.read_text(encoding="utf-8")

        self.assertIn("references/new-printer-onboarding.md", skill_text)
        for required in [
            "Enable LAN Only",
            "Enable Developer Mode",
            "A1 / A1 Mini",
            "P1P / P1S",
            "X1 / X1C / X1E",
            "H2D / Newer Bambu Printers",
            "printer IP address and LAN access code",
        ]:
            with self.subTest(required=required):
                self.assertIn(required, onboarding)

    def test_explicit_print_request_policy_is_documented(self) -> None:
        skill_root = repo_path("skills/bambu-labs")
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        checklist = (skill_root / "references" / "real-printer-checklist.md").read_text(encoding="utf-8")

        self.assertIn("explicit user request to print or start", skill_text)
        self.assertIn("do not pause for a second confirmation", skill_text)
        self.assertIn("live-start authorization for this checklist", checklist)

    def test_default_config_uses_workspace_root_not_skill_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "workspace"
            workspace_root.mkdir()
            with mock.patch.dict(os.environ, {"INIT_CWD": str(workspace_root)}):
                self.assertEqual(workspace_root.resolve(), bambu.default_workspace_root())

        skill_root = repo_path("skills/bambu-labs")
        self.assertNotEqual(skill_root.resolve(), bambu.DEFAULT_CONFIG_PATH.parent)

    def test_inspects_plain_gcode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job.gcode"
            write_gcode(job)

            inspection = bambu.inspect_gcode_file(job)

            self.assertEqual(inspection.size_bytes, job.stat().st_size)
            self.assertRegex(inspection.md5, r"^[0-9a-f]{32}$")
            self.assertEqual(inspection.path, str(job))

    def test_rejects_non_plain_gcode_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.gcode"
            empty = root / "empty.gcode"
            empty.write_text("", encoding="utf-8")
            sliced = root / "job.gcode.3mf"
            write_sliced_3mf(sliced)
            mesh = root / "part.stl"
            mesh.write_text("solid part\nendsolid part\n", encoding="utf-8")

            cases = [
                (missing, "does not exist"),
                (empty, "empty"),
                (sliced, "Expected plain .gcode"),
                (mesh, "Expected a plain .gcode"),
            ]
            for path, message in cases:
                with self.subTest(path=path):
                    with self.assertRaisesRegex(bambu.BambuPrintError, message):
                        bambu.inspect_gcode_file(path)

    def test_plain_send_plan_uses_gcode_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job 01.gcode"
            write_gcode(job)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--host",
                    "192.168.1.50",
                    "--serial",
                    "00M00A000000000",
                    "--action",
                    "upload-start",
                    "--sequence-id",
                    "seq-1",
                    "--remote-name",
                    "job 01.gcode",
                ]
            )

            plan = bambu.build_send_plan(args)

            self.assertTrue(plan["dry_run"])
            self.assertEqual(plan["handoff"], "plain")
            self.assertTrue(plan["ftps"]["will_upload"])
            self.assertTrue(plan["mqtt"]["will_publish"])
            self.assertEqual(plan["ftps"]["remote_path"], "cache/job_01.gcode")
            self.assertEqual(plan["mqtt"]["topic"], "device/00M00A000000000/request")
            payload = plan["mqtt"]["payload"]["print"]
            self.assertEqual(payload["command"], "gcode_file")
            self.assertEqual(payload["param"], "cache/job_01.gcode")
            self.assertEqual(payload["sequence_id"], "seq-1")

    def test_gcode_param_override_is_allowed_for_plain_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job.gcode"
            write_gcode(job)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--host",
                    "192.168.1.50",
                    "--serial",
                    "00M00A000000000",
                    "--gcode-param",
                    "/cache/job.gcode",
                ]
            )

            plan = bambu.build_send_plan(args)

            self.assertEqual(plan["mqtt"]["payload"]["print"]["param"], "/cache/job.gcode")

    def test_config_set_writes_printer_json_without_echoing_access_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "printers.json"
            args = bambu.parse_args(
                [
                    "config",
                    "--config",
                    str(config),
                    "set",
                    "--printer",
                    "a1-mini",
                    "--host",
                    "192.168.1.34",
                    "--access-code",
                    "12345678",
                    "--model",
                    "a1-mini",
                    "--serial",
                    "0309CA4C0901107",
                ]
            )

            with mock.patch("builtins.print") as mocked_print:
                code = bambu.config_set_main(args)

            self.assertEqual(code, 0)
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(data["printers"]["a1-mini"]["access_code"], "12345678")
            payload = json.loads(mocked_print.call_args.args[0])
            self.assertEqual(payload["entry"]["host"], "192.168.1.34")
            self.assertNotIn("access_code", payload["entry"])

    def test_send_parser_loads_printer_defaults_from_json_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job.gcode"
            config = root / "printers.json"
            write_gcode(job)
            config.write_text(
                json.dumps(
                    {
                        "printers": {
                            "a1-mini": {
                                "host": "192.168.1.34",
                                "access_code": "12345678",
                                "serial": "0309CA4C0901107",
                                "model": "a1-mini",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            args = bambu.parse_args(["send", "--config", str(config), "--printer", "a1-mini", "--gcode", str(job)])
            plan = bambu.build_send_plan(args)

            self.assertEqual(args.host, "192.168.1.34")
            self.assertEqual(args.serial, "0309CA4C0901107")
            self.assertEqual(bambu.access_code_from_args(args), "12345678")
            self.assertEqual(plan["mqtt"]["topic"], "device/0309CA4C0901107/request")

    def test_dry_run_send_plan_does_not_discover_serial_when_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job.gcode"
            config = root / "printers.json"
            write_gcode(job)
            config.write_text(
                json.dumps({"printers": {"a1-mini": {"host": "192.168.1.34", "access_code": "12345678"}}}),
                encoding="utf-8",
            )
            args = bambu.parse_args(
                [
                    "send",
                    "--config",
                    str(config),
                    "--printer",
                    "a1-mini",
                    "--gcode",
                    str(job),
                    "--action",
                    "upload-start",
                ]
            )

            with mock.patch.object(
                bambu,
                "discover_printer_serial",
                side_effect=AssertionError("dry-run plans must not perform network discovery"),
            ) as mocked_discover:
                plan = bambu.build_send_plan(args)

            mocked_discover.assert_not_called()
            self.assertEqual(args.serial, "")
            self.assertIsNone(plan["mqtt"]["topic"])
            cached = json.loads(config.read_text(encoding="utf-8"))
            self.assertNotIn("serial", cached["printers"]["a1-mini"])

    def test_execute_send_discovers_serial_from_printer_certificate_when_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job.gcode"
            config = root / "printers.json"
            write_gcode(job)
            config.write_text(
                json.dumps({"printers": {"a1-mini": {"host": "192.168.1.34", "access_code": "12345678"}}}),
                encoding="utf-8",
            )
            args = bambu.parse_args(
                [
                    "send",
                    "--config",
                    str(config),
                    "--printer",
                    "a1-mini",
                    "--gcode",
                    str(job),
                    "--action",
                    "upload-start",
                    "--execute",
                    "--confirm-start-print",
                ]
            )

            with (
                mock.patch.object(bambu, "discover_printer_serial", return_value="0309CA4C0901107") as mocked_discover,
                mock.patch.object(bambu, "upload_ftps") as mocked_upload,
                mock.patch.object(bambu, "publish_mqtt") as mocked_publish,
                mock.patch("builtins.print") as mocked_print,
            ):
                code = bambu.send_main(args)

            self.assertEqual(code, 0)
            mocked_discover.assert_called_once()
            mocked_upload.assert_called_once()
            mocked_publish.assert_called_once()
            self.assertEqual(args.serial, "0309CA4C0901107")
            payload = json.loads(mocked_print.call_args.args[0])
            self.assertEqual(payload["mqtt"]["topic"], "device/0309CA4C0901107/request")
            cached = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(cached["printers"]["a1-mini"]["serial"], "0309CA4C0901107")

    def test_serial_command_reports_tls_certificate_serial(self) -> None:
        args = bambu.parse_args(["serial", "--host", "192.168.1.34", "--json"])

        with mock.patch.object(bambu, "discover_printer_serial", return_value="0309CA4C0901107"), mock.patch(
            "builtins.print"
        ) as mocked_print:
            code = bambu.serial_main(args)

        self.assertEqual(code, 0)
        payload = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(payload["serial"], "0309CA4C0901107")
        self.assertEqual(payload["source"], "printer_tls_certificate_common_name")

    def test_bambox_project_refuses_unsupported_a1_mini_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job.gcode"
            write_gcode(job)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--handoff",
                    "bambox-project",
                    "--bambox-profile",
                    "a1-mini-0.4",
                    "--filament",
                    "PLA",
                ]
            )

            with self.assertRaisesRegex(bambu.BambuPrintError, "a1-mini-0.4 is not enabled"):
                bambu.build_send_plan(args)

    def test_bambox_project_builds_pack_command_without_running_bambox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job.gcode"
            write_gcode(job)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--handoff",
                    "bambox-project",
                    "--bambox-profile",
                    "p1s-0.4",
                    "--filament",
                    "PLA",
                    "--bambox-bin",
                    "/usr/local/bin/bambox",
                    "--action",
                    "upload-start",
                ]
            )

            plan = bambu.build_send_plan(args)

            command = plan["input"]["bambox"]["pack_command"]
            self.assertEqual(command[:3], ["/usr/local/bin/bambox", "pack", str(job.resolve())])
            self.assertIn("-m", command)
            self.assertIn("p1s", command)
            self.assertIn("--nozzle-diameter", command)
            self.assertIn("0.4", command)
            self.assertIn("-f", command)
            self.assertIn("PLA", command)
            self.assertEqual(plan["mqtt"]["payload"]["print"]["command"], "project_file")
            self.assertIsNone(plan["mqtt"]["payload"]["print"]["md5"])
            self.assertEqual(plan["mqtt"]["payload"]["print"]["subtask_name"], "job")
            self.assertTrue(plan["mqtt"]["payload"]["print"]["bed_levelling"])
            self.assertFalse(plan["mqtt"]["payload"]["print"]["use_ams"])
            self.assertEqual(plan["ftps"]["remote_path"], "job.gcode.3mf")
            self.assertEqual(plan["ftps"]["url"], "ftp:///job.gcode.3mf")

    def test_package_execute_uses_fake_bambox_and_validates_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job.gcode"
            output = root / "job.gcode.3mf"
            fake_bambox = root / "bambox"
            write_gcode(job)
            write_fake_bambox(fake_bambox)
            args = bambu.parse_args(
                [
                    "package",
                    "--gcode",
                    str(job),
                    "--output",
                    str(output),
                    "--bambox-profile",
                    "p1s-0.4",
                    "--filament",
                    "PLA",
                    "--bambox-bin",
                    str(fake_bambox),
                    "--execute",
                ]
            )

            with mock.patch("builtins.print") as mocked_print:
                code = bambu.package_main(args)

            self.assertEqual(code, 0)
            self.assertTrue(output.exists())
            payload = json.loads(mocked_print.call_args.args[0])
            self.assertEqual(payload["executed"], ["bambox_pack", "bambox_validate"])
            self.assertEqual(payload["result"]["project"]["plates"][0]["path"], "Metadata/plate_1.gcode")

    def test_template_project_pack_replaces_plate_gcode_and_md5(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job.gcode"
            template = root / "template.gcode.3mf"
            output = root / "job.gcode.3mf"
            write_gcode(job, "M104 S220\nM140 S65\nG1 X2 Y2 Z0.2 E0.2\n")
            write_sliced_3mf(template)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--handoff",
                    "template-project",
                    "--template-project",
                    str(template),
                ]
            )

            result = bambu.package_with_template_project(args, output)

            self.assertEqual(result["pack"]["replaced_plate"], "Metadata/plate_1.gcode")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read("Metadata/plate_1.gcode"), job.read_bytes())
                self.assertEqual(
                    archive.read("Metadata/plate_1.gcode.md5").decode("ascii"),
                    hashlib.md5(job.read_bytes()).hexdigest().upper(),
                )

    def test_template_project_upload_start_execute_uses_root_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job.gcode"
            template = root / "template.gcode.3mf"
            write_gcode(job)
            write_sliced_3mf(template)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--handoff",
                    "template-project",
                    "--template-project",
                    str(template),
                    "--host",
                    "192.168.1.50",
                    "--serial",
                    "00M00A000000000",
                    "--access-code",
                    "12345678",
                    "--action",
                    "upload-start",
                    "--execute",
                    "--confirm-start-print",
                ]
            )

            with (
                mock.patch.object(bambu, "upload_ftps") as mocked_upload,
                mock.patch.object(bambu, "publish_mqtt") as mocked_publish,
                mock.patch("builtins.print") as mocked_print,
            ):
                code = bambu.send_main(args)

            self.assertEqual(code, 0)
            mocked_upload.assert_called_once()
            self.assertEqual(mocked_upload.call_args.args[2], "job.gcode.3mf")
            mocked_publish.assert_called_once()
            payload = json.loads(mocked_print.call_args.args[0])
            self.assertEqual(payload["handoff"], "template-project")
            self.assertEqual(payload["ftps"]["remote_path"], "job.gcode.3mf")
            self.assertEqual(payload["ftps"]["url"], "ftp:///job.gcode.3mf")
            self.assertEqual(payload["mqtt"]["payload"]["print"]["command"], "project_file")
            self.assertEqual(payload["mqtt"]["payload"]["print"]["url"], "ftp:///job.gcode.3mf")
            self.assertEqual(payload["mqtt"]["payload"]["print"]["subtask_name"], "job")
            self.assertTrue(payload["mqtt"]["payload"]["print"]["flow_cali"])
            self.assertRegex(payload["mqtt"]["payload"]["print"]["md5"], r"^[0-9A-F]{32}$")

    def test_bambox_upload_start_execute_packages_then_uses_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job.gcode"
            fake_bambox = root / "bambox"
            write_gcode(job)
            write_fake_bambox(fake_bambox)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--handoff",
                    "bambox-project",
                    "--bambox-profile",
                    "p1s-0.4",
                    "--filament",
                    "PLA",
                    "--bambox-bin",
                    str(fake_bambox),
                    "--host",
                    "192.168.1.50",
                    "--serial",
                    "00M00A000000000",
                    "--access-code",
                    "12345678",
                    "--action",
                    "upload-start",
                    "--execute",
                    "--confirm-start-print",
                ]
            )

            with (
                mock.patch.object(bambu, "upload_ftps") as mocked_upload,
                mock.patch.object(bambu, "publish_mqtt") as mocked_publish,
                mock.patch("builtins.print") as mocked_print,
            ):
                code = bambu.send_main(args)

            self.assertEqual(code, 0)
            mocked_upload.assert_called_once()
            mocked_publish.assert_called_once()
            payload = json.loads(mocked_print.call_args.args[0])
            self.assertEqual(payload["executed"], ["upload", "publish_start_request"])
            self.assertEqual(payload["mqtt"]["payload"]["print"]["command"], "project_file")
            self.assertEqual(payload["mqtt"]["payload"]["print"]["param"], "Metadata/plate_1.gcode")
            self.assertEqual(payload["mqtt"]["payload"]["print"]["url"], "ftp:///job.gcode.3mf")
            self.assertEqual(payload["mqtt"]["payload"]["print"]["subtask_name"], "job")
            self.assertRegex(payload["mqtt"]["payload"]["print"]["md5"], r"^[0-9A-F]{32}$")

    def test_implicit_ftps_reuses_control_tls_session_for_data_connection(self) -> None:
        context = mock.Mock()
        control_socket = mock.Mock()
        control_socket.session = "session-token"
        data_socket = mock.Mock()
        wrapped_data_socket = mock.Mock()
        context.wrap_socket.return_value = wrapped_data_socket
        ftp = bambu.ImplicitFTP_TLS(context=context)
        ftp.sock = control_socket
        ftp.host = "printer.local"
        ftp._prot_p = True

        with mock.patch.object(bambu.ftplib.FTP, "ntransfercmd", return_value=(data_socket, 123)):
            conn, size = ftp.ntransfercmd("STOR job.gcode")

        self.assertIs(conn, wrapped_data_socket)
        self.assertEqual(size, 123)
        context.wrap_socket.assert_called_once_with(
            data_socket,
            server_hostname="printer.local",
            session="session-token",
        )

    def test_ftps_upload_accepts_timeout_when_control_channel_confirms_completion(self) -> None:
        ftp = mock.Mock()
        ftp.storbinary.side_effect = bambu.socket.timeout("data channel shutdown timed out")
        ftp.voidresp.return_value = "226 Transfer complete"

        bambu.storbinary_with_bambu_timeout_tolerance(ftp, "STOR job.gcode", mock.Mock())

        ftp.storbinary.assert_called_once()
        ftp.voidresp.assert_called_once()

    def test_start_execute_requires_confirmation_before_network_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job.gcode"
            write_gcode(job)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--host",
                    "192.168.1.50",
                    "--serial",
                    "00M00A000000000",
                    "--action",
                    "start",
                    "--execute",
                ]
            )

            with self.assertRaisesRegex(bambu.BambuPrintError, "confirm-start-print"):
                bambu.send_main(args)

    def test_validate_local_host_accepts_hostname_resolving_to_private_address(self) -> None:
        with mock.patch.object(
            bambu.socket,
            "getaddrinfo",
            return_value=[
                (
                    bambu.socket.AF_INET,
                    bambu.socket.SOCK_STREAM,
                    0,
                    "",
                    ("192.168.1.50", 0),
                )
            ],
        ):
            bambu.validate_local_host("printer.local", allow_nonprivate=False)

    def test_validate_local_host_rejects_hostname_resolving_to_public_address(self) -> None:
        with mock.patch.object(
            bambu.socket,
            "getaddrinfo",
            return_value=[
                (
                    bambu.socket.AF_INET,
                    bambu.socket.SOCK_STREAM,
                    0,
                    "",
                    ("8.8.8.8", 0),
                )
            ],
        ):
            with self.assertRaisesRegex(bambu.BambuPrintError, "non-private"):
                bambu.validate_local_host("printer.example.com", allow_nonprivate=False)

    def test_validate_local_host_does_not_resolve_when_nonprivate_hosts_are_allowed(self) -> None:
        with mock.patch.object(bambu.socket, "getaddrinfo") as mocked_getaddrinfo:
            bambu.validate_local_host("printer.example.com", allow_nonprivate=True)

        mocked_getaddrinfo.assert_not_called()

    def test_validate_local_host_rejects_literal_public_address(self) -> None:
        with self.assertRaisesRegex(bambu.BambuPrintError, "non-private"):
            bambu.validate_local_host("8.8.8.8", allow_nonprivate=False)

    def test_upload_start_reports_published_start_request_not_confirmed_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job.gcode"
            write_gcode(job)
            args = bambu.parse_args(
                [
                    "send",
                    "--gcode",
                    str(job),
                    "--host",
                    "192.168.1.50",
                    "--serial",
                    "00M00A000000000",
                    "--access-code",
                    "12345678",
                    "--action",
                    "upload-start",
                    "--execute",
                    "--confirm-start-print",
                ]
            )

            with (
                mock.patch.object(bambu, "upload_ftps") as mocked_upload,
                mock.patch.object(bambu, "publish_mqtt") as mocked_publish,
                mock.patch("builtins.print") as mocked_print,
            ):
                code = bambu.send_main(args)

        self.assertEqual(code, 0)
        mocked_upload.assert_called_once()
        mocked_publish.assert_called_once()
        payload = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(payload["executed"], ["upload", "publish_start_request"])
        self.assertEqual(payload["mqtt"]["payload"]["print"]["command"], "gcode_file")
        self.assertIn("does not confirm printer acceptance", payload["execution_notes"][0])

    def test_mqtt_client_id_defaults_to_serial(self) -> None:
        args = mock.Mock()
        args.access_code = "12345678"
        args.host = "192.168.1.50"
        args.mqtt_port = 8883
        args.timeout = 20.0
        args.tls_verify = False
        args.allow_nonprivate_host = True
        args.client_id = ""
        args.serial = "00M00A000000000"
        sent = bytearray()
        connack = bytearray(b"\x20\x02\x00\x00")

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def sendall(self, data):
                sent.extend(data)

            def recv(self, size):
                chunk = bytes(connack[:size])
                del connack[:size]
                return chunk

        fake_context = mock.Mock()
        fake_context.wrap_socket.return_value = FakeSocket()
        with (
            mock.patch.object(bambu.ssl, "create_default_context", return_value=fake_context),
            mock.patch.object(bambu.socket, "create_connection", return_value=FakeSocket()),
        ):
            bambu.publish_mqtt(args, "device/00M00A000000000/request", {"print": {}})

        self.assertIn(b"00M00A000000000", bytes(sent))

    def test_mqtt_qos1_publish_waits_for_puback(self) -> None:
        args = mock.Mock()
        args.access_code = "12345678"
        args.host = "192.168.1.50"
        args.mqtt_port = 8883
        args.timeout = 20.0
        args.tls_verify = False
        args.allow_nonprivate_host = True
        args.client_id = ""
        args.serial = "00M00A000000000"
        args.mqtt_qos = 1
        args.wait_after_publish = 0.0
        sent = bytearray()
        incoming = bytearray(b"\x20\x02\x00\x00\x40\x02\x00\x02")

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def sendall(self, data):
                sent.extend(data)

            def recv(self, size):
                chunk = bytes(incoming[:size])
                del incoming[:size]
                return chunk

            def settimeout(self, timeout):
                self.timeout = timeout

        fake_context = mock.Mock()
        fake_context.wrap_socket.return_value = FakeSocket()
        with (
            mock.patch.object(bambu.ssl, "create_default_context", return_value=fake_context),
            mock.patch.object(bambu.socket, "create_connection", return_value=FakeSocket()),
        ):
            result = bambu.publish_mqtt(args, "device/00M00A000000000/request", {"print": {}})

        self.assertTrue(result["puback_received"])
        self.assertIn(b"\x32", bytes(sent))

    def test_mqtt_packet_encoding(self) -> None:
        self.assertEqual(bambu.encode_remaining_length(0), b"\x00")
        self.assertEqual(bambu.encode_remaining_length(321), b"\xc1\x02")
        packet = bambu.mqtt_publish_packet("device/abc/request", json.dumps({"print": {}}).encode())
        self.assertEqual(packet[0], 0x30)
        self.assertIn(b"device/abc/request", packet)
        qos_packet = bambu.mqtt_publish_packet(
            "device/abc/request",
            json.dumps({"print": {}}).encode(),
            qos=1,
            packet_id=7,
        )
        self.assertEqual(qos_packet[0], 0x32)
        self.assertIn(b"\x00\x07", qos_packet)
        subscribe = bambu.mqtt_subscribe_packet(1, "device/abc/report")
        self.assertEqual(subscribe[0], 0x82)
        self.assertIn(b"device/abc/report", subscribe)

    def test_status_command_uses_configured_printer_report_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "printers.json"
            config.write_text(
                json.dumps(
                    {
                        "printers": {
                            "a1-mini": {
                                "host": "192.168.1.34",
                                "access_code": "12345678",
                                "serial": "0309CA4C0901107",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            args = bambu.parse_args(["status", "--config", str(config), "--printer", "a1-mini", "--wait-seconds", "0.1"])

            with mock.patch.object(
                bambu,
                "subscribe_mqtt_reports",
                return_value=[{"topic": "device/0309CA4C0901107/report", "json": {"print": {"gcode_state": "RUNNING"}}}],
            ) as mocked_status, mock.patch("builtins.print") as mocked_print:
                code = bambu.status_main(args)

        self.assertEqual(code, 0)
        mocked_status.assert_called_once()
        self.assertEqual(mocked_status.call_args.args[1], "device/0309CA4C0901107/report")
        payload = json.loads(mocked_print.call_args.args[0])
        self.assertTrue(payload["ok"])

    def test_clear_error_dry_run_builds_clean_print_error_payload(self) -> None:
        args = bambu.parse_args(
            [
                "clear-error",
                "--host",
                "192.168.1.50",
                "--serial",
                "00M00A000000000",
                "--sequence-id",
                "seq-1",
            ]
        )

        plan = bambu.build_clear_error_plan(args)

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["mqtt"]["topic"], "device/00M00A000000000/request")
        self.assertEqual(plan["mqtt"]["payload"]["print"]["command"], "clean_print_error")
        self.assertEqual(plan["mqtt"]["payload"]["print"]["sequence_id"], "seq-1")

    def test_clear_error_execute_publishes_without_start_confirmation(self) -> None:
        args = bambu.parse_args(
            [
                "clear-error",
                "--host",
                "192.168.1.50",
                "--serial",
                "00M00A000000000",
                "--access-code",
                "12345678",
                "--execute",
            ]
        )

        with mock.patch.object(bambu, "publish_mqtt", return_value={"puback_received": True}) as mocked_publish, mock.patch(
            "builtins.print"
        ) as mocked_print:
            code = bambu.clear_error_main(args)

        self.assertEqual(code, 0)
        mocked_publish.assert_called_once()
        payload = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(payload["executed"], ["publish_clean_print_error"])
        self.assertEqual(payload["mqtt"]["payload"]["print"]["command"], "clean_print_error")

    def test_pause_dry_run_builds_pause_payload(self) -> None:
        args = bambu.parse_args(
            [
                "pause",
                "--host",
                "192.168.1.50",
                "--serial",
                "00M00A000000000",
                "--sequence-id",
                "seq-1",
            ]
        )

        plan = bambu.build_print_control_plan(args)

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["action"], "pause")
        self.assertEqual(plan["mqtt"]["topic"], "device/00M00A000000000/request")
        self.assertFalse(plan["mqtt"]["will_publish"])
        payload = plan["mqtt"]["payload"]["print"]
        self.assertEqual(payload["command"], "pause")
        self.assertEqual(payload["sequence_id"], "seq-1")

    def test_cancel_dry_run_maps_to_bambu_stop_payload(self) -> None:
        args = bambu.parse_args(
            [
                "cancel",
                "--host",
                "192.168.1.50",
                "--serial",
                "00M00A000000000",
                "--sequence-id",
                "seq-2",
            ]
        )

        plan = bambu.build_print_control_plan(args)

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["action"], "cancel")
        payload = plan["mqtt"]["payload"]["print"]
        self.assertEqual(payload["command"], "stop")
        self.assertEqual(payload["param"], "")
        self.assertEqual(payload["sequence_id"], "seq-2")

    def test_cancel_execute_requires_cancel_confirmation(self) -> None:
        args = bambu.parse_args(
            [
                "cancel",
                "--host",
                "192.168.1.50",
                "--serial",
                "00M00A000000000",
                "--access-code",
                "12345678",
                "--execute",
            ]
        )

        with self.assertRaisesRegex(bambu.BambuPrintError, "--confirm-cancel-print"):
            bambu.print_control_main(args)

    def test_cancel_execute_publishes_stop_after_confirmation(self) -> None:
        args = bambu.parse_args(
            [
                "cancel",
                "--host",
                "192.168.1.50",
                "--serial",
                "00M00A000000000",
                "--access-code",
                "12345678",
                "--execute",
                "--confirm-cancel-print",
            ]
        )

        with mock.patch.object(bambu, "publish_mqtt", return_value={"puback_received": True}) as mocked_publish, mock.patch(
            "builtins.print"
        ) as mocked_print:
            code = bambu.print_control_main(args)

        self.assertEqual(code, 0)
        mocked_publish.assert_called_once()
        payload = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(payload["executed"], ["publish_cancel_request"])
        self.assertEqual(payload["mqtt"]["payload"]["print"]["command"], "stop")

    def test_formats_hms_codes_from_status_payload(self) -> None:
        message = {"json": {"print": {"hms": [{"attr": 83887360, "code": 65543, "action": 0}]}}}

        bambu.annotate_hms_codes(message)

        self.assertEqual(message["hms"][0]["hms_code"], "0500-0500-0001-0007")


if __name__ == "__main__":
    unittest.main()
