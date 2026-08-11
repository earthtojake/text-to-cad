#!/usr/bin/env python3
"""Dry-run-first helpers for local Bambu Lab print workflows.

The default behavior is non-networked. Start from a validated plain .gcode file,
then either upload/start it directly with the printer's gcode_file command or,
for explicitly supported printer profiles, package it with bambox into a
.gcode.3mf project and start that with project_file.
"""

from __future__ import annotations

import argparse
import ftplib
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Union


BAMBU_USERNAME = "bblp"
DEFAULT_FTPS_PORT = 990
DEFAULT_MQTT_PORT = 8883
DEFAULT_REMOTE_DIR = "cache"
PLATE_RE = re.compile(r"^Metadata/plate_(\d+)\.gcode$")
IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def default_workspace_root() -> Path:
    init_cwd = str(os.environ.get("INIT_CWD") or "").strip()
    return Path(init_cwd).expanduser().resolve() if init_cwd else Path.cwd().resolve()


DEFAULT_CONFIG_PATH = default_workspace_root() / "bambu-printers.json"


class BambuPrintError(RuntimeError):
    """Raised for expected user-facing workflow errors."""


@dataclass(frozen=True)
class GCodeInspection:
    path: str
    size_bytes: int
    md5: str


@dataclass(frozen=True)
class PlateInfo:
    index: int
    path: str
    size_bytes: int


@dataclass(frozen=True)
class ProjectInspection:
    path: str
    size_bytes: int
    md5: str
    plates: list[PlateInfo]


@dataclass(frozen=True)
class BamboxProfile:
    key: str
    machine: str
    nozzle_diameter: str
    enabled: bool
    reason: str
    allowed_filaments: set[str]


BAMBOX_PROFILES: dict[str, BamboxProfile] = {
    "p1s-0.4": BamboxProfile(
        key="p1s-0.4",
        machine="p1s",
        nozzle_diameter="0.4",
        enabled=True,
        reason="bambox 0.5.0 bundles and hardware-validates the Bambu Lab P1S 0.4 profile.",
        allowed_filaments={"PLA", "ASA", "PETG-CF"},
    ),
    "a1-mini-0.4": BamboxProfile(
        key="a1-mini-0.4",
        machine="a1-mini",
        nozzle_diameter="0.4",
        enabled=False,
        reason="no validated bambox A1 Mini profile is present.",
        allowed_filaments=set(),
    ),
    "a1-0.4": BamboxProfile(
        key="a1-0.4",
        machine="a1",
        nozzle_diameter="0.4",
        enabled=False,
        reason="no validated bambox A1 profile is present.",
        allowed_filaments=set(),
    ),
    "x1c-0.4": BamboxProfile(
        key="x1c-0.4",
        machine="x1c",
        nozzle_diameter="0.4",
        enabled=False,
        reason="no validated bambox X1C profile is present.",
        allowed_filaments=set(),
    ),
    "p1p-0.4": BamboxProfile(
        key="p1p-0.4",
        machine="p1p",
        nozzle_diameter="0.4",
        enabled=False,
        reason="no validated bambox P1P profile is present.",
        allowed_filaments=set(),
    ),
}


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS variant for implicit FTPS servers such as Bambu printers."""

    def connect(self, host: str = "", port: int = 0, timeout: float | None = -999, source_address=None):
        if host:
            self.host = host
        if port:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        if source_address is not None:
            self.source_address = source_address
        raw_sock = socket.create_connection(
            (self.host, self.port),
            self.timeout,
            source_address=self.source_address,
        )
        self.af = raw_sock.family
        self.sock = self.context.wrap_socket(raw_sock, server_hostname=self.host)
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd: str, rest: Any = None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


def config_path_from_args(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "config", None) or DEFAULT_CONFIG_PATH).expanduser().resolve()


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"printers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BambuPrintError(f"Printer config is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BambuPrintError(f"Printer config must be a JSON object: {path}")
    printers = data.setdefault("printers", {})
    if not isinstance(printers, dict):
        raise BambuPrintError("Printer config field printers must be an object.")
    return data


def save_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sanitized_printer_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if key != "access_code"}


def printer_entry(data: dict[str, Any], printer_id: str) -> dict[str, Any]:
    printers = data.get("printers", {})
    entry = printers.get(printer_id)
    if not isinstance(entry, dict):
        known = ", ".join(sorted(printers)) or "<none>"
        raise BambuPrintError(f"Printer {printer_id!r} is not configured. Known printers: {known}")
    return entry


def apply_printer_config(args: argparse.Namespace) -> None:
    printer_id = getattr(args, "printer", "") or ""
    if not printer_id:
        return
    data = load_config(config_path_from_args(args))
    entry = printer_entry(data, printer_id)
    for attr, key in (
        ("host", "host"),
        ("access_code", "access_code"),
        ("serial", "serial"),
        ("model", "model"),
    ):
        if hasattr(args, attr) and not getattr(args, attr, "") and entry.get(key):
            setattr(args, attr, str(entry[key]))


def cache_printer_serial(args: argparse.Namespace, serial: str) -> None:
    printer_id = getattr(args, "printer", "") or ""
    if not printer_id:
        return
    path = config_path_from_args(args)
    data = load_config(path)
    entry = printer_entry(data, printer_id)
    if entry.get("serial") == serial:
        return
    entry["serial"] = serial
    entry["serial_source"] = "printer_tls_certificate_common_name"
    entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_config(path, data)


def md5_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.md5()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def inspect_gcode_file(path: Path) -> GCodeInspection:
    if not path.is_file():
        raise BambuPrintError(f"G-code input file does not exist: {path}")
    name = path.name.lower()
    if name.endswith(".gcode.3mf") or path.suffix.lower() == ".3mf":
        raise BambuPrintError("Expected plain .gcode, not a Bambu .gcode.3mf or .3mf archive.")
    if path.suffix.lower() != ".gcode":
        raise BambuPrintError(f"Expected a plain .gcode input, got: {path.name}")
    md5, size = md5_and_size(path)
    if size == 0:
        raise BambuPrintError(f"G-code input is empty: {path}")
    return GCodeInspection(path=str(path), size_bytes=size, md5=md5)


def inspect_sliced_3mf(path: Path) -> ProjectInspection:
    if not path.is_file():
        raise BambuPrintError(f"Packaged project file does not exist: {path}")

    md5, size = md5_and_size(path)
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise BambuPrintError(f"Packaged project is not a readable 3MF/ZIP archive: {path}") from exc

    plates: list[PlateInfo] = []
    with archive:
        for info in archive.infolist():
            match = PLATE_RE.match(info.filename)
            if match:
                plates.append(
                    PlateInfo(
                        index=int(match.group(1)),
                        path=info.filename,
                        size_bytes=info.file_size,
                    )
                )

    if not plates:
        raise BambuPrintError("Packaged project has no Metadata/plate_N.gcode entries.")

    plates.sort(key=lambda item: item.index)
    return ProjectInspection(path=str(path), size_bytes=size, md5=md5, plates=plates)


def sanitize_remote_name(name: str) -> str:
    base = Path(name).name.strip()
    if not base:
        raise BambuPrintError("Remote filename cannot be empty.")
    return re.sub(r"[^A-Za-z0-9._+-]", "_", base)


def join_remote_path(remote_dir: str, remote_name: str) -> str:
    clean_dir = remote_dir.strip("/")
    clean_name = sanitize_remote_name(remote_name)
    return f"{clean_dir}/{clean_name}" if clean_dir else clean_name


def default_project_name(gcode_path: Path) -> str:
    if gcode_path.name.lower().endswith(".gcode"):
        return f"{gcode_path.name}.3mf"
    return f"{gcode_path.name}.gcode.3mf"


def project_subtask_name(remote_path: str) -> str:
    name = Path(remote_path).name
    for suffix in (".gcode.3mf", ".3mf", ".gcode"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name or "local_print"


def is_local_address(address: IPAddress) -> bool:
    return address.is_private or address.is_loopback or address.is_link_local


def resolve_host_addresses(host: str) -> list[IPAddress]:
    clean_host = host.strip("[]")
    try:
        return [ipaddress.ip_address(clean_host)]
    except ValueError:
        pass

    try:
        results = socket.getaddrinfo(clean_host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BambuPrintError(f"Could not resolve printer host {host!r}: {exc}") from exc

    addresses = sorted({ipaddress.ip_address(item[4][0]) for item in results}, key=str)
    if not addresses:
        raise BambuPrintError(f"Could not resolve printer host {host!r}.")
    return addresses


def validate_local_host(host: str, allow_nonprivate: bool) -> None:
    if not host:
        raise BambuPrintError("Printer host/IP is required for network actions.")
    if allow_nonprivate:
        return

    addresses = resolve_host_addresses(host)
    nonprivate = [str(address) for address in addresses if not is_local_address(address)]
    if nonprivate:
        raise BambuPrintError(
            f"{host} resolves to non-private address(es): {', '.join(nonprivate)}. "
            "Refusing unless --allow-nonprivate-host is set."
        )


def common_name_from_decoded_cert(decoded: dict[str, Any]) -> str:
    for subject_item in decoded.get("subject", ()):
        for key, value in subject_item:
            if key == "commonName":
                return str(value)
    return ""


def decode_der_certificate(der_cert: bytes) -> dict[str, Any]:
    pem = ssl.DER_cert_to_PEM_cert(der_cert)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".pem", delete=False) as handle:
            temp_path = handle.name
            handle.write(pem)
        return ssl._ssl._test_decode_cert(temp_path)  # type: ignore[attr-defined]
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink()
            except FileNotFoundError:
                pass


def discover_printer_serial(
    *,
    host: str,
    port: int = DEFAULT_MQTT_PORT,
    timeout: float = 20.0,
    tls_verify: bool = False,
    allow_nonprivate_host: bool = False,
) -> str:
    validate_local_host(host, allow_nonprivate_host)
    context = ssl.create_default_context()
    if not tls_verify:
        # Bambu printer firmware serves self-signed LAN certificates; validate_local_host()
        # above restricts this to private/loopback/link-local hosts, so disabling verification
        # here only trusts the printer's subnet, not its actual certificate.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as raw_sock:
        with context.wrap_socket(raw_sock, server_hostname=host) as sock:
            der_cert = sock.getpeercert(binary_form=True)
    if not der_cert:
        raise BambuPrintError("Printer did not provide a TLS certificate for serial discovery.")
    serial = common_name_from_decoded_cert(decode_der_certificate(der_cert)).strip()
    if not serial:
        raise BambuPrintError("Could not find printer serial in the local TLS certificate common name.")
    return serial


def ensure_printer_serial(args: argparse.Namespace) -> str:
    if getattr(args, "serial", ""):
        return args.serial
    if not getattr(args, "host", ""):
        return ""
    args.serial = discover_printer_serial(
        host=args.host,
        port=args.mqtt_port,
        timeout=args.timeout,
        tls_verify=args.tls_verify,
        allow_nonprivate_host=args.allow_nonprivate_host,
    )
    cache_printer_serial(args, args.serial)
    return args.serial


def selected_plate(inspection: ProjectInspection, requested: int | None) -> PlateInfo:
    if requested is None:
        return inspection.plates[0]
    for plate in inspection.plates:
        if plate.index == requested:
            return plate
    available = ", ".join(str(plate.index) for plate in inspection.plates)
    raise BambuPrintError(f"Plate {requested} not found. Available plates: {available}")


def sequence_id(value: str | None) -> str:
    if value:
        return value
    return str(int(time.time() * 1000))


def build_gcode_file_payload(*, remote_path: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "print": {
            "sequence_id": sequence_id(args.sequence_id),
            "command": "gcode_file",
            "param": args.gcode_param or remote_path,
        }
    }


def build_clean_print_error_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "print": {
            "sequence_id": sequence_id(args.sequence_id),
            "command": "clean_print_error",
        }
    }


def build_print_control_payload(args: argparse.Namespace) -> dict[str, Any]:
    command = "stop" if args.action == "cancel" else args.action
    payload = {
        "print": {
            "sequence_id": sequence_id(args.sequence_id),
            "command": command,
        }
    }
    if command == "stop":
        payload["print"]["param"] = ""
    return payload


def build_project_file_payload(
    *,
    plate: PlateInfo,
    remote_path: str,
    remote_url: str,
    md5: str | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "print": {
            "sequence_id": sequence_id(args.sequence_id),
            "command": "project_file",
            "param": plate.path,
            "project_id": "0",
            "profile_id": "0",
            "task_id": "0",
            "subtask_id": "0",
            "subtask_name": project_subtask_name(remote_path),
            "url": remote_url,
            "md5": md5.upper() if md5 else None,
            "timelapse": False,
            "bed_type": "auto",
            "bed_levelling": True,
            "flow_cali": True,
            "vibration_cali": False,
            "layer_inspect": True,
            "use_ams": False,
            "ams_mapping": "",
        }
    }


def bambox_profile(profile_key: str) -> BamboxProfile:
    try:
        profile = BAMBOX_PROFILES[profile_key]
    except KeyError as exc:
        known = ", ".join(sorted(BAMBOX_PROFILES))
        raise BambuPrintError(f"Unknown bambox profile {profile_key!r}. Known profiles: {known}") from exc
    if not profile.enabled:
        raise BambuPrintError(f"{profile.key} is not enabled because {profile.reason}")
    return profile


def bambox_profile_payload(profile: BamboxProfile) -> dict[str, Any]:
    return {
        "key": profile.key,
        "machine": profile.machine,
        "nozzle_diameter": profile.nozzle_diameter,
        "enabled": profile.enabled,
        "reason": profile.reason,
        "allowed_filaments": sorted(profile.allowed_filaments),
    }


def bambox_filament_type(spec: str) -> str:
    parts = spec.split(":")
    if len(parts) >= 2 and parts[0].isdigit():
        value = parts[1]
    else:
        value = parts[0]
    return value.strip().upper()


def validate_bambox_filaments(profile: BamboxProfile, filaments: list[str] | None) -> list[str]:
    if not filaments:
        raise BambuPrintError("At least one --filament is required for bambox packaging.")
    for spec in filaments:
        filament_type = bambox_filament_type(spec)
        if filament_type not in profile.allowed_filaments:
            allowed = ", ".join(sorted(profile.allowed_filaments))
            raise BambuPrintError(
                f"Filament {filament_type!r} is not enabled for {profile.key}. Allowed filaments: {allowed}"
            )
    return filaments


def resolve_bambox_bin(requested: str | None, *, require_exists: bool) -> str:
    candidate = requested or os.environ.get("BAMBOX_BIN") or "bambox"
    if not require_exists:
        return candidate
    resolved = shutil.which(candidate) if Path(candidate).name == candidate else candidate
    if not resolved or not Path(resolved).exists():
        raise BambuPrintError("bambox CLI was not found. Install it separately or set BAMBOX_BIN.")
    return resolved


def build_bambox_pack_command(
    *,
    gcode_path: Path,
    output_path: Path,
    profile_key: str,
    filaments: list[str] | None,
    bambox_bin: str | None = None,
    require_bambox: bool = False,
) -> list[str]:
    profile = bambox_profile(profile_key)
    safe_filaments = validate_bambox_filaments(profile, filaments)
    command = [
        resolve_bambox_bin(bambox_bin, require_exists=require_bambox),
        "pack",
        str(gcode_path),
        "-o",
        str(output_path),
        "-m",
        profile.machine,
        "--nozzle-diameter",
        profile.nozzle_diameter,
    ]
    for filament in safe_filaments:
        command.extend(["-f", filament])
    return command


def build_bambox_validate_command(*, project_path: Path, bambox_bin: str | None = None, require_bambox: bool = False) -> list[str]:
    return [
        resolve_bambox_bin(bambox_bin, require_exists=require_bambox),
        "validate",
        str(project_path),
        "--json",
        "--strict",
    ]


def run_checked_command(command: list[str], label: str) -> dict[str, Any]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    payload: dict[str, Any] = {"command": command, "returncode": result.returncode}
    if result.stdout:
        payload["stdout_tail"] = tail_text(result.stdout)
    if result.stderr:
        payload["stderr_tail"] = tail_text(result.stderr)
    if result.returncode != 0:
        raise BambuPrintError(f"{label} failed: {json.dumps(payload, indent=2)}")
    return payload


def package_with_bambox(args: argparse.Namespace, output_path: Path) -> dict[str, Any]:
    gcode_path = Path(args.gcode).expanduser().resolve()
    inspect_gcode_file(gcode_path)
    pack_command = build_bambox_pack_command(
        gcode_path=gcode_path,
        output_path=output_path,
        profile_key=args.bambox_profile,
        filaments=args.filament,
        bambox_bin=args.bambox_bin,
        require_bambox=True,
    )
    validate_command = build_bambox_validate_command(
        project_path=output_path,
        bambox_bin=args.bambox_bin,
        require_bambox=True,
    )
    pack_result = run_checked_command(pack_command, "bambox pack")
    if not output_path.is_file():
        raise BambuPrintError(f"bambox pack did not create expected output: {output_path}")
    project_inspection = inspect_sliced_3mf(output_path)
    validate_result = run_checked_command(validate_command, "bambox validate")
    return {
        "pack": pack_result,
        "validate": validate_result,
        "project": asdict(project_inspection),
    }


def package_with_template_project(args: argparse.Namespace, output_path: Path) -> dict[str, Any]:
    gcode_path = Path(args.gcode).expanduser().resolve()
    inspection = inspect_gcode_file(gcode_path)
    if not args.template_project:
        raise BambuPrintError("--template-project is required for template-project packaging.")
    template_path = Path(args.template_project).expanduser().resolve()
    template_inspection = inspect_sliced_3mf(template_path)
    plate = selected_plate(template_inspection, args.plate)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    gcode_bytes = gcode_path.read_bytes()
    gcode_md5 = hashlib.md5(gcode_bytes).hexdigest().upper()
    md5_path = f"{plate.path}.md5"
    found_plate = False
    found_md5 = False

    with zipfile.ZipFile(template_path, "r") as source, zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == plate.path:
                data = gcode_bytes
                found_plate = True
            elif info.filename == md5_path:
                data = gcode_md5.encode("ascii")
                found_md5 = True
            target.writestr(info, data)
        if not found_md5:
            target.writestr(md5_path, gcode_md5)

    if not found_plate:
        raise BambuPrintError(f"Template project plate G-code entry not found: {plate.path}")

    project_inspection = inspect_sliced_3mf(output_path)
    return {
        "pack": {
            "template": str(template_path),
            "output": str(output_path),
            "replaced_plate": plate.path,
            "plate_gcode_md5": gcode_md5,
            "input": asdict(inspection),
        },
        "project": asdict(project_inspection),
    }


def build_package_plan(args: argparse.Namespace) -> dict[str, Any]:
    gcode_path = Path(args.gcode).expanduser().resolve()
    inspection = inspect_gcode_file(gcode_path)
    output_path = Path(args.output).expanduser().resolve()
    pack_command = build_bambox_pack_command(
        gcode_path=gcode_path,
        output_path=output_path,
        profile_key=args.bambox_profile,
        filaments=args.filament,
        bambox_bin=args.bambox_bin,
        require_bambox=False,
    )
    validate_command = build_bambox_validate_command(
        project_path=output_path,
        bambox_bin=args.bambox_bin,
        require_bambox=False,
    )
    return {
        "dry_run": not args.execute,
        "action": "package",
        "input": asdict(inspection),
        "output": str(output_path),
        "bambox": {
            "profile": bambox_profile_payload(bambox_profile(args.bambox_profile)),
            "filaments": args.filament,
            "pack_command": pack_command,
            "validate_command": validate_command,
        },
        "notes": [
            "bambox is optional and must be installed separately.",
            "Only enabled bambox profiles can be packaged.",
            "A1 Mini is intentionally disabled until a validated bambox profile is available.",
        ],
    }


def build_plain_send_plan(args: argparse.Namespace) -> dict[str, Any]:
    gcode_path = Path(args.gcode).expanduser().resolve()
    inspection = inspect_gcode_file(gcode_path)
    remote_name = sanitize_remote_name(args.remote_name or gcode_path.name)
    remote_path = join_remote_path(args.remote_dir or DEFAULT_REMOTE_DIR, remote_name)
    payload = build_gcode_file_payload(remote_path=remote_path, args=args)
    return build_common_send_plan(
        args=args,
        input_payload={**asdict(inspection), "kind": "plain_gcode"},
        local_path=str(gcode_path),
        remote_path=remote_path,
        remote_url=None,
        payload=payload,
    )


def build_bambox_project_send_plan(args: argparse.Namespace, project_path: Path | None = None) -> dict[str, Any]:
    gcode_path = Path(args.gcode).expanduser().resolve()
    inspection = inspect_gcode_file(gcode_path)
    remote_name = sanitize_remote_name(args.remote_name or default_project_name(gcode_path))
    remote_path = join_remote_path(args.remote_dir or "", remote_name)
    remote_url = f"ftp:///{remote_path}"
    output_path = project_path or Path(tempfile.gettempdir()) / default_project_name(gcode_path)
    pack_command = build_bambox_pack_command(
        gcode_path=gcode_path,
        output_path=output_path,
        profile_key=args.bambox_profile,
        filaments=args.filament,
        bambox_bin=args.bambox_bin,
        require_bambox=False,
    )
    validate_command = build_bambox_validate_command(
        project_path=output_path,
        bambox_bin=args.bambox_bin,
        require_bambox=False,
    )

    project: dict[str, Any] | None = None
    payload: dict[str, Any]
    if project_path is not None:
        project_inspection = inspect_sliced_3mf(project_path)
        plate = selected_plate(project_inspection, args.plate)
        project = {**asdict(project_inspection), "selected_plate": asdict(plate)}
        payload = build_project_file_payload(
            plate=plate,
            remote_path=remote_path,
            remote_url=remote_url,
            md5=project_inspection.md5,
            args=args,
        )
    else:
        payload = build_project_file_payload(
            plate=PlateInfo(index=1, path="Metadata/plate_1.gcode", size_bytes=0),
            remote_path=remote_path,
            remote_url=remote_url,
            md5=None,
            args=args,
        )

    return build_common_send_plan(
        args=args,
        input_payload={
            **asdict(inspection),
            "kind": "plain_gcode",
            "bambox_project": project,
            "bambox": {
                "profile": bambox_profile_payload(bambox_profile(args.bambox_profile)),
                "filaments": args.filament,
                "pack_command": pack_command,
                "validate_command": validate_command,
            },
        },
        local_path=str(project_path) if project_path is not None else None,
        remote_path=remote_path,
        remote_url=remote_url,
        payload=payload,
    )


def build_template_project_send_plan(args: argparse.Namespace, project_path: Path | None = None) -> dict[str, Any]:
    gcode_path = Path(args.gcode).expanduser().resolve()
    inspection = inspect_gcode_file(gcode_path)
    template_path = Path(args.template_project).expanduser().resolve() if args.template_project else None
    if template_path is None:
        raise BambuPrintError("--template-project is required for --handoff template-project.")
    inspect_sliced_3mf(template_path)
    remote_name = sanitize_remote_name(args.remote_name or default_project_name(gcode_path))
    remote_path = join_remote_path(args.remote_dir or "", remote_name)
    remote_url = f"ftp:///{remote_path}"
    output_path = project_path or Path(tempfile.gettempdir()) / default_project_name(gcode_path)

    project: dict[str, Any] | None = None
    if project_path is not None:
        project_inspection = inspect_sliced_3mf(project_path)
        plate = selected_plate(project_inspection, args.plate)
        project = {**asdict(project_inspection), "selected_plate": asdict(plate)}
        payload = build_project_file_payload(
            plate=plate,
            remote_path=remote_path,
            remote_url=remote_url,
            md5=project_inspection.md5,
            args=args,
        )
    else:
        payload = build_project_file_payload(
            plate=PlateInfo(index=1, path="Metadata/plate_1.gcode", size_bytes=0),
            remote_path=remote_path,
            remote_url=remote_url,
            md5=None,
            args=args,
        )

    return build_common_send_plan(
        args=args,
        input_payload={
            **asdict(inspection),
            "kind": "plain_gcode",
            "template_project": {
                "template": str(template_path),
                "output": str(output_path),
                "packaged_project": project,
                "note": "Experimental A1/A1 Mini path: replaces Metadata/plate_1.gcode in a same-printer template project.",
            },
        },
        local_path=str(project_path) if project_path is not None else None,
        remote_path=remote_path,
        remote_url=remote_url,
        payload=payload,
    )


def build_common_send_plan(
    *,
    args: argparse.Namespace,
    input_payload: dict[str, Any],
    local_path: str | None,
    remote_path: str,
    remote_url: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    serial = getattr(args, "serial", "") or ""
    topic = f"device/{serial}/request" if serial else None
    will_upload = args.action in {"upload", "upload-start"}
    will_publish = args.action in {"start", "upload-start"}

    ftps: dict[str, Any] = {
        "host": args.host,
        "port": args.ftps_port,
        "username": BAMBU_USERNAME,
        "remote_path": remote_path,
        "will_upload": will_upload,
    }
    if remote_url:
        ftps["url"] = remote_url

    return {
        "dry_run": not args.execute,
        "action": args.action,
        "handoff": args.handoff,
        "input": input_payload,
        "local_upload_path": local_path,
        "ftps": ftps,
        "mqtt": {
            "host": args.host,
            "port": args.mqtt_port,
            "username": BAMBU_USERNAME,
            "topic": topic,
            "payload": payload,
            "will_publish": will_publish,
        },
        "safety": [
            "Dry-run is the default; network actions require --execute.",
            "Starting a print requires --confirm-start-print.",
            "MQTT start publishes a request only; watch the printer UI/state for acceptance and progress.",
            "Verify the build plate is clear, filament/path are correct, and the printer is physically safe before execution.",
        ],
    }


def build_clear_error_plan(args: argparse.Namespace) -> dict[str, Any]:
    serial = getattr(args, "serial", "") or ""
    topic = f"device/{serial}/request" if serial else None
    return {
        "dry_run": not args.execute,
        "action": "clear-error",
        "printer": args.printer or None,
        "host": args.host,
        "mqtt": {
            "host": args.host,
            "port": args.mqtt_port,
            "username": BAMBU_USERNAME,
            "topic": topic,
            "payload": build_clean_print_error_payload(args),
            "will_publish": bool(args.execute),
        },
        "notes": [
            "This publishes clean_print_error only; it does not upload files or start a print.",
            "Use after resolving the underlying cause of a stale printer error, then read status before retrying.",
        ],
    }


def build_print_control_plan(args: argparse.Namespace) -> dict[str, Any]:
    serial = getattr(args, "serial", "") or ""
    topic = f"device/{serial}/request" if serial else None
    return {
        "dry_run": not args.execute,
        "action": args.action,
        "printer": args.printer or None,
        "host": args.host,
        "mqtt": {
            "host": args.host,
            "port": args.mqtt_port,
            "username": BAMBU_USERNAME,
            "topic": topic,
            "payload": build_print_control_payload(args),
            "will_publish": bool(args.execute),
        },
        "notes": [
            "This publishes a print-control request only; it does not upload files or start a print.",
            "Read printer status after publishing to confirm the state changed as intended.",
        ],
    }


def build_send_plan(args: argparse.Namespace, project_path: Path | None = None) -> dict[str, Any]:
    apply_printer_config(args)
    if args.handoff == "plain":
        return build_plain_send_plan(args)
    if args.handoff == "bambox-project":
        return build_bambox_project_send_plan(args, project_path=project_path)
    if args.handoff == "template-project":
        return build_template_project_send_plan(args, project_path=project_path)
    raise BambuPrintError(f"Unsupported handoff: {args.handoff}")


def upload_ftps(args: argparse.Namespace, local_path: Path, remote_path: str) -> None:
    access_code = access_code_from_args(args)
    validate_local_host(args.host, args.allow_nonprivate_host)
    context = ssl.create_default_context()
    if not args.tls_verify:
        # Bambu printer firmware serves self-signed LAN certificates; validate_local_host()
        # above restricts this to private/loopback/link-local hosts, so disabling verification
        # here only trusts the printer's subnet, not its actual certificate.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    ftp = ImplicitFTP_TLS(context=context, timeout=args.timeout)
    ftp.connect(args.host, args.ftps_port)
    try:
        ftp.login(BAMBU_USERNAME, access_code)
        ftp.prot_p()
        remote_dir = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
        remote_name = Path(remote_path).name
        if remote_dir:
            try:
                ftp.cwd(remote_dir)
            except ftplib.error_perm:
                ftp.mkd(remote_dir)
                ftp.cwd(remote_dir)
        with local_path.open("rb") as handle:
            storbinary_with_bambu_timeout_tolerance(ftp, f"STOR {remote_name}", handle)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def storbinary_with_bambu_timeout_tolerance(ftp: ftplib.FTP_TLS, command: str, handle: Any) -> None:
    try:
        ftp.storbinary(command, handle)
    except socket.timeout as exc:
        try:
            ftp.voidresp()
        except Exception as confirm_exc:
            raise BambuPrintError(
                "FTPS upload timed out before the printer confirmed completion. "
                "The file may be partially uploaded; retry upload-only after checking printer storage."
            ) from confirm_exc
        # Some Bambu FTPS firmware completes STOR but does not close the TLS data
        # channel the way Python's ftplib expects. A 226 control response is enough.


def encode_mqtt_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 65535:
        raise BambuPrintError("MQTT string is too long.")
    return len(encoded).to_bytes(2, "big") + encoded


def encode_remaining_length(length: int) -> bytes:
    out = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length:
            byte |= 0x80
        out.append(byte)
        if not length:
            return bytes(out)


def read_exact(sock: ssl.SSLSocket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise BambuPrintError("MQTT connection closed unexpectedly.")
        chunks.extend(chunk)
    return bytes(chunks)


def read_mqtt_packet(sock: ssl.SSLSocket) -> tuple[int, bytes]:
    header = read_exact(sock, 1)[0]
    multiplier = 1
    remaining = 0
    while True:
        digit = read_exact(sock, 1)[0]
        remaining += (digit & 127) * multiplier
        if not digit & 128:
            break
        multiplier *= 128
        if multiplier > 128 * 128 * 128:
            raise BambuPrintError("Malformed MQTT remaining length.")
    return header, read_exact(sock, remaining)


def mqtt_connect_packet(client_id: str, username: str, password: str, keepalive: int = 30) -> bytes:
    variable = encode_mqtt_string("MQTT") + bytes([4, 0xC2]) + keepalive.to_bytes(2, "big")
    payload = encode_mqtt_string(client_id) + encode_mqtt_string(username) + encode_mqtt_string(password)
    remaining = variable + payload
    return bytes([0x10]) + encode_remaining_length(len(remaining)) + remaining


def mqtt_publish_packet(topic: str, payload: bytes, *, qos: int = 0, packet_id: int = 1) -> bytes:
    if qos not in {0, 1}:
        raise BambuPrintError("Only MQTT QoS 0 and QoS 1 are supported.")
    variable = encode_mqtt_string(topic)
    if qos:
        variable += packet_id.to_bytes(2, "big")
    remaining = variable + payload
    return bytes([0x30 | (qos << 1)]) + encode_remaining_length(len(remaining)) + remaining


def mqtt_subscribe_packet(packet_id: int, topic: str) -> bytes:
    variable = packet_id.to_bytes(2, "big")
    payload = encode_mqtt_string(topic) + bytes([0])
    remaining = variable + payload
    return bytes([0x82]) + encode_remaining_length(len(remaining)) + remaining


def parse_mqtt_publish(header: int, body: bytes) -> tuple[str, bytes]:
    if header & 0xF0 != 0x30:
        raise BambuPrintError(f"Expected MQTT PUBLISH packet, got header=0x{header:02x}.")
    if len(body) < 2:
        raise BambuPrintError("Malformed MQTT PUBLISH packet.")
    topic_length = int.from_bytes(body[:2], "big")
    topic_start = 2
    topic_end = topic_start + topic_length
    topic = body[topic_start:topic_end].decode("utf-8", errors="replace")
    payload_start = topic_end
    qos = (header & 0x06) >> 1
    if qos:
        payload_start += 2
    return topic, body[payload_start:]


def format_hms_code(attr: Any, code: Any) -> str:
    try:
        attr_int = int(attr)
        code_int = int(code)
    except (TypeError, ValueError) as exc:
        raise BambuPrintError("HMS attr/code values must be integers.") from exc
    return f"{(attr_int >> 16) & 0xFFFF:04X}-{attr_int & 0xFFFF:04X}-{(code_int >> 16) & 0xFFFF:04X}-{code_int & 0xFFFF:04X}"


def annotate_hms_codes(message: dict[str, Any]) -> None:
    payload = message.get("json")
    if not isinstance(payload, dict):
        return
    print_payload = payload.get("print")
    if not isinstance(print_payload, dict):
        return
    hms_items = print_payload.get("hms")
    if not isinstance(hms_items, list):
        return
    decoded: list[dict[str, Any]] = []
    for item in hms_items:
        if not isinstance(item, dict) or "attr" not in item or "code" not in item:
            continue
        decoded.append({**item, "hms_code": format_hms_code(item["attr"], item["code"])})
    if decoded:
        message["hms"] = decoded


def mqtt_puback_packet(packet_id: int) -> bytes:
    return bytes([0x40, 0x02]) + packet_id.to_bytes(2, "big")


def read_mqtt_reports_until(
    sock: ssl.SSLSocket,
    *,
    deadline: float,
    timeout: float,
    expected_puback_packet_id: int | None = None,
    stop_after_puback: bool = False,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    puback_received = expected_puback_packet_id is None
    while time.monotonic() < deadline:
        sock.settimeout(max(0.1, min(timeout, deadline - time.monotonic())))
        try:
            header, body = read_mqtt_packet(sock)
        except socket.timeout:
            break
        if header == 0x40:
            packet_id = int.from_bytes(body[:2], "big") if len(body) >= 2 else None
            if packet_id == expected_puback_packet_id:
                puback_received = True
                if stop_after_puback:
                    break
            continue
        if header & 0xF0 != 0x30:
            continue
        message_topic, report_payload = parse_mqtt_publish(header, body)
        text = report_payload.decode("utf-8", errors="replace")
        item: dict[str, Any] = {"topic": message_topic, "payload": text}
        try:
            item["json"] = json.loads(text)
        except json.JSONDecodeError:
            pass
        annotate_hms_codes(item)
        messages.append(item)
        qos = (header & 0x06) >> 1
        if qos == 1:
            topic_length = int.from_bytes(body[:2], "big")
            publish_packet_id_start = 2 + topic_length
            packet_id = int.from_bytes(body[publish_packet_id_start : publish_packet_id_start + 2], "big")
            sock.sendall(mqtt_puback_packet(packet_id))
    return {"puback_received": puback_received, "messages": messages}


def publish_mqtt(
    args: argparse.Namespace,
    topic: str,
    payload: dict[str, Any],
    *,
    report_topic: str | None = None,
) -> dict[str, Any]:
    access_code = access_code_from_args(args)
    validate_local_host(args.host, args.allow_nonprivate_host)
    context = ssl.create_default_context()
    if not args.tls_verify:
        # Bambu printer firmware serves self-signed LAN certificates; validate_local_host()
        # above restricts this to private/loopback/link-local hosts, so disabling verification
        # here only trusts the printer's subnet, not its actual certificate.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    client_id = args.client_id or args.serial or f"codex-bambu-{int(time.time())}"
    raw_mqtt_qos = getattr(args, "mqtt_qos", 0)
    if not isinstance(raw_mqtt_qos, (int, float, str)):
        raw_mqtt_qos = 0
    mqtt_qos = int(raw_mqtt_qos)
    publish_packet_id = 2
    raw_wait_after_publish = getattr(args, "wait_after_publish", 0.0)
    if not isinstance(raw_wait_after_publish, (int, float, str)):
        raw_wait_after_publish = 0.0
    wait_after_publish = float(raw_wait_after_publish or 0.0)
    diagnostics: dict[str, Any] = {
        "qos": mqtt_qos,
        "puback_required": mqtt_qos == 1,
        "puback_received": mqtt_qos == 0,
        "report_topic": report_topic if wait_after_publish and report_topic else None,
        "messages": [],
    }
    with socket.create_connection((args.host, args.mqtt_port), timeout=args.timeout) as raw_sock:
        with context.wrap_socket(raw_sock, server_hostname=args.host) as sock:
            sock.sendall(mqtt_connect_packet(client_id, BAMBU_USERNAME, access_code))
            header, body = read_mqtt_packet(sock)
            if header != 0x20 or len(body) != 2 or body[1] != 0:
                raise BambuPrintError(f"MQTT CONNACK failed: header=0x{header:02x} body={body.hex()}")
            if wait_after_publish and report_topic:
                sock.sendall(mqtt_subscribe_packet(1, report_topic))
                header, body = read_mqtt_packet(sock)
                if header != 0x90 or len(body) < 3 or body[-1] == 0x80:
                    raise BambuPrintError(f"MQTT SUBACK failed: header=0x{header:02x} body={body.hex()}")
            sock.sendall(mqtt_publish_packet(topic, payload_bytes, qos=mqtt_qos, packet_id=publish_packet_id))
            if mqtt_qos == 1 or wait_after_publish:
                wait_seconds = wait_after_publish if wait_after_publish else args.timeout
                observed = read_mqtt_reports_until(
                    sock,
                    deadline=time.monotonic() + wait_seconds,
                    timeout=args.timeout,
                    expected_puback_packet_id=publish_packet_id if mqtt_qos == 1 else None,
                    stop_after_puback=mqtt_qos == 1 and not wait_after_publish,
                )
                diagnostics.update(observed)
            sock.sendall(bytes([0xE0, 0x00]))
    return diagnostics


def subscribe_mqtt_reports(
    args: argparse.Namespace,
    topic: str,
    wait_seconds: float,
    *,
    push_all_topic: str | None = None,
    max_messages: int = 1,
) -> list[dict[str, Any]]:
    access_code = access_code_from_args(args)
    validate_local_host(args.host, args.allow_nonprivate_host)
    context = ssl.create_default_context()
    if not args.tls_verify:
        # Bambu printer firmware serves self-signed LAN certificates; validate_local_host()
        # above restricts this to private/loopback/link-local hosts, so disabling verification
        # here only trusts the printer's subnet, not its actual certificate.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    client_id = args.client_id or args.serial or f"codex-bambu-status-{int(time.time())}"
    messages: list[dict[str, Any]] = []
    deadline = time.monotonic() + wait_seconds
    with socket.create_connection((args.host, args.mqtt_port), timeout=args.timeout) as raw_sock:
        with context.wrap_socket(raw_sock, server_hostname=args.host) as sock:
            sock.sendall(mqtt_connect_packet(client_id, BAMBU_USERNAME, access_code))
            header, body = read_mqtt_packet(sock)
            if header != 0x20 or len(body) != 2 or body[1] != 0:
                raise BambuPrintError(f"MQTT CONNACK failed: header=0x{header:02x} body={body.hex()}")
            sock.sendall(mqtt_subscribe_packet(1, topic))
            header, body = read_mqtt_packet(sock)
            if header != 0x90 or len(body) < 3 or body[-1] == 0x80:
                raise BambuPrintError(f"MQTT SUBACK failed: header=0x{header:02x} body={body.hex()}")
            if push_all_topic:
                payload = {
                    "pushing": {
                        "sequence_id": sequence_id(args.sequence_id),
                        "command": "pushall",
                        "version": 1,
                        "push_target": 1,
                    }
                }
                sock.sendall(mqtt_publish_packet(push_all_topic, json.dumps(payload, separators=(",", ":")).encode()))
            while time.monotonic() < deadline:
                sock.settimeout(max(0.1, min(args.timeout, deadline - time.monotonic())))
                try:
                    header, body = read_mqtt_packet(sock)
                except socket.timeout:
                    break
                if header & 0xF0 != 0x30:
                    continue
                message_topic, payload = parse_mqtt_publish(header, body)
                text = payload.decode("utf-8", errors="replace")
                item: dict[str, Any] = {"topic": message_topic, "payload": text}
                try:
                    item["json"] = json.loads(text)
                except json.JSONDecodeError:
                    pass
                annotate_hms_codes(item)
                messages.append(item)
                if len(messages) >= max_messages:
                    break
                payload_json = item.get("json")
                if (
                    push_all_topic
                    and isinstance(payload_json, dict)
                    and isinstance(payload_json.get("print"), dict)
                    and payload_json["print"].get("command") == "push_status"
                    and payload_json["print"].get("msg") == 0
                ):
                    break
            sock.sendall(bytes([0xE0, 0x00]))
    return messages


def access_code_from_args(args: argparse.Namespace) -> str:
    access_code = args.access_code or ""
    if not access_code:
        raise BambuPrintError("Access code is required for --execute. Configure --printer with config set or pass --access-code.")
    if set(access_code) == {"0"}:
        raise BambuPrintError("Access code is all zeros; refresh the printer access code before execution.")
    return access_code


def tail_text(value: str, *, max_lines: int = 80) -> str:
    lines = value.splitlines()
    if len(lines) <= max_lines:
        return value
    return "\n".join(lines[-max_lines:])


def package_main(args: argparse.Namespace) -> int:
    plan = build_package_plan(args)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0

    output_path = Path(args.output).expanduser().resolve()
    result = package_with_bambox(args, output_path)
    plan["dry_run"] = False
    plan["executed"] = ["bambox_pack", "bambox_validate"]
    plan["result"] = result
    print(json.dumps(plan, indent=2))
    return 0


def config_set_main(args: argparse.Namespace) -> int:
    path = config_path_from_args(args)
    data = load_config(path)
    printers = data.setdefault("printers", {})
    entry = printers.get(args.printer)
    if not isinstance(entry, dict):
        entry = {}
        printers[args.printer] = entry
    if args.host:
        entry["host"] = args.host
    if args.access_code:
        entry["access_code"] = args.access_code
    if args.model:
        entry["model"] = args.model
    if args.notes:
        entry["notes"] = args.notes
    serial = args.serial or ""
    if args.fetch_serial:
        host = args.host or str(entry.get("host") or "")
        if not host:
            raise BambuPrintError("Cannot fetch serial without --host or an existing host in the printer config.")
        serial = discover_printer_serial(
            host=host,
            port=args.mqtt_port,
            timeout=args.timeout,
            tls_verify=args.tls_verify,
            allow_nonprivate_host=args.allow_nonprivate_host,
        )
        entry["serial_source"] = "printer_tls_certificate_common_name"
    if serial:
        entry["serial"] = serial
    entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_config(path, data)
    print(json.dumps({"ok": True, "config": str(path), "printer": args.printer, "entry": sanitized_printer_entry(entry)}, indent=2))
    return 0


def config_list_main(args: argparse.Namespace) -> int:
    path = config_path_from_args(args)
    data = load_config(path)
    printers = data.get("printers", {})
    payload = {
        "config": str(path),
        "printers": {printer_id: sanitized_printer_entry(entry) for printer_id, entry in sorted(printers.items())},
    }
    print(json.dumps(payload, indent=2))
    return 0


def config_show_main(args: argparse.Namespace) -> int:
    path = config_path_from_args(args)
    data = load_config(path)
    entry = printer_entry(data, args.printer)
    print(json.dumps({"config": str(path), "printer": args.printer, "entry": sanitized_printer_entry(entry)}, indent=2))
    return 0


def serial_main(args: argparse.Namespace) -> int:
    apply_printer_config(args)
    serial = discover_printer_serial(
        host=args.host,
        port=args.mqtt_port,
        timeout=args.timeout,
        tls_verify=args.tls_verify,
        allow_nonprivate_host=args.allow_nonprivate_host,
    )
    args.serial = serial
    cache_printer_serial(args, serial)
    payload = {
        "ok": True,
        "printer": args.printer or None,
        "host": args.host,
        "config": str(config_path_from_args(args)) if args.printer else None,
        "port": args.mqtt_port,
        "serial": serial,
        "source": "printer_tls_certificate_common_name",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(serial)
    return 0


def status_main(args: argparse.Namespace) -> int:
    apply_printer_config(args)
    serial = ensure_printer_serial(args)
    if not serial:
        raise BambuPrintError("Printer serial is required for status; configure --printer or pass --serial.")
    topic = args.topic or f"device/{serial}/report"
    push_all_topic = f"device/{serial}/request" if args.push_all else None
    messages = subscribe_mqtt_reports(
        args,
        topic,
        args.wait_seconds,
        push_all_topic=push_all_topic,
        max_messages=args.max_messages,
    )
    payload = {
        "ok": bool(messages),
        "printer": args.printer or None,
        "host": args.host,
        "topic": topic,
        "push_all_requested": bool(args.push_all),
        "messages": messages,
    }
    if not messages:
        payload["warning"] = f"No report message received within {args.wait_seconds:g} seconds."
    print(json.dumps(payload, indent=2))
    return 0 if messages else 1


def clear_error_main(args: argparse.Namespace) -> int:
    apply_printer_config(args)
    if args.execute and not ensure_printer_serial(args):
        raise BambuPrintError("Printer serial is required to publish clean_print_error.")
    plan = build_clear_error_plan(args)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    publish_result = publish_mqtt(
        args,
        plan["mqtt"]["topic"],
        plan["mqtt"]["payload"],
        report_topic=f"device/{args.serial}/report" if getattr(args, "serial", "") else None,
    )
    plan["dry_run"] = False
    plan["executed"] = ["publish_clean_print_error"]
    plan["mqtt_publish_result"] = publish_result
    print(json.dumps(plan, indent=2))
    return 0


def print_control_main(args: argparse.Namespace) -> int:
    apply_printer_config(args)
    if args.execute and args.action == "cancel" and not args.confirm_cancel_print:
        raise BambuPrintError("Canceling a print requires --confirm-cancel-print.")
    if args.execute and not ensure_printer_serial(args):
        raise BambuPrintError("Printer serial is required to publish a print-control command.")
    plan = build_print_control_plan(args)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    publish_result = publish_mqtt(
        args,
        plan["mqtt"]["topic"],
        plan["mqtt"]["payload"],
        report_topic=f"device/{args.serial}/report" if getattr(args, "serial", "") else None,
    )
    plan["dry_run"] = False
    plan["executed"] = [f"publish_{args.action}_request"]
    plan["mqtt_publish_result"] = publish_result
    print(json.dumps(plan, indent=2))
    return 0


def send_main(args: argparse.Namespace) -> int:
    apply_printer_config(args)
    if args.execute and args.action == "plan":
        raise BambuPrintError("--execute has no effect with --action plan.")
    if args.execute and args.action in {"start", "upload-start"} and not args.confirm_start_print:
        raise BambuPrintError("Starting a print requires --confirm-start-print.")
    if args.execute and args.action in {"start", "upload-start"} and not ensure_printer_serial(args):
        raise BambuPrintError("Printer serial is required to publish a start command.")
    plan = build_send_plan(args)

    if args.handoff == "plain":
        local_path = Path(args.gcode).expanduser().resolve()
        if not args.execute:
            print(json.dumps(plan, indent=2))
            return 0
        return execute_send(args, plan, local_path)

    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0

    if args.handoff == "template-project":
        with tempfile.TemporaryDirectory(prefix="bambu-template-project-") as tmp:
            project_path = Path(tmp) / default_project_name(Path(args.gcode).expanduser())
            package_result = package_with_template_project(args, project_path)
            plan = build_send_plan(args, project_path=project_path)
            plan["template_project_execution"] = package_result
            return execute_send(args, plan, project_path)

    with tempfile.TemporaryDirectory(prefix="bambu-bambox-") as tmp:
        project_path = Path(tmp) / default_project_name(Path(args.gcode).expanduser())
        package_result = package_with_bambox(args, project_path)
        plan = build_send_plan(args, project_path=project_path)
        plan["bambox_execution"] = package_result
        return execute_send(args, plan, project_path)


def execute_send(args: argparse.Namespace, plan: dict[str, Any], local_path: Path) -> int:
    executed: list[str] = []
    if args.action in {"upload", "upload-start"}:
        upload_ftps(args, local_path, plan["ftps"]["remote_path"])
        executed.append("upload")
    if args.action in {"start", "upload-start"}:
        publish_result = publish_mqtt(
            args,
            plan["mqtt"]["topic"],
            plan["mqtt"]["payload"],
            report_topic=f"device/{args.serial}/report" if getattr(args, "serial", "") else None,
        )
        if isinstance(publish_result, dict):
            plan["mqtt_publish_result"] = publish_result
        executed.append("publish_start_request")
    plan["dry_run"] = False
    plan["local_upload_path"] = str(local_path)
    plan["executed"] = executed
    if "publish_start_request" in executed:
        plan["execution_notes"] = [
            "MQTT start was published as a request; this helper does not confirm printer acceptance or print progress."
        ]
    print(json.dumps(plan, indent=2))
    return 0


def add_package_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("package", help="Package plain G-code into a supported bambox .gcode.3mf project.")
    parser.add_argument("--gcode", required=True, help="Validated plain .gcode input.")
    parser.add_argument("--output", required=True, help="Output .gcode.3mf path.")
    parser.add_argument("--bambox-profile", required=True, help="Enabled bambox compatibility profile such as p1s-0.4.")
    parser.add_argument("--filament", action="append", help="bambox filament spec. Repeat for multi-filament jobs.")
    parser.add_argument("--bambox-bin", help="Path to bambox CLI. Defaults to BAMBOX_BIN or bambox on PATH.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="execute", action="store_false", help="Print the packaging plan without running bambox.")
    mode.add_argument("--execute", dest="execute", action="store_true", help="Run bambox pack and bambox validate.")
    parser.set_defaults(execute=False, func=package_main)


def add_config_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("config", help="Read and write local Bambu printer JSON config.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Printer config JSON path.")
    config_subparsers = parser.add_subparsers(dest="config_command", required=True)

    set_parser = config_subparsers.add_parser("set", help="Create or update a configured printer.")
    set_parser.add_argument("--printer", required=True, help="Local printer id, for example a1-mini.")
    set_parser.add_argument("--host", help="Printer LAN IP or hostname.")
    set_parser.add_argument("--access-code", help="Printer LAN access code.")
    set_parser.add_argument("--model", help="Printer model, for example a1-mini.")
    set_parser.add_argument("--serial", help="Printer serial. Usually omitted; use --fetch-serial.")
    set_parser.add_argument("--notes", help="Optional operator notes.")
    set_parser.add_argument("--fetch-serial", action="store_true", help="Fetch and cache serial from the printer TLS certificate.")
    set_parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    set_parser.add_argument("--timeout", type=float, default=20.0)
    set_parser.add_argument("--tls-verify", action="store_true", help="Verify printer TLS certificates.")
    set_parser.add_argument(
        "--allow-nonprivate-host",
        action="store_true",
        help="Allow printer hosts that resolve outside private/link-local/loopback ranges.",
    )
    set_parser.set_defaults(func=config_set_main)

    list_parser = config_subparsers.add_parser("list", help="List configured printers.")
    list_parser.set_defaults(func=config_list_main)

    show_parser = config_subparsers.add_parser("show", help="Show one configured printer without printing the access code.")
    show_parser.add_argument("--printer", required=True)
    show_parser.set_defaults(func=config_show_main)


def add_serial_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("serial", help="Fetch the printer serial from its local TLS certificate.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Printer config JSON path.")
    parser.add_argument("--printer", help="Configured printer id.")
    parser.add_argument("--host", default="", help="Printer LAN IP or hostname.")
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--tls-verify", action="store_true", help="Verify printer TLS certificates.")
    parser.add_argument(
        "--allow-nonprivate-host",
        action="store_true",
        help="Allow printer hosts that resolve outside private/link-local/loopback ranges.",
    )
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=serial_main)


def add_status_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("status", help="Read one MQTT report message from a configured local printer.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Printer config JSON path.")
    parser.add_argument("--printer", help="Configured printer id.")
    parser.add_argument("--host", default="", help="Printer LAN IP or hostname.")
    parser.add_argument(
        "--serial",
        default="",
        help="Printer serial number for MQTT topic. Usually loaded from config or fetched automatically.",
    )
    parser.add_argument("--access-code", help="Printer access code for one-off use. Prefer --printer config.")
    parser.add_argument("--topic", help="MQTT report topic. Defaults to device/{serial}/report.")
    parser.add_argument("--push-all", action="store_true", help="Request a full status report after subscribing.")
    parser.add_argument("--wait-seconds", type=float, default=10.0)
    parser.add_argument("--max-messages", type=int, default=1, help="Maximum report messages to collect before returning.")
    parser.add_argument("--sequence-id", help="MQTT sequence id for --push-all. Defaults to current timestamp milliseconds.")
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--tls-verify", action="store_true", help="Verify printer TLS certificates.")
    parser.add_argument(
        "--allow-nonprivate-host",
        action="store_true",
        help="Allow printer hosts that resolve outside private/link-local/loopback ranges.",
    )
    parser.add_argument("--client-id", help="MQTT client id. Defaults to the printer serial.")
    parser.set_defaults(func=status_main)


def add_clear_error_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("clear-error", help="Publish Bambu clean_print_error; dry-run by default.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Printer config JSON path.")
    parser.add_argument("--printer", help="Configured printer id.")
    parser.add_argument("--host", default="", help="Printer LAN IP or hostname.")
    parser.add_argument(
        "--serial",
        default="",
        help="Printer serial number for MQTT topic. Usually loaded from config or fetched automatically.",
    )
    parser.add_argument("--access-code", help="Printer access code for one-off use. Prefer --printer config.")
    parser.add_argument("--execute", action="store_true", help="Publish clean_print_error to the printer.")
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--tls-verify", action="store_true", help="Verify printer TLS certificates.")
    parser.add_argument(
        "--allow-nonprivate-host",
        action="store_true",
        help="Allow printer hosts that resolve outside private/link-local/loopback ranges.",
    )
    parser.add_argument("--client-id", help="MQTT client id. Defaults to the printer serial.")
    parser.add_argument("--sequence-id", help="MQTT sequence id. Defaults to current timestamp milliseconds.")
    parser.add_argument(
        "--mqtt-qos",
        type=int,
        choices=[0, 1],
        default=0,
        help="MQTT publish QoS. Default 0; use 1 for protocol diagnostics.",
    )
    parser.add_argument(
        "--wait-after-publish",
        type=float,
        default=0.0,
        help="After publishing, stay connected for this many seconds and capture report messages.",
    )
    parser.set_defaults(func=clear_error_main)


def add_print_control_parser(subparsers: argparse._SubParsersAction, action: str) -> None:
    help_text = "Pause the active local print; dry-run by default." if action == "pause" else "Cancel the active local print; dry-run by default."
    parser = subparsers.add_parser(action, help=help_text)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Printer config JSON path.")
    parser.add_argument("--printer", help="Configured printer id.")
    parser.add_argument("--host", default="", help="Printer LAN IP or hostname.")
    parser.add_argument(
        "--serial",
        default="",
        help="Printer serial number for MQTT topic. Usually loaded from config or fetched automatically.",
    )
    parser.add_argument("--access-code", help="Printer access code for one-off use. Prefer --printer config.")
    parser.add_argument("--execute", action="store_true", help=f"Publish the {action} request to the printer.")
    if action == "cancel":
        parser.add_argument(
            "--confirm-cancel-print",
            action="store_true",
            help="Required with --execute because canceling stops the active print job.",
        )
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--tls-verify", action="store_true", help="Verify printer TLS certificates.")
    parser.add_argument(
        "--allow-nonprivate-host",
        action="store_true",
        help="Allow printer hosts that resolve outside private/link-local/loopback ranges.",
    )
    parser.add_argument("--client-id", help="MQTT client id. Defaults to the printer serial.")
    parser.add_argument("--sequence-id", help="MQTT sequence id. Defaults to current timestamp milliseconds.")
    parser.add_argument(
        "--mqtt-qos",
        type=int,
        choices=[0, 1],
        default=0,
        help="MQTT publish QoS. Default 0; use 1 for protocol diagnostics.",
    )
    parser.add_argument(
        "--wait-after-publish",
        type=float,
        default=0.0,
        help="After publishing, stay connected for this many seconds and capture report messages.",
    )
    parser.set_defaults(action=action, func=print_control_main)


def add_send_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("send", help="Inspect, upload, and optionally start a validated plain G-code job.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Printer config JSON path.")
    parser.add_argument("--printer", help="Configured printer id. Preferred over repeating host/access-code flags.")
    parser.add_argument("--gcode", required=True, help="Validated plain .gcode input.")
    parser.add_argument("--handoff", choices=["plain", "bambox-project", "template-project"], default="plain")
    parser.add_argument("--host", default="", help="Printer LAN IP or hostname.")
    parser.add_argument(
        "--serial",
        default="",
        help="Printer serial number for MQTT topic. Usually omitted; the helper fetches it from the printer TLS certificate.",
    )
    parser.add_argument("--access-code", help="Printer access code for one-off use. Prefer --printer config for repeated use.")
    parser.add_argument("--action", choices=["plan", "upload", "start", "upload-start"], default="plan")
    parser.add_argument("--execute", action="store_true", help="Perform network action selected by --action.")
    parser.add_argument("--confirm-start-print", action="store_true", help="Required for --action start or upload-start with --execute.")
    parser.add_argument(
        "--remote-dir",
        default=None,
        help="Remote directory. Defaults to cache for plain G-code and printer root for project handoffs.",
    )
    parser.add_argument("--remote-name", help="Filename to store on the printer.")
    parser.add_argument("--gcode-param", help="Override MQTT gcode_file param. Defaults to the uploaded remote path.")
    parser.add_argument("--plate", type=int, help="Plate number for packaged projects. Defaults to the first plate.")
    parser.add_argument("--bambox-profile", default="p1s-0.4", help="Enabled bambox profile for --handoff bambox-project.")
    parser.add_argument("--filament", action="append", help="bambox filament spec. Repeat for multi-filament jobs.")
    parser.add_argument("--bambox-bin", help="Path to bambox CLI. Defaults to BAMBOX_BIN or bambox on PATH.")
    parser.add_argument(
        "--template-project",
        help="Same-printer sliced .gcode.3mf template for --handoff template-project.",
    )
    parser.add_argument("--ftps-port", type=int, default=DEFAULT_FTPS_PORT)
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--tls-verify", action="store_true", help="Verify printer TLS certificates.")
    parser.add_argument(
        "--allow-nonprivate-host",
        action="store_true",
        help="Allow printer hosts that resolve outside private/link-local/loopback ranges.",
    )
    parser.add_argument("--client-id", help="MQTT client id. Defaults to the printer serial for start commands.")
    parser.add_argument("--sequence-id", help="MQTT sequence id. Defaults to current timestamp milliseconds.")
    parser.add_argument(
        "--mqtt-qos",
        type=int,
        choices=[0, 1],
        default=0,
        help="MQTT publish QoS for start commands. Default 0; use 1 for protocol diagnostics.",
    )
    parser.add_argument(
        "--wait-after-publish",
        type=float,
        default=0.0,
        help="After publishing a start command, stay connected for this many seconds and capture report messages.",
    )
    parser.set_defaults(func=send_main)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_package_parser(subparsers)
    add_config_parser(subparsers)
    add_serial_parser(subparsers)
    add_status_parser(subparsers)
    add_clear_error_parser(subparsers)
    add_print_control_parser(subparsers, "pause")
    add_print_control_parser(subparsers, "cancel")
    add_send_parser(subparsers)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args)
    except BambuPrintError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
