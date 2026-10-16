"""Reserve output filenames atomically so repeat requests never overwrite a file."""
import os
import uuid
from contextlib import contextmanager


@contextmanager
def reserve_output(folder, preferred_name):
    stem, extension = os.path.splitext(preferred_name)
    name = preferred_name
    while True:
        path = os.path.join(folder, name)
        try:
            output = open(path, "xb")
            break
        except FileExistsError:
            name = f"{stem}_{uuid.uuid4().hex}{extension}"
    try:
        with output:
            yield name, output
    except BaseException:
        os.remove(path)
        raise
