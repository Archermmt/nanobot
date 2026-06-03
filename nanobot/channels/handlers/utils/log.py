import io
import sys


class CaptureOutput:
    def __enter__(self):
        self._output = io.StringIO()
        self._error_output = io.StringIO()
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = self._output
        sys.stderr = self._error_output

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        self.output = self._output.getvalue()
        self.error_output = self._error_output.getvalue()
        self._output.close()
        self._error_output.close()
