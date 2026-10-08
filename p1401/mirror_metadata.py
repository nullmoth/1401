"""Minimal release-index metadata; vendor archives are never rewritten."""
import re
_INDEX = re.compile(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/releases/?\Z')
_TAG = re.compile(r'[^\s"<>]+\Z')

def release_index(url, data):
    match = _INDEX.fullmatch(url)
    if not match:
        return data
    text = data.decode('utf-8', 'strict')
    for line in text.splitlines():
        if '<a' in line and 'href="' in line and '/releases/tag/' in line:
            tag = line.split('/releases/tag/', 1)[1].split('"', 1)[0]
            if not _TAG.fullmatch(tag):
                raise ValueError('Release index tag is invalid')
            owner, repo = match.groups()
            return ('<a href="/' + owner + '/' + repo + '/releases/tag/' + tag + '">release</a>\n').encode('utf-8')
    raise ValueError('Release index has no supported release tag')
