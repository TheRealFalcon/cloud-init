import logging
import os
import pathlib
import queue
import struct
import threading
import time
from ctypes import CDLL
from ctypes.util import find_library
from enum import IntEnum
from select import poll
from typing import NamedTuple, Optional

LOG = logging.getLogger(__name__)

INOTIFY_EVENT_FORMAT = "iIII"


class Flags(IntEnum):
    """Defines copied from inotify.h"""

    IN_ACCESS = 0x00000001  # File was accessed
    IN_MODIFY = 0x00000002  # File was modified
    IN_ATTRIB = 0x00000004  # Metadata changed
    IN_CLOSE_WRITE = 0x00000008  # Writable file was closed
    IN_CLOSE_NOWRITE = 0x00000010  # Unwritable file closed
    IN_OPEN = 0x00000020  # File was opened
    IN_MOVED_FROM = 0x00000040  # File was moved from X
    IN_MOVED_TO = 0x00000080  # File was moved to Y
    IN_CREATE = 0x00000100  # Subfile was created
    IN_DELETE = 0x00000200  # Subfile was deleted
    IN_DELETE_SELF = 0x00000400  # Self was deleted
    IN_MOVE_SELF = 0x00000800  # Self was moved

    IN_UNMOUNT = 0x00002000  # Backing fs was unmounted
    IN_Q_OVERFLOW = 0x00004000  # Event queue overflowed
    IN_IGNORED = 0x00008000  # File was ignored

    IN_CLOSE = IN_CLOSE_WRITE | IN_CLOSE_NOWRITE  # close
    IN_MOVE = IN_MOVED_FROM | IN_MOVED_TO  # moves

    IN_ONLYDIR = 0x01000000  # only watch the path if it is a directory
    IN_DONT_FOLLOW = 0x02000000  # don't follow a sym link
    IN_EXCL_UNLINK = 0x04000000  # exclude events on unlinked objects
    IN_MASK_ADD = 0x20000000  # add to the mask of an already existing watch
    IN_ISDIR = 0x40000000  # event occurred against dir
    IN_ONESHOT = 0x80000000  # only send event once


class InotifyEvent(NamedTuple):
    """See the "inotify_event" struct in inotify.h or `man inotify`."""

    wd: int
    mask: int
    cookie: int
    name: str


def unpack_data(data):
    """Unpack the inotify data into a list of InotifyEvent objects.

    See the "inotify_event" struct in inotify.h or `man inotify`.
    """
    index = 0
    while index < len(data):
        # See struct inotify_event in inotify.h or `man inotify``
        wd, mask, cookie, name_len = struct.unpack_from(
            INOTIFY_EVENT_FORMAT, data, index
        )
        index += struct.calcsize(INOTIFY_EVENT_FORMAT) + name_len
        name = data[index - name_len : index].rstrip(b"\x00")
        yield InotifyEvent(wd, mask, cookie, name.decode("utf-8"))


def _get_create_events_body(
    directory: bytes, timeout_in_milliseconds: int, event_queue: queue.Queue
):
    """Get "create events" for files in a directory using inotify."""
    libc = CDLL(find_library("c") or "libc.so.6")
    fd = libc.inotify_init()
    poller = poll()
    poller.register(fd)

    wd = libc.inotify_add_watch(fd, directory, Flags.IN_CREATE)

    start_time = time.monotonic()

    while poller.poll(
        timeout_in_milliseconds - ((time.monotonic() - start_time) * 1000)
    ):
        # Not 100% sure what the length arg should be here...
        data = os.read(fd, 256)
        for event in unpack_data(data):
            event_queue.put(event)
    event_queue.put(None)

    libc.inotify_rm_watch(fd, wd)
    os.close(fd)


def _get_create_events(
    directory: bytes, timeout_in_milliseconds: int, event_queue: queue.Queue
):
    """Wraps the "create events" function in a try/except block."""
    try:
        _get_create_events_body(
            directory, timeout_in_milliseconds, event_queue
        )
    except Exception as e:
        LOG.error("Unexpected error in _get_create_events: %s", e)
        event_queue.put(None)


def wait_for_file_creation(
    path: pathlib.Path, timeout_in_milliseconds: int
) -> bool:
    """Use inotify to wait for a file to be created.

    :param path: The path to the file to wait for.
    :param timeout_in_milliseconds: The maximum time to wait in milliseconds.
    :return: True if the file was created, False if the timeout was reached.

    The parent directory must exist before this function is called.
    This function is NOT thread-safe.
    """
    if not path.parent.exists():
        raise FileNotFoundError(
            f"Parent directory {path.parent} does not exist"
        )
    if path.exists():
        return True

    event_queue: "queue.Queue[Optional[InotifyEvent]]" = queue.Queue()
    t = threading.Thread(
        target=_get_create_events,
        args=(
            bytes(path.parent),
            timeout_in_milliseconds,
            event_queue,
        ),
    )
    t.daemon = True
    t.start()

    if path.exists():
        return True

    while event := event_queue.get():
        if event.name == path.name:
            return True
    return False
