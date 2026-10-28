class ProcessingError(RuntimeError):
    pass


class ProcessingInputError(ProcessingError):
    pass


class ProcessorUnavailableError(ProcessingError):
    pass


class ProcessorTimeoutError(ProcessingError):
    pass


class ProcessorExecutionError(ProcessingError):
    def __init__(
        self,
        message: str,
        return_code: int | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message)
        self.return_code = return_code
        self.stderr = stderr
