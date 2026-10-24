"""Per-install preferences, stored separately from files replaced by updates."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile


def preferences_path():
    if os.name == 'nt':
        return Path(__file__).resolve().with_name('preferences.json')
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'BeastRecon/preferences.json'


def default_download_directory():
    return Path('C:/BeastRecon/Downloads') if os.name == 'nt' else Path.home() / 'Downloads/BeastRecon'


@dataclass(frozen=True)
class Preferences:
    download_directory: str = ''
    default_format: str = 'mp3'
    auto_preview: bool = True

    def __post_init__(self):
        if not self.download_directory:
            object.__setattr__(self, 'download_directory', str(default_download_directory()))


def load_preferences(path=None):
    from converter import FORMATS
    path = Path(path) if path is not None else preferences_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Expected a settings object')
        folder = data.get('download_directory')
        if not isinstance(folder, str) or not folder.strip() or not Path(folder).expanduser().is_absolute():
            raise ValueError('Invalid download directory')
        if data.get('default_format') not in FORMATS or not isinstance(data.get('auto_preview'), bool):
            raise ValueError('Invalid format or preview preference')
        return Preferences(folder, data['default_format'], data['auto_preview']), None
    except FileNotFoundError:
        return Preferences(), None
    except (OSError, ValueError, TypeError) as error:
        return Preferences(), f'Could not load preferences; using defaults. Your saved file was kept. Details: {error}'


def save_preferences(preferences, path=None):
    path = Path(path) if path is not None else preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.preferences-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            json.dump(asdict(preferences), output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
