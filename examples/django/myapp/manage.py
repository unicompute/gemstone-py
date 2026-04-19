#!/usr/bin/env python3
"""
Minimal Django manage.py for the Rails myapp port.
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

import os
import sys


def main() -> None:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myapp.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
