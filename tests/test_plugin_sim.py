# -*- coding: UTF-8 -*-
# Integration simulation: stubs NVDA's modules, imports the real plugin,
# and replays announcement sequences captured in the NVDA logs of the
# 2026-07-11 diagnostic and 2026-07-13 live-test sessions — including the
# one-keypress-lag race found in styles B/C. Run:
#   python tests/test_plugin_sim.py

import builtins
import os
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---- NVDA module stubs -------------------------------------------------------


def _mod(name, **attrs):
	m = types.ModuleType(name)
	for k, v in attrs.items():
		setattr(m, k, v)
	sys.modules[name] = m
	return m


class _Conf(dict):
	def __init__(self):
		super().__init__()
		self.spec = {}


_config = _mod("config")
_config.conf = _Conf()
_config.conf["terminalMenuNav"] = {"enabled": True, "announcePosition": True}

_api = _mod("api")
_api.getFocusObject = lambda: None  # replaced by the test

_Role = types.SimpleNamespace(TERMINAL="TERMINAL")
_mod("controlTypes", Role=_Role)

_mod("globalPluginHandler", GlobalPlugin=type("GlobalPlugin", (), {
	"__init__": lambda self: None, "terminate": lambda self: None}))

_mod("textInfos", POSITION_ALL="all")
_messages = []
_mod("ui", message=_messages.append)
_mod("wx", CheckBox=object)
_gui = _mod("gui", guiHelper=types.SimpleNamespace())
_mod("gui.settingsDialogs",
	SettingsPanel=type("SettingsPanel", (), {}),
	NVDASettingsDialog=types.SimpleNamespace(categoryClasses=[]))
_gui.settingsDialogs = sys.modules["gui.settingsDialogs"]
_mod("logHandler", log=types.SimpleNamespace(
	debugWarning=lambda *a, **k: None))
_mod("scriptHandler", script=lambda **kw: (lambda f: f))


class _FakeTimer:
	def __init__(self, func):
		self.func = func
		self.stopped = False

	def Stop(self):
		self.stopped = True


_pendingTimers = []


def _callLater(ms, func, *args):
	t = _FakeTimer(lambda: func(*args))
	_pendingTimers.append(t)
	return t


def _fireTimers():
	"""Run pending timers (skipping cancelled ones), like the wx loop."""
	global _pendingTimers
	timers, _pendingTimers = _pendingTimers, []
	for t in timers:
		if not t.stopped:
			t.func()


_mod("core", callLater=_callLater)


class _Filter:
	def __init__(self):
		self.handlers = []

	def register(self, h):
		self.handlers.append(h)

	def unregister(self, h):
		self.handlers.remove(h)


_speech = _mod("speech")
_speechExt = _mod("speech.extensions", filter_speechSequence=_Filter())
_speech.extensions = _speechExt


def _initTranslation():
	builtins._ = lambda s: s


_mod("addonHandler", initTranslation=_initTranslation)

# ---- import the real plugin ---------------------------------------------------

sys.path.insert(0, os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	"addon", "globalPlugins"))
import terminalMenuNav  # noqa: E402

plugin = terminalMenuNav.GlobalPlugin()
filt = _speechExt.filter_speechSequence.handlers[0]

# ---- fake focus object ---------------------------------------------------------


class FakeTerminal:
	role = _Role.TERMINAL
	name = "Terminal"
	appModule = types.SimpleNamespace(appName="windowsterminal")
	bufferText = ""

	def makeTextInfo(self, pos):
		return types.SimpleNamespace(text=self.bufferText)


term = FakeTerminal()
_api.getFocusObject = lambda: term

PASS = 0
FAIL = 0


def check(name, got, expected):
	global PASS, FAIL
	if got == expected:
		PASS += 1
		print(f"  ok: {name}")
	else:
		FAIL += 1
		print(f"FAIL: {name}\n  got:      {got!r}\n  expected: {expected!r}")


def spoken():
	"""Fire timers and return (and clear) captured self-announcements."""
	_fireTimers()
	out = list(_messages)
	_messages.clear()
	return out


FRAME = (
	"PS C:\\Users\\benme> python menu_test.py\n"
	"MENU-A-BEGIN use arrows then Enter (Esc to skip)\n"
	"{o1} GOLF-1 apple\n"
	"{o2} GOLF-2 banana\n"
	"{o3} GOLF-3 cherry\n"
	"{o4} GOLF-4 date\n"
	"{o5} GOLF-5 elderberry\n"
)

# 1) initial render: flattened block trigger is swallowed, debounced read
# announces context + selection.
term.bufferText = FRAME.format(o1=">", o2=" ", o3=" ", o4=" ", o5=" ")
out = filt(["MENU-A-BEGIN use arrows then Enter (Esc to skip) > GOLF-1 apple "
	"GOLF-2 banana GOLF-3 cherry GOLF-4 date GOLF-5 elderberry "])
check("initial trigger swallowed", out, [])
check("initial render: context + selection", spoken(),
	["MENU-A-BEGIN use arrows then Enter (Esc to skip). GOLF-1 apple, 1 of 5"])

# 2) down arrow: caret line + repaint diff both swallowed, ONE announcement.
term.bufferText = FRAME.format(o1=" ", o2=">", o3=" ", o4=" ", o5=" ")
out1 = filt(["  GOLF-5 elderberry"])
out2 = filt(["GOLF-1 apple > GOLF-2 banana GOLF-3 cherry GOLF-4 date "
	"GOLF-5 elderberry "])
check("down: both triggers swallowed", (out1, out2), ([], []))
check("down: single correct announcement", spoken(), ["GOLF-2 banana, 2 of 5"])

# 3) THE RACE (style C bug from the live test): trigger arrives while the
# buffer still shows the OLD state; by the time the timer fires the repaint
# has landed. The announcement must reflect the final state, not lag.
out = filt(["  GOLF-3 cherry"])  # caret trigger, buffer still on banana
check("race: trigger swallowed", out, [])
term.bufferText = FRAME.format(o1=" ", o2=" ", o3=">", o4=" ", o5=" ")
check("race: announces the settled state", spoken(), ["GOLF-3 cherry, 3 of 5"])

# 4) flattened partial-repaint diff (style B/C leak from the live test):
# "item> item" with no whitespace before the marker must now be swallowed.
term.bufferText = FRAME.format(o1=" ", o2=" ", o3=" ", o4=">", o5=" ")
out = filt(["GOLF-3 cherry> GOLF-4 date "])
check("glued diff swallowed", out, [])
check("glued diff: correct announcement", spoken(), ["GOLF-4 date, 4 of 5"])

# 5) duplicate echo of the same state after it was announced: silence.
out = filt(["GOLF-3 cherry> GOLF-4 date "])
check("echo swallowed", out, [])
check("echo: no announcement", spoken(), [])

# 6) Enter: result printed below the frame -> not menu-related, passes
# through immediately and untouched.
term.bufferText = FRAME.format(o1=" ", o2=" ", o3=" ", o4=">", o5=" ") \
	+ "MENU-A-RESULT chose GOLF-4 date\nPS C:\\Users\\benme> \n"
out = filt(["MENU-A-RESULT chose GOLF-4 date "])
check("result line: passes through immediately",
	out, ["MENU-A-RESULT chose GOLF-4 date "])
check("result line: nothing extra spoken", spoken(), [])

# 7) fail open: gate misfires on ordinary output (marker-like text) with no
# menu in the buffer -> the swallowed text is given back.
plugin._lastKey = None
plugin._lastMenu = None
term.bufferText = "PS C:\\Users\\benme> git log\ncommit abc\nPS> \n"
out = filt(["merge branch > feature x"])
check("misfire swallowed first", out, [])
check("misfire: swallowed text re-spoken", spoken(),
	["merge branch > feature x"])

# 8) ordinary speech in the terminal: untouched, no timer scheduled.
out = filt(["PS C:\\Users\\benme> dir"])
check("plain speech: passes through", out, ["PS C:\\Users\\benme> dir"])
check("plain speech: no announcement", spoken(), [])

# 9) non-terminal focus: untouched even with a pointer marker.
class FakeEditor:
	role = "EDITOR"
	name = "readme.md"
	appModule = types.SimpleNamespace(appName="notepad")


_api.getFocusObject = lambda: FakeEditor()
out = filt(["> quoted line from a markdown file"])
check("non-terminal focus: passes through",
	out, ["> quoted line from a markdown file"])

# 10) VS Code terminal recognized by app + name.
class FakeVSCodeTerminal(FakeTerminal):
	role = "EDITABLETEXT"
	name = "Terminal 1, powershell"
	appModule = types.SimpleNamespace(appName="code")


vsterm = FakeVSCodeTerminal()
vsterm.bufferText = FRAME.format(o1=" ", o2=" ", o3=" ", o4=">", o5=" ")
_api.getFocusObject = lambda: vsterm
plugin._lastKey = None
plugin._lastMenu = None
out = filt(["MENU-A-BEGIN use arrows then Enter (Esc to skip) > GOLF-4 date "])
check("VS Code trigger swallowed", out, [])
check("VS Code terminal: detected via app+name", spoken(),
	["MENU-A-BEGIN use arrows then Enter (Esc to skip). GOLF-4 date, 4 of 5"])

# 11) disabled: everything passes through.
_config.conf["terminalMenuNav"]["enabled"] = False
out = filt(["> GOLF-1 apple GOLF-2 banana"])
check("disabled: passes through", out, ["> GOLF-1 apple GOLF-2 banana"])
_config.conf["terminalMenuNav"]["enabled"] = True

# 12) buffer read failure: fallback parses the swallowed multi-line text.
class BrokenTerminal(FakeTerminal):
	def makeTextInfo(self, pos):
		raise RuntimeError("no buffer")


_api.getFocusObject = lambda: BrokenTerminal()
plugin._lastKey = None
plugin._lastMenu = None
out = filt(["? Pick one\n> alpha\n  beta\n  gamma"])
check("broken buffer: trigger swallowed", out, [])
check("broken buffer: fallback announcement", spoken(),
	["? Pick one. alpha, 1 of 3"])

# 13) style-C wrap-around leak (live test 2026-07-13): the question line
# above the menu escapes as a stray caret event; it must be gated so only
# the settled selection is announced.
_api.getFocusObject = lambda: term
plugin._lastKey = None
plugin._lastMenu = None
term.bufferText = FRAME.format(o1=">", o2=" ", o3=" ", o4=" ", o5=" ")
filt(["MENU-A-BEGIN use arrows then Enter (Esc to skip) > GOLF-1 apple "])
spoken()  # establish the menu (and its context) as known
term.bufferText = FRAME.format(o1=" ", o2=" ", o3=" ", o4=" ", o5=">")
out1 = filt(["MENU-A-BEGIN use arrows then Enter (Esc to skip)"])
out2 = filt(["  GOLF-5 elderberry"])
check("context echo swallowed", (out1, out2), ([], []))
check("wrap-around: single correct announcement", spoken(),
	["GOLF-5 elderberry, 5 of 5"])

# 14) NVDA+Alt+K now includes the question line on demand.
_messages.clear()
plugin.script_announceCurrent(None)
check("announce current: item + position + context", list(_messages),
	["GOLF-5 elderberry, 5 of 5. "
		"MENU-A-BEGIN use arrows then Enter (Esc to skip)"])
_messages.clear()

# 15) questionary checkbox replay (real log 2026-07-13): "»" pointer with
# ○/● glyphs; a previous-output line above the question leaks as a stray
# caret event; Space toggles ○→● without it being a "new" menu.
CHECKBOX = (
	"REAL-1-RESULT chose HOTEL-2 blueberry\n"
	"? REAL-2 Pick two fruits (Use arrow keys)\n"
	"{p1} {b1} INDIA-1 kiwi\n"
	"{p2} {b2} INDIA-2 lemon\n"
	"{p3} {b3} INDIA-3 mango\n"
	"{p4} {b4} INDIA-4 nectarine\n"
)
_api.getFocusObject = lambda: term
plugin._lastKey = None
plugin._lastMenu = None
term.bufferText = CHECKBOX.format(
	p1="»", p2=" ", p3=" ", p4=" ", b1="○", b2="○", b3="○", b4="○")
filt(["? REAL-2 Pick two fruits (Use arrow keys) » ○ INDIA-1 kiwi"])
check("checkbox: initial announcement", spoken(),
	["? REAL-2 Pick two fruits (Use arrow keys). ○ INDIA-1 kiwi, 1 of 4"])

# leak of the line above the question on up-arrow wrap:
term.bufferText = CHECKBOX.format(
	p1=" ", p2=" ", p3=" ", p4="»", b1="○", b2="○", b3="○", b4="○")
out1 = filt(["REAL-1-RESULT chose HOTEL-2 blueberry"])
out2 = filt(["  ○ INDIA-4 nectarine"])
check("checkbox: above-line echo swallowed", (out1, out2), ([], []))
check("checkbox: wrap announces settled state", spoken(),
	["○ INDIA-4 nectarine, 4 of 4"])

# bare pointer glyph leak:
out = filt(["» "])
check("bare marker swallowed", out, [])
check("bare marker: silence (state unchanged)", spoken(), [])

# Space toggle: ○→● is the same menu — announce the new state WITHOUT
# re-announcing the question.
term.bufferText = CHECKBOX.format(
	p1=" ", p2=" ", p3=" ", p4="»", b1="○", b2="○", b3="○", b4="●")
out = filt(["● INDIA-4 nectarine "])
check("toggle diff swallowed", out, [])
check("toggle: new state, no context repeat", spoken(),
	["● INDIA-4 nectarine, 4 of 4"])

# 16) create-vite (clack) replay from the real npm log (2026-07-13):
# radio glyphs behind box borders, no arrow pointer, scrolling viewport.
VITE_HEAD = (
	"PS C:\\Users\\benme> npm create vite@latest\n"
	"◇  Project name:\n"
	"│  test1\n"
	"│\n"
	"◆  Select a framework:\n"
)
VITE_TAIL = "│  ...\n│  ↑/↓ to navigate • Enter: confirm\n└\n"
_api.getFocusObject = lambda: term
plugin._lastKey = None
plugin._lastMenu = None
term.bufferText = VITE_HEAD + (
	"│  ● Vanilla\n│  ○ Vue\n│  ○ React\n│  ○ Preact\n│  ○ Lit\n"
	"│  ○ Svelte\n") + VITE_TAIL
out = filt(["│ test1█◇ Project name: │ test1 │ ◆ Select a framework: "
	"│ ● Vanilla │ ○ Vue │ ○ React │ ○ Preact │ ○ Lit │ ○ Svelte │ ... "
	"│ ↑/↓ to navigate • Enter: confirm └ "])
check("vite: initial flattened frame swallowed", out, [])
check("vite: context + selection announced", spoken(),
	["◆  Select a framework:. Vanilla, 1 of 6"])

# down arrow: '└' border leak + flattened repaint, single announcement.
term.bufferText = VITE_HEAD + (
	"│  ○ Vanilla\n│  ● Vue\n│  ○ React\n│  ○ Preact\n│  ○ Lit\n"
	"│  ○ Svelte\n") + VITE_TAIL
out1 = filt(["└"])
out2 = filt(["│ ○ Vanilla │ ● Vue │ ○ React │ ○ Preact │ ○ Lit │ ○ Svelte "
	"│ ... │ ↑/↓ to navigate • Enter: confirm └ "])
check("vite down: border + repaint swallowed", (out1, out2), ([], []))
check("vite down: single announcement, no context repeat", spoken(),
	["Vue, 2 of 6"])

# hint footer stray echo (real leak from the log): gated to silence.
out = filt(["│  ↑/↓ to navigate • Enter: confirm\n"])
check("vite hint echo swallowed", out, [])
check("vite hint echo: silence", spoken(), [])

# viewport scroll: visible items change but the question is the same —
# announce the selection only, without re-announcing the context.
term.bufferText = VITE_HEAD + (
	"│  ...\n│  ○ React\n│  ○ Preact\n│  ○ Lit\n│  ● Svelte\n"
	"│  ○ Solid\n") + VITE_TAIL
out = filt(["│ ... │ ○ React │ ○ Preact │ ○ Lit │ ● Svelte │ ○ Solid │ ... "
	"│ ↑/↓ to navigate • Enter: confirm └ "])
check("vite scroll: repaint swallowed", out, [])
check("vite scroll: selection without context repeat", spoken(),
	["Svelte, 4 of 5"])

# 17) a bare border with NO active menu (clack text-input phase): swallowed
# and NOT re-spoken by the fail-open net — it carries no information.
plugin._lastKey = None
plugin._lastMenu = None
term.bufferText = "PS> npm create vite@latest\n◆  Project name:\n│  test1\n└\n"
_api.getFocusObject = lambda: term
out = filt(["└"])
check("bare border, no menu: swallowed", out, [])
check("bare border, no menu: not re-spoken", spoken(), [])

# 18) our own announcement must not be re-filtered (self-speech guard).
_api.getFocusObject = lambda: term
term.bufferText = FRAME.format(o1=">", o2=" ", o3=" ", o4=" ", o5=" ")
plugin._selfSpeaking = True
out = filt(["GOLF-1 apple, 1 of 5"])
plugin._selfSpeaking = False
check("self speech: passes through", out, ["GOLF-1 apple, 1 of 5"])

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
