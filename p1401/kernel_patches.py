"""Do not produce an EFI when a selected kernel patch set is unavailable."""
from .downloads import DownloadError


def harden(gathering_class):
    if getattr(gathering_class, '_1401_required_patches', False):
        return

    def get_kernel_patches(self, patches_name, patches_url):
        try:
            response = self.fetcher.fetch_and_parse_content(patches_url, 'plist')
            patches = response['Kernel']['Patch']
        except DownloadError:
            raise
        except (TypeError, KeyError, ValueError) as error:
            raise DownloadError(f'{patches_name} did not contain a valid kernel patch list. '
                                'Rebuild after the dependency is available; the EFI was not completed.') from error
        if not isinstance(patches, list) or not patches or not all(isinstance(p, dict) for p in patches):
            raise DownloadError(f'{patches_name} returned an empty or invalid kernel patch list. '
                                'Rebuild after the dependency is available; the EFI was not completed.')
        return patches

    gathering_class.get_kernel_patches = get_kernel_patches
    gathering_class._1401_required_patches = True
