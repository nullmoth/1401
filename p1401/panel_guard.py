"""Warn when the plan disables the adapter an observed active internal panel runs on; never infer a firmware MUX or a
missing route. Laptops whose panel is wired to the Intel GPU are common and still build: macOS drives the NVIDIA card's
own outputs and the panel stays dark, which the user must know before installing."""
import re


def active_panel_notice(disabled, capture):
    """Notice text when exact completed scan evidence (one observed adapter/PnP match) puts an active internal panel on
    an Intel adapter the plan disables; None otherwise."""
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
                return ('The built-in screen runs on the Intel graphics (' + device.upper() + '), which macOS cannot use on '
                        'this system, so it will stay dark in macOS. Use a monitor on a port wired to the NVIDIA card '
                        '(often HDMI or a USB-C/Thunderbolt port), or switch the display mode to discrete/dGPU in the '
                        'firmware if it offers one and scan again.')
    return None
