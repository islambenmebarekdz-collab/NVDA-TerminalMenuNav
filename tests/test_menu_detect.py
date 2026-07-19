# -*- coding: UTF-8 -*-
# Unit tests for menuDetect, runnable with plain Python (no NVDA needed):
#   python tests/test_menu_detect.py
# Buffers below reproduce the real states captured in the NVDA speech log
# during the diagnostic session of 2026-07-11 (menu_test.py, styles A/B/C).

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	"addon", "globalPlugins", "terminalMenuNav"))

import menuDetect  # noqa: E402

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
	global PASS, FAIL
	if condition:
		PASS += 1
		print(f"  ok: {name}")
	else:
		FAIL += 1
		print(f"FAIL: {name} {detail}")


# --- style A: full-block frame, pointer on option 2 (after one down) -----
bufferA = [
	"PS C:\\Users\\benme> python menu_test.py",
	"MENU-A-BEGIN use arrows then Enter (Esc to skip)",
	"  GOLF-1 apple",
	"> GOLF-2 banana",
	"  GOLF-3 cherry",
	"  GOLF-4 date",
	"  GOLF-5 elderberry",
	"",
]
m = menuDetect.findMenu(bufferA)
check("style A: menu detected", m is not None)
if m:
	check("style A: 5 items", len(m.items) == 5, str(m.items))
	check("style A: banana selected (index 1)", m.selectedIndex == 1)
	check("style A: item text stripped", m.items[1] == "GOLF-2 banana")
	check("style A: context is the prompt line",
		m.context == "MENU-A-BEGIN use arrows then Enter (Esc to skip)")

# --- finished menu pushed up by result lines: must NOT be active ----------
bufferFinished = [
	"  GOLF-1 apple",
	"  GOLF-2 banana",
	"> GOLF-3 cherry",
	"  GOLF-4 date",
	"  GOLF-5 elderberry",
	"MENU-A-RESULT chose GOLF-3 cherry",
	">>> Press Enter to start menu style B <<<",
	"",
]
check("finished menu (2 lines below): ignored",
	menuDetect.findMenu(bufferFinished) is None)

# --- one trailing line below the block is tolerated (footer/hint) --------
bufferHint = [
	"Pick a fruit:",
	"> GOLF-1 apple",
	"  GOLF-2 banana",
	"  GOLF-3 cherry",
	"(Use arrow keys)",
]
m = menuDetect.findMenu(bufferHint)
check("menu with one footer line: detected", m is not None)
if m:
	check("footer menu: apple selected", m.selectedIndex == 0)

# --- no menu at all --------------------------------------------------------
bufferPlain = [
	"PS C:\\Users\\benme> dir",
	"    Directory: C:\\Users\\benme",
	"Mode                 LastWriteTime         Length Name",
	"----                 -------------         ------ ----",
	"d-----         11/07/2026     18:00                TerminalTest",
	"PS C:\\Users\\benme>",
]
check("plain output: no menu", menuDetect.findMenu(bufferPlain) is None)

# --- ">>>" banners are not pointers ---------------------------------------
bufferBanner = [
	"MENU-TEST-SESSION-BEGIN",
	"Three menu styles will appear one after another.",
	"In each: press down arrow 3 times, up arrow once, then Enter.",
	">>> Press Enter to start menu style A <<<",
]
check("'>>>' banner: no menu", menuDetect.findMenu(bufferBanner) is None)

# --- a lone '>' line with no option block around it ------------------------
bufferLone = [
	"some output",
	"> quoted reply line",
	"PS C:\\Users\\benme>",
]
check("lone pointer without block: no menu",
	menuDetect.findMenu(bufferLone) is None)

# --- unicode pointer and radio forms ---------------------------------------
bufferUnicode = [
	"? Select a package manager",
	"  ( ) npm",
	"❯ (x) pnpm",
	"  ( ) yarn",
]
m = menuDetect.findMenu(bufferUnicode)
check("unicode pointer: detected", m is not None)
if m:
	check("unicode pointer: index 1", m.selectedIndex == 1)
	check("unicode pointer: 3 items", len(m.items) == 3)
	check("unicode pointer: question as context",
		m.context == "? Select a package manager")

# --- exactly one pointer required ------------------------------------------
bufferTwoPointers = [
	"> GOLF-1 apple",
	"> GOLF-2 banana",
	"  GOLF-3 cherry",
]
check("two pointers: rejected", menuDetect.findMenu(bufferTwoPointers) is None)

# --- old finished frame above an active one: last pointer wins --------------
bufferTwoMenus = [
	"  GOLF-1 apple",
	"  GOLF-2 banana",
	"> GOLF-3 cherry",
	"  GOLF-4 date",
	"  GOLF-5 elderberry",
	"MENU-A-RESULT chose GOLF-3 cherry",
	"MENU-B-BEGIN use arrows then Enter (Esc to skip)",
	"> GOLF-1 apple",
	"  GOLF-2 banana",
	"  GOLF-3 cherry",
	"  GOLF-4 date",
	"  GOLF-5 elderberry",
	"",
]
m = menuDetect.findMenu(bufferTwoMenus)
check("two frames: active one found", m is not None)
if m:
	check("two frames: apple selected", m.selectedIndex == 0)

# --- relevance gate ----------------------------------------------------------
check("relevance: flattened block with pointer",
	menuDetect.looksRelevant(
		"MENU-A-BEGIN use arrows then Enter (Esc to skip) > GOLF-1 apple "
		"GOLF-2 banana GOLF-3 cherry"))
check("relevance: bare caret line matches known items",
	menuDetect.looksRelevant("  GOLF-5 elderberry",
		knownItems={"GOLF-1 apple", "GOLF-5 elderberry"}))
check("relevance: result line does not match",
	not menuDetect.looksRelevant("MENU-A-RESULT chose GOLF-3 cherry",
		knownItems={"GOLF-3 cherry"}))
check("relevance: plain text rejected",
	not menuDetect.looksRelevant("hello world, nothing here"))
check("relevance: '>>>' banner rejected",
	not menuDetect.looksRelevant(">>> Press Enter to start menu style B <<<"))

# --- clack/create-vite radio frame (real npm test, 2026-07-13) --------------
bufferVite = [
	"PS C:\\Users\\benme> npm create vite@latest",
	"◇  Project name:",
	"│  test1",
	"│",
	"◆  Select a framework:",
	"│  ● Vanilla",
	"│  ○ Vue",
	"│  ○ React",
	"│  ○ Preact",
	"│  ○ Lit",
	"│  ○ Svelte",
	"│  ...",
	"│  ↑/↓ to navigate • Enter: confirm",
	"└",
]
m = menuDetect.findMenu(bufferVite)
check("vite radio menu: detected", m is not None)
if m:
	check("vite: 6 visible items", len(m.items) == 6, str(m.items))
	check("vite: Vanilla selected", m.selectedIndex == 0)
	check("vite: glyph stripped from item", m.items[1] == "Vue")
	check("vite: step question as context",
		m.context == "◆  Select a framework:")
	check("vite: hint footer captured for gating",
		"↑/↓ to navigate • Enter: confirm" in m.below)

# scrolled viewport: "..." above and below, selection mid-window
bufferViteScroll = bufferVite[:5] + [
	"│  ...",
	"│  ○ React",
	"│  ○ Preact",
	"│  ○ Lit",
	"│  ● Svelte",
	"│  ○ Solid",
	"│  ...",
	"│  ↑/↓ to navigate • Enter: confirm",
	"└",
]
m = menuDetect.findMenu(bufferViteScroll)
check("vite scrolled: detected", m is not None)
if m:
	check("vite scrolled: Svelte selected (4 of 5 visible)",
		(m.selectedIndex, len(m.items)) == (3, 5))

# multiple filled circles (a checkbox summary, not a radio menu): rejected
bufferMultiSel = [
	"│  ● kiwi",
	"│  ● mango",
	"│  ○ lemon",
]
check("two filled circles: rejected",
	menuDetect.findMenu(bufferMultiSel) is None)

# bare box border and marker column leaks
check("bare border '└': bare marker", menuDetect.isBareMarker("└"))
check("bare pointer '»': bare marker", menuDetect.isBareMarker("» "))
check("real text: not bare marker",
	not menuDetect.isBareMarker("> real option"))

# --- inline horizontal radio (clack Yes/No, real vite log) -------------------
bufferYesNo = [
	"◇  Which linter to use?",
	"│  Oxlint",
	"│",
	"◆  Install with npm and start now?",
	"│  ● Yes / ○ No",
	"└",
]
m = menuDetect.findMenu(bufferYesNo)
check("inline Yes/No: detected", m is not None)
if m:
	check("inline Yes/No: two items", len(m.items) == 2, str(m.items))
	check("inline Yes/No: Yes selected", m.selectedIndex == 0)
	check("inline Yes/No: separator stripped", m.items == ("Yes", "No"))
	check("inline Yes/No: question as context",
		m.context == "◆  Install with npm and start now?")

bufferNoSel = ["◆  Question?", "│  ● A / ● B", "└"]
check("inline two filled: rejected", menuDetect.findMenu(bufferNoSel) is None)
bufferProse = ["some output with ● in prose and more text", "PS> "]
check("prose with circle: rejected", menuDetect.findMenu(bufferProse) is None)

# --- input line extraction ----------------------------------------------------
bufferInput = [
	"◆  Project name:",
	"│  tes█",
	"└",
]
check("input line: extracted text", menuDetect.findInputLine(bufferInput) == "tes")
check("input line: none without cursor",
	menuDetect.findInputLine(["│  test1", "└"]) is None)

# --- windows CRLF endings ------------------------------------------------------
bufferCRLF = [ln + "\r" for ln in bufferA]
m = menuDetect.findMenu(bufferCRLF)
check("CRLF buffer: detected", m is not None and m.selectedIndex == 1)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
