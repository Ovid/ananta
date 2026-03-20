FROM python:3.12-slim

# Security: run as non-root user
RUN useradd -m -s /bin/bash sandbox

WORKDIR /sandbox

# Copy the runner script
COPY runner.py /sandbox/runner.py

# Set ownership
RUN chown -R sandbox:sandbox /sandbox

USER sandbox

# The runner reads JSON commands from stdin, executes, writes JSON to stdout
CMD ["python", "/sandbox/runner.py"]
