"""Properties of the stored files, so the rest of the code ignores mp3 details."""

from functools import wraps
from hashlib import sha1

from mutagen import MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError

HASHED_AUDIO_BYTES = 256 * 1024
ID_HEX_DIGITS = 16


class UnreadableFile(Exception):
    pass


def raising_unreadable_file(read_metadata):
    @wraps(read_metadata)
    def wrapper(filepath):
        try:
            return read_metadata(filepath)
        except (OSError, MutagenError) as e:
            raise UnreadableFile(e) from e
    return wrapper


@raising_unreadable_file
def identify(filepath):
    """Identifies a track by its audio, so renaming or retagging keeps it stable."""
    with open(filepath, 'rb') as file:
        file.seek(id3_tags_size(filepath))
        return sha1(file.read(HASHED_AUDIO_BYTES)).hexdigest()[:ID_HEX_DIGITS]


@raising_unreadable_file
def title(filepath):
    try:
        return str(ID3(filepath)['TIT2'])
    except (ID3NoHeaderError, KeyError):
        return filepath.stem


def id3_tags_size(filepath):
    try:
        return ID3(filepath).size
    except ID3NoHeaderError:
        return 0
