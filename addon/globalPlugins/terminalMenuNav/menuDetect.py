# -*- coding: UTF-8 -*-
# TerminalMenuNav — menu detection core.
# Pure Python, importable outside NVDA so it can be unit-tested directly.
#
# Author: Islam Benmebarek <islam.benmebarek.dz@gmail.com>
# License: GPL v2

import re
from collections import namedtuple

# items: tuple of option texts (markers stripped)
# selectedIndex: 0-based position of the pointed option within items
# context: the prompt/question line right above the block, or None
# above: up to 3 stripped non-empty lines above the block (context first);
#	stray caret events echo these during navigation, so they get gated too
# below: up to 3 stripped non-empty lines below the block (hint/footer
#	lines like "↑/↓ to navigate"), gated for the same reason
Menu = namedtuple("Menu", ("items", "selectedIndex", "context", "above", "below"))

# Arrow-style pointer at the start of a line: "> option", "❯ option"...
# Exactly one marker character then whitespace, so ">>> banner <<<" and
# ">> nested quote" are NOT pointers.
_POINTER_RE = re.compile(r"^(\s*)([>❯›→▸»])\s+(\S.*)$")

# Selected radio/checkbox forms: "(x) option", "[x] option", "(•) option".
_SEL_BOX_RE = re.compile(r"^(\s*)(\((?:[xX*•●◉])\)|\[(?:[xX*])\])\s+(\S.*)$")

# Unselected option shapes: "( ) option", "[ ] option", or plain text
# indented at least two columns (the empty pointer column).
_UNSEL_BOX_RE = re.compile(r"^(\s*)(\(\s\)|\[\s\])\s+(\S.*)$")
_INDENTED_RE = re.compile(r"^\s{2,}(\S.*)$")

# The pointed block must end within this many non-empty lines of the end of
# the visible buffer.  An active menu sits at the bottom (the cursor lives
# in or right under it); finished menus get pushed up by result lines and
# stop matching, so stale frames in scrollback are ignored.
MAX_LINES_FROM_BOTTOM = 1

# Loose marker probe for flattened single-string announcements (VS Code
# live regions collapse the block into one line, so ^-anchored regexes
# cannot see the pointer).  Used for cheap relevance checks only.
RELEVANCE_RE = re.compile(
	r"(?:^|\s)[>❯›→▸»]\s+\S|\((?:[xX*•●◉])\)\s+\S|\[(?:[xX*])\]\s+\S"
	r"|(?:^|\s)[●◉○◯]\s+\S")

# clack-style frames (create-vite, @clack/prompts) draw a box border in
# front of every line; strip it before radio-mode matching.
_BOX_STRIP_RE = re.compile(r"^[\s│┃┆┇╎]+")


def _stripBox(line):
	return _BOX_STRIP_RE.sub("", line)


# Radio-mode options: no arrow pointer at all; the selection is the one
# filled circle among hollow ones ("● Vanilla" / "○ Vue").  ◆/◇ are clack
# step icons, not options, so they are deliberately excluded.
_RADIO_SEL_RE = re.compile(r"^[●◉]\s+(\S.*)$")
_RADIO_UNSEL_RE = re.compile(r"^[○◯]\s+(\S.*)$")

# Radio frames keep a "..." viewport marker and a key-hint footer under the
# options, so they get a looser bottom allowance than arrow menus.
_RADIO_MAX_BELOW = 3

# Scrolling-viewport marker lines ("..."): never context, never an item.
_ELLIPSIS_RE = re.compile(r"^[.…‥]+$")


def _stripOption(line):
	"""Return the option text if the line looks like a menu option
	(selected or not), else None."""
	m = _POINTER_RE.match(line)
	if m:
		return m.group(3).rstrip()
	m = _SEL_BOX_RE.match(line)
	if m:
		return m.group(3).rstrip()
	m = _UNSEL_BOX_RE.match(line)
	if m:
		return m.group(3).rstrip()
	m = _INDENTED_RE.match(line)
	if m:
		return m.group(1).rstrip()
	return None


def _isPointer(line):
	return bool(_POINTER_RE.match(line))


def _surroundings(lines, start, end, lastContent):
	"""Collect up to 3 stripped non-empty lines above and below the block
	(box borders removed): the question/context, hint footers, and their
	neighbours — everything whose stray echoes must be gated."""
	above = []
	for i in range(start - 1, max(start - 4, -1), -1):
		s = _stripBox(lines[i]).strip()
		if s and not _ELLIPSIS_RE.match(s):
			above.append(s)
		if len(above) >= 3:
			break
	below = []
	for i in range(end + 1, min(end + 4, lastContent + 1)):
		s = _stripBox(lines[i]).strip()
		if s and not _ELLIPSIS_RE.match(s):
			below.append(s)
		if len(below) >= 3:
			break
	return tuple(above), tuple(below)


def _findArrowMenu(lines, lastContent, requireBottom):
	"""Pointer-marker menus: "> option" / "❯ option" (inquirer family)."""
	pointerIdx = None
	for i in range(lastContent, -1, -1):
		if _isPointer(lines[i]):
			pointerIdx = i
			break
	if pointerIdx is None:
		return None
	# Grow the contiguous option block around the pointer.
	start = pointerIdx
	while start > 0 and lines[start - 1].strip() \
			and _stripOption(lines[start - 1]) is not None:
		start -= 1
	end = pointerIdx
	while end < lastContent and lines[end + 1].strip() \
			and _stripOption(lines[end + 1]) is not None:
		end += 1
	# Validate the block.
	if end - start + 1 < 2:
		return None
	pointerCount = sum(1 for i in range(start, end + 1) if _isPointer(lines[i]))
	if pointerCount != 1:
		return None
	if requireBottom:
		below = sum(1 for i in range(end + 1, lastContent + 1) if lines[i].strip())
		if below > MAX_LINES_FROM_BOTTOM:
			return None
	items = tuple(_stripOption(lines[i]) for i in range(start, end + 1))
	above, belowLines = _surroundings(lines, start, end, lastContent)
	return Menu(items=items, selectedIndex=pointerIdx - start,
		context=above[0] if above else None, above=above, below=belowLines)


def _findRadioMenu(lines, lastContent, requireBottom):
	"""Radio-glyph menus with no pointer: the selection is the single
	filled circle among hollow ones, behind a box border (clack style,
	as drawn by create-vite and friends)."""
	stripped = [_stripBox(ln) for ln in lines]
	selIdx = None
	for i in range(lastContent, -1, -1):
		if _RADIO_SEL_RE.match(stripped[i]):
			selIdx = i
			break
	if selIdx is None:
		return None

	def isRadio(i):
		return bool(_RADIO_SEL_RE.match(stripped[i])
			or _RADIO_UNSEL_RE.match(stripped[i]))

	start = selIdx
	while start > 0 and isRadio(start - 1):
		start -= 1
	end = selIdx
	while end < lastContent and isRadio(end + 1):
		end += 1
	if end - start + 1 < 2:
		return None
	selCount = sum(
		1 for i in range(start, end + 1) if _RADIO_SEL_RE.match(stripped[i]))
	if selCount != 1:
		return None
	if requireBottom:
		below = sum(
			1 for i in range(end + 1, lastContent + 1) if stripped[i].strip())
		if below > _RADIO_MAX_BELOW:
			return None
	items = []
	for i in range(start, end + 1):
		m = _RADIO_SEL_RE.match(stripped[i]) or _RADIO_UNSEL_RE.match(stripped[i])
		items.append(m.group(1).rstrip())
	above, belowLines = _surroundings(lines, start, end, lastContent)
	return Menu(items=tuple(items), selectedIndex=selIdx - start,
		context=above[0] if above else None, above=above, below=belowLines)


def findMenu(lines, requireBottom=True):
	"""Detect an active interactive menu in terminal buffer lines.

	Tries pointer-marker menus first (inquirer family), then radio-glyph
	menus (clack family).  Returns a Menu or None.
	"""
	if not lines:
		return None
	lines = [ln.rstrip("\r") for ln in lines]
	lastContent = len(lines) - 1
	while lastContent >= 0 and not lines[lastContent].strip():
		lastContent -= 1
	if lastContent < 0:
		return None
	menu = _findArrowMenu(lines, lastContent, requireBottom)
	if menu is None:
		menu = _findRadioMenu(lines, lastContent, requireBottom)
	return menu


_BOX_PREFIX_RE = re.compile(
	r"^(?:[○◯●◉]|\((?:[xX*•●◉ ])?\)|\[(?:[xX* ])?\])\s+")


def normalizeItem(item):
	"""Strip a leading radio/checkbox glyph so toggling an option does not
	make it look like a different item ("○ mango" == "● mango")."""
	return _BOX_PREFIX_RE.sub("", item)


def isBareMarker(text):
	"""True when the text is nothing but pointer-marker glyphs or box
	borders (repaints leak the marker column or a frame edge on their
	own, e.g. "»" or "└")."""
	stripped = text.strip()
	return bool(stripped) and all(
		ch in ">❯›→▸»│┃┆┇╎└┘┌┐├┤─╭╮╯╰.…‥ \t" for ch in stripped)


def matchesFlattenedDiff(text, knownItems):
	"""True when a line looks like a flattened partial repaint: a known
	item immediately followed by a pointer marker ("GOLF-1 apple> GOLF-2
	banana").  VS Code live regions join the two rewritten lines without a
	newline, so the marker loses its leading whitespace and escapes the
	normal relevance probe."""
	if not knownItems:
		return False
	markers = ">❯›→▸»"
	for ln in text.split("\n"):
		ln = ln.strip()
		for item in knownItems:
			if ln.startswith(item):
				rest = ln[len(item):].lstrip()
				if rest[:1] in markers:
					return True
	return False


def looksRelevant(text, knownItems=None):
	"""Cheap gate: could this announcement be menu-related?

	True when the text contains a pointer/selection marker anywhere
	(flattened announcements included), or when one of its stripped lines
	exactly equals a known menu item (catches the bare caret-line
	announcements NVDA makes on every arrow press).
	"""
	if RELEVANCE_RE.search(text):
		return True
	if isBareMarker(text):
		return True
	if knownItems:
		normKnown = {normalizeItem(i) for i in knownItems}
		for ln in text.split("\n"):
			stripped = ln.strip()
			if stripped in knownItems or normalizeItem(stripped) in normKnown:
				return True
		if matchesFlattenedDiff(text, knownItems):
			return True
	return False
