class ServiceConfigurationError(RuntimeError):
    """
    Raised when a required external-service configuration is missing or invalid.

    This is intentionally a plain exception (not DRF-specific) so it can be used
    from both HTTP views and websocket/worker code.
    """

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code

