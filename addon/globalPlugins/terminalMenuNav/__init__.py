# -*- coding: UTF-8 -*-
# TerminalMenuNav — NVDA global plugin.
# Makes interactive CLI menus (inquirer-style option lists redrawn with
# ANSI escapes) usable with speech: instead of re-reading the whole
# repainted block plus a misleading cursor line on every arrow press, it
# announces only the currently pointed option and its position.
#
# Strategy ("read the state, not the event"): new-text announcements are
# used only as a trigger.  On each candidate announcement the full visible
# terminal buffer is read and the menu block is located there, so the
# result stays correct no matter how the tool repaints (full block,
# partial lines, or anything else).
#
# Author: Islam Benmebarek <islam.benmebarek.dz@gmail.com>
# License: GPL v2

import time

import api
import config
import controlTypes
import core
import globalPluginHandler
import speech
import textInfos
import ui
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel, NVDASettingsDialog
from logHandler import log
from scriptHandler import script
from speech.extensions import filter_speechSequence

from . import menuDetect

# NVDA substitutes the translated word "blank" for empty text BEFORE the
# speech filter runs, so blank caret echoes arrive as that word, not as an
# empty sequence.  Capture NVDA's core translation now, while ``_`` is
# still NVDA's own gettext (initTranslation below rebinds it to ours).
try:
	_CORE_BLANK = _("blank")
except NameError:
	_CORE_BLANK = "blank"

try:
	import addonHandler
	addonHandler.initTranslation()
except BaseException:
	# Fall back to NVDA's builtin gettext so ``_`` stays defined.
	pass

try:
	_ROLE_TERMINAL = controlTypes.Role.TERMINAL
except AttributeError:
	_ROLE_TERMINAL = controlTypes.ROLE_TERMINAL

# Fallback defaults used if the config spec has not been applied yet.
_DEFAULTS = {
	"enabled": True,
	"announcePosition": True,
}

config.conf.spec["terminalMenuNav"] = {
	"enabled": "boolean(default=true)",
	# Append "N of M" after the selected option text.
	"announcePosition": "boolean(default=true)",
}


def _getCfg(key):
	"""Read an option, surviving a not-yet-applied config spec."""
	try:
		return config.conf["terminalMenuNav"][key]
	except KeyError:
		return _DEFAULTS[key]


def _setCfg(key, value):
	config.conf["terminalMenuNav"][key] = value


class TerminalMenuNavPanel(SettingsPanel):
	# Translators: title of the add-on settings category in NVDA settings.
	title = _("Terminal Menu Navigator")

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: label of a checkbox in the add-on settings.
		self.enabledCheck = sHelper.addItem(
			wx.CheckBox(self, label=_("&Filter interactive menu announcements "
				"in terminals")))
		self.enabledCheck.SetValue(_getCfg("enabled"))
		# Translators: label of a checkbox in the add-on settings.
		self.positionCheck = sHelper.addItem(
			wx.CheckBox(self, label=_("Announce the option's &position "
				"(for example: 3 of 5)")))
		self.positionCheck.SetValue(_getCfg("announcePosition"))

	def onSave(self):
		_setCfg("enabled", self.enabledCheck.IsChecked())
		_setCfg("announcePosition", self.positionCheck.IsChecked())


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: category shown in NVDA Input gestures dialog.
	scriptCategory = _("Terminal Menu Navigator")

	# Repaints and their announcements arrive as a burst spread over a few
	# tens of milliseconds, sometimes BEFORE the buffer finishes updating.
	# Triggers only restart this timer; the state is read and spoken once
	# after the burst settles, so the announcement can never lag a key
	# press behind the real selection.
	_DEBOUNCE_MS = 60

	def __init__(self):
		super().__init__()
		# (selectedIndex, items) of the last announcement, for deduping the
		# caret-line + repaint-diff double announcements per key press.
		self._lastKey = None
		# Last detected menu; its items let us recognize the bare
		# caret-line announcements (which carry no pointer marker).
		self._lastMenu = None
		self._timer = None
		# Texts swallowed since the last state read; re-spoken if the read
		# finds no menu (fail open: a false-positive gate must never cost
		# the user real output).
		self._swallowed = []
		# Current text of the active clack input field, for the deletion
		# echo (None when no input field is active).
		self._lastInputText = None
		# When a menu was last seen in the buffer; blank caret echoes
		# within this window are navigation noise, not content.
		self._lastMenuTime = 0.0
		# Guards our own ui.message calls from being re-filtered.
		self._selfSpeaking = False
		filter_speechSequence.register(self._filterSpeech)
		self._panelRegistered = False
		try:
			NVDASettingsDialog.categoryClasses.append(TerminalMenuNavPanel)
			self._panelRegistered = True
		except Exception:
			pass

	def terminate(self):
		self._cancelTimer()
		try:
			filter_speechSequence.unregister(self._filterSpeech)
		except Exception:
			pass
		if self._panelRegistered:
			try:
				NVDASettingsDialog.categoryClasses.remove(TerminalMenuNavPanel)
			except Exception:
				pass
		super().terminate()

	# -- focus tracking -----------------------------------------------------
	def event_gainFocus(self, obj, nextHandler):
		# New context: forget menu state so stale items from another window
		# can never gate or suppress speech here.
		self._lastKey = None
		self._lastMenu = None
		self._lastInputText = None
		nextHandler()

	# -- terminal identification ---------------------------------------------
	def _isTerminal(self, obj):
		if obj is None:
			return False
		try:
			if obj.role == _ROLE_TERMINAL:
				return True
		except Exception:
			return False
		# VS Code's integrated terminal is a Chromium text area, not a
		# TERMINAL-role object; recognize it by app + accessible name.
		try:
			appName = obj.appModule.appName
		except Exception:
			return False
		if appName == "code":
			try:
				name = obj.name or ""
			except Exception:
				name = ""
			return "erminal" in name
		return False

	# -- buffer access --------------------------------------------------------
	# Only the bottom of the buffer matters (active menus live at the
	# cursor); capping what we hand to the detector keeps the filter cheap
	# even with huge scrollbacks.
	_MAX_SCAN_LINES = 200

	def _getTerminalLines(self, obj):
		try:
			ti = obj.makeTextInfo(textInfos.POSITION_ALL)
			text = ti.text
		except Exception:
			return None
		if not text or not text.strip():
			return None
		return text.split("\n")[-self._MAX_SCAN_LINES:]

	# -- announcement building -------------------------------------------------
	def _formatAnnouncement(self, menu):
		item = menu.items[menu.selectedIndex]
		if _getCfg("announcePosition"):
			# Translators: spoken for a terminal menu option; {item} is the
			# option text, {position}/{count} its place in the list.
			return _("{item}, {position} of {count}").format(
				item=item, position=menu.selectedIndex + 1,
				count=len(menu.items))
		return item

	# -- the speech filter -------------------------------------------------------
	def _filterSpeech(self, value):
		# A speech filter must never break speech: any internal failure
		# returns the original sequence untouched.
		try:
			return self._doFilter(value)
		except Exception:
			log.debugWarning("TerminalMenuNav filter error", exc_info=True)
			return value

	def _doFilter(self, value):
		if self._selfSpeaking or not _getCfg("enabled"):
			return value
		focus = api.getFocusObject()
		if not self._isTerminal(focus):
			return value
		texts = [part for part in value if isinstance(part, str)]
		joined = "\n".join(texts).strip()
		if not joined or joined == _CORE_BLANK:
			# Blank caret echoes ride along with every arrow press while a
			# menu is active ("blank" between announcements): silence them
			# for the duration of the menu session only.
			if self._lastMenu is not None \
					and time.time() - self._lastMenuTime < 2.0:
				return []
			return value
		# While a clack input field is active, box-border frame echoes
		# (including the bare placeholder repaint when the field empties)
		# belong to the field, not to the output.
		if self._lastInputText is not None \
				and joined.startswith(("│", "┃")):
			self._swallowed.append(joined)
			self._scheduleStateRead()
			return []
		knownItems = set(self._lastMenu.items) if self._lastMenu else None
		# Lines around the menu (the question above, hint footers below)
		# leak as stray caret events on some repaints (style-C wrap-around,
		# the questionary checkbox, clack's "↑/↓ to navigate" footer); they
		# belong to the menu too, so gate them alongside the items.
		isContextEcho = False
		if self._lastMenu:
			nearby = set(self._lastMenu.above) | set(self._lastMenu.below)
			stripped = joined.strip()
			isContextEcho = (stripped in nearby
				or menuDetect._stripBox(stripped).strip() in nearby)
		# Input-field redraw echoes carry the block cursor ("│ te█"); NVDA's
		# own character echo already voices what was typed, so these are
		# pure noise — swallow them and let the state read handle deletion.
		isInputEcho = menuDetect.INPUT_CURSOR in joined
		if not isInputEcho and not isContextEcho \
				and not menuDetect.looksRelevant(joined, knownItems):
			return value
		# Menu-related burst: swallow the noisy trigger now, read the real
		# state once the repaint settles.  Bare markers/borders ("»", "└")
		# are never meaningful on their own, so they are exempt from the
		# fail-open re-speak; cursor-bearing texts stay on it, so progress
		# bars (runs of the same block glyph) are given back verbatim when
		# the state read finds no real input field.
		if not menuDetect.isBareMarker(joined):
			self._swallowed.append(joined)
		self._scheduleStateRead()
		# Low-latency path: if the repaint has already settled, a coherent
		# menu with a NEW selection is visible right now — announce it
		# immediately instead of waiting out the debounce.  A stale or
		# mid-repaint buffer yields no menu or the old key, and the
		# debounced read stays as the correctness net.
		lines = self._getTerminalLines(focus)
		menu = menuDetect.findMenu(lines) if lines else None
		if menu is not None and (menu.selectedIndex, menu.items) != self._lastKey:
			self._swallowed = []
			self._announceMenu(menu)
		return []

	# -- debounced state read ---------------------------------------------------
	def _cancelTimer(self):
		if self._timer is not None:
			try:
				self._timer.Stop()
			except Exception:
				pass
			self._timer = None

	def _scheduleStateRead(self):
		self._cancelTimer()
		self._timer = core.callLater(self._DEBOUNCE_MS, self._announceState)

	def _announceState(self):
		self._timer = None
		swallowed = self._swallowed
		self._swallowed = []
		focus = api.getFocusObject()
		if not self._isTerminal(focus):
			return
		# State over event: the buffer is authoritative.
		lines = self._getTerminalLines(focus)
		menu = menuDetect.findMenu(lines) if lines else None
		# Active text-input field: track its text and voice deletions.
		inputText = menuDetect.findInputLine(lines) if lines else None
		prevInput = self._lastInputText
		if menu is None and inputText is not None:
			self._lastInputText = inputText
			if prevInput is not None and len(inputText) < len(prevInput) \
					and prevInput.startswith(inputText):
				# Backspace: voice what was removed (typing itself is
				# already echoed by NVDA's own character echo).
				self._speak(prevInput[len(inputText):])
			return
		if menu is None and prevInput is not None and lines \
				and menuDetect.hasActiveInputStep(lines):
			# The block cursor vanished but the step is still active: the
			# field emptied back to its placeholder.  Voice the deleted
			# remainder and keep tracking from the empty string.
			self._lastInputText = ""
			if prevInput:
				self._speak(prevInput)
			return
		self._lastInputText = None
		if menu is None and swallowed:
			# Buffer unavailable: best-effort parse of what was swallowed,
			# which keeps line structure outside VS Code's live regions.
			menu = menuDetect.findMenu(
				"\n".join(swallowed).split("\n"), requireBottom=False)
		if menu is None:
			# The gate misfired on ordinary output: give it back verbatim.
			self._lastKey = None
			if swallowed:
				self._speak(" ".join(swallowed))
			return
		self._announceMenu(menu)

	def _announceMenu(self, menu):
		"""Update menu state and speak the selection if it changed."""
		self._lastMenuTime = time.time()
		key = (menu.selectedIndex, menu.items)
		# Same question ⇒ same menu: keeps the context from being
		# re-announced when a scrolling viewport (clack's "...") changes
		# the visible items.  Without a shared question, compare items
		# with radio/checkbox glyphs stripped, so toggling "○ mango" to
		# "● mango" with Space is not a "new" menu either.
		if self._lastMenu is None:
			isNewMenu = True
		elif menu.context and menu.context == self._lastMenu.context:
			isNewMenu = False
		else:
			isNewMenu = (
				tuple(menuDetect.normalizeItem(i) for i in menu.items)
				!= tuple(menuDetect.normalizeItem(i) for i in self._lastMenu.items))
		self._lastMenu = menu
		if key == self._lastKey:
			# Echo of an already-announced state: stay silent.
			return
		self._lastKey = key
		announcement = self._formatAnnouncement(menu)
		if isNewMenu and menu.context:
			# First time this menu shows up: keep the question/prompt line
			# that sits above the options, then the selection.
			announcement = menu.context + ". " + announcement
		# Navigating: the previous item's speech is stale — cut it, like
		# native list boxes do.
		try:
			speech.cancelSpeech()
		except Exception:
			pass
		self._speak(announcement)

	def _speak(self, text):
		self._selfSpeaking = True
		try:
			ui.message(text)
		finally:
			self._selfSpeaking = False

	# -- scripts ---------------------------------------------------------------
	@script(
		# Translators: description for the toggle command.
		description=_("Toggles filtering of interactive menu announcements "
			"in terminals"),
		gesture="kb:NVDA+alt+l",
	)
	def script_toggleFiltering(self, gesture):
		newVal = not _getCfg("enabled")
		_setCfg("enabled", newVal)
		if newVal:
			# Translators: reported when the feature is turned on.
			ui.message(_("Menu filtering on"))
		else:
			self._cancelTimer()
			self._swallowed = []
			self._lastKey = None
			self._lastMenu = None
			self._lastInputText = None
			# Translators: reported when the feature is turned off.
			ui.message(_("Menu filtering off"))

	@script(
		# Translators: description for the announce-current command.
		description=_("Announces the currently selected option of the "
			"terminal menu"),
		gesture="kb:NVDA+alt+k",
	)
	def script_announceCurrent(self, gesture):
		focus = api.getFocusObject()
		menu = None
		if self._isTerminal(focus):
			lines = self._getTerminalLines(focus)
			if lines:
				menu = menuDetect.findMenu(lines)
		if menu is None:
			menu = self._lastMenu
		if menu is None:
			# Translators: reported when no interactive menu is found.
			ui.message(_("No menu detected"))
			return
		self._lastMenu = menu
		announcement = self._formatAnnouncement(menu)
		if menu.context:
			# On demand, remind the user of the question too (its live
			# echoes are gated, so this is where it stays reachable).
			announcement += ". " + menu.context
		ui.message(announcement)
