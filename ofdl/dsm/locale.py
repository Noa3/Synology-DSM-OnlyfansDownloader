"""Read the DSM system language, not user credentials or DSM sessions."""
from __future__ import annotations

import os
import re
from pathlib import Path

LANGUAGES = {'ger': 'de', 'enu': 'en', 'fre': 'fr', 'spn': 'es',
             'ita': 'it', 'nld': 'nl', 'ptg': 'pt', 'ptb': 'pt'}


def dsm_language(path: Path = Path('/etc/synoinfo.conf')) -> str:
    override = os.environ.get('OFDL_DSM_LANGUAGE', '')
    if override:
        return LANGUAGES.get(override, override if override in LANGUAGES.values() else '')
    for candidate in (path, Path('/usr/syno/etc/synoinfo.conf')):
        try:
            with candidate.open(encoding='utf-8', errors='replace') as stream:
                text = stream.read(256 * 1024)
        except OSError:
            continue
        match = re.search(r'^language\s*=\s*[\"\']?([a-zA-Z_-]+)', text, re.MULTILINE)
        if match:
            return LANGUAGES.get(match[1].lower(), '')
    return ''
