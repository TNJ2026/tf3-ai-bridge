"""Presentation language only; never translates native IDs or user content."""
import locale
import os


def language(value=None):
    """Explicit setting, process locale override, then OS locale; English fallback."""
    candidates = [value, os.environ.get('TF3_UI_LANGUAGE')]
    candidates += [os.environ.get(k) for k in ('LC_ALL', 'LC_MESSAGES', 'LANG')]
    try:
        candidates.append(locale.getlocale()[0])
    except (ValueError, TypeError):
        pass
    for candidate in candidates:
        if not candidate or str(candidate).lower() == 'auto':
            continue
        tag = str(candidate).lower().replace('_', '-').split('.')[0]
        if tag.startswith('zh') or tag.startswith('chinese'):
            return 'zh-CN'
        if tag.startswith('en') or tag in ('c', 'posix'):
            return 'en'
    return 'en'


def translate(chinese, english, lang=None):
    return chinese if language(lang) == 'zh-CN' else english
