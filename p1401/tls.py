"""One TLS policy for every download 1401 makes: verify certificates, and trust what this PC trusts.

10-07 (uploaded logs NM-BWQGX8A3, NM-Q8S0TG9G, NM-MTQJT5V7, NM-GF6TWC5E, NM-9J7658B9, NM-7Z4J90J3, NM-XEG1NNF8):
every GitHub download failed with CERTIFICATE_VERIFY_FAILED "unable to get local issuer certificate", and the empty result
later crashed the build ("argument of type 'NoneType' is not iterable"). The engine built its context with
create_default_context(cafile=certifi), and passing a cafile makes Python skip the Windows certificate store - so on a PC
whose antivirus or network inspects HTTPS (its root certificate lives in that store), nothing verified, while the browser
on the same PC worked. Here the context loads the operating system's store AND certifi's bundle. Verification stays on.
"""
import ssl
import urllib.request

_CTX = None


def context():
    global _CTX
    if _CTX is None:
        ctx = ssl.create_default_context()          # no cafile: loads the OS store (Windows: ROOT and CA)
        try:
            import certifi  # noqa: PLC0415 - bundled; adds Mozilla's list for PCs whose store is thin
            ctx.load_verify_locations(cafile=certifi.where())
        except Exception:  # noqa: BLE001 - the OS store alone still verifies; the reason is that certifi is absent
            pass
        _CTX = ctx
    return _CTX


def install():
    """Every urllib.request.urlopen in this process (1401's own downloads) and the engine's fetcher use context()."""
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=context())))
    try:
        from Scripts import resource_fetcher as rf  # noqa: PLC0415 - upstream, importable once its path is set
        rf.ResourceFetcher.create_ssl_context = lambda self: context()
    except ImportError:
        pass
