class SpeccifyError(Exception):
    pass


class CollectionError(SpeccifyError):
    """Raised at collection time, i.e. when applying the decorator"""


class RuntimeError(SpeccifyError):
    """Raised at run time, i.e. when serving requests"""


class OverlappingMethods(CollectionError):
    def __init__(self):
        super().__init__("overlapping methods are not allowed")


class InvalidReturnValue(RuntimeError):
    pass
