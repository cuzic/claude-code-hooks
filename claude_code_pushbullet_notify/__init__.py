"""
Claude Code hook for sending Pushbullet notifications when tasks complete.
Reads JSON from stdin and processes transcript files.
"""

# Only export the main function
from .pushbullet import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
