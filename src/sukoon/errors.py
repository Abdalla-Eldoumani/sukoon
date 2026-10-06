class Canceled(Exception):
    """The user cancelled the job."""


class JobError(Exception):
    """A failure whose message is shown to the user as written."""


DISK_FULL = "The disk is full."
