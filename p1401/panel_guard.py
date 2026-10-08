"""Prevent disabling an observed active panel output; never infer a firmware MUX or a missing route."""
import re


def refuse_active_panel_disable(disabled, capture):
    """Use only exact completed scan evidence with one observed adapter/PnP match."""
    if not isinstance(capture, dict) or not isinstance(disabled, dict):
        return
    binding = capture.get('scan_binding')
    if not isinstance(binding, dict):
        return
    if binding.get('status') != 'same_scan_run' or binding.get('scan_status') != 'complete':
        return
    devices = capture.get('device_map')
    if not isinstance(devices, dict):
        return
    graph = devices.get('graphics')
    if not isinstance(graph, dict):
        return
    if graph.get('status') != 'measured' or not isinstance(graph.get('value'), list):
        return
    for properties in disabled.values():
        if not isinstance(properties, dict) or properties.get('Device Type') != 'Integrated GPU':
            continue
        device, subsystem = properties.get('Device ID'), properties.get('Subsystem ID')
        if not isinstance(device, str) or not re.fullmatch(r'8086-[0-9A-Fa-f]{4}', device):
            continue
        if not isinstance(subsystem, str) or not re.fullmatch(r'[0-9A-Fa-f]{8}', subsystem):
            continue
        matches = [a for a in graph['value'] if isinstance(a, dict) and
                   (a.get('vendor_id'), a.get('device_id'), a.get('subsystem_id')) ==
                   ('8086', device[5:].upper(), subsystem.upper())]
        if len(matches) != 1:
            continue
        adapter = matches[0]
        candidates = adapter.get('pci_candidates')
        displays = adapter.get('displays')
        if (not isinstance(candidates, list) or not isinstance(displays, list) or
                adapter.get('pci_match') != 'unique by IDs' or len(candidates) != 1 or
                adapter.get('identical_adapters')):
            continue
        for panel in displays:
            if (isinstance(panel, dict) and panel.get('internal_panel') is True and panel.get('active') is True and
                    panel.get('target_available') is True and panel.get('output_adapter') == adapter.get('adapter') and
                    panel.get('routing_source') == 'QueryDisplayConfig targetInfo.adapterId'):
                raise RuntimeError('EFI planning stopped: this exact scan places an active internal panel on Intel ' +
                                   device.upper() + ', but the selected configuration would disable that adapter. '
                                   'The selected plan does not establish a compatible display route or add Intel acceleration. '
                                   'Confirm an output path supported by the exact system and rescan after any firmware display-mode change. '
                                   'No installable EFI was produced; no MUX or connector route is assumed.')
