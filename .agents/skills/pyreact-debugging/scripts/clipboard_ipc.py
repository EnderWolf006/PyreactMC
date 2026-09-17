# -*- coding: utf-8 -*-
"""
Clipboard IPC using pyperclip.

pip3 install pyperclip
"""
import pyperclip


def read_clipboard():
    return pyperclip.paste()


def write_clipboard(text):
    pyperclip.copy(text)
