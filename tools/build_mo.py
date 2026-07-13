# -*- coding: UTF-8 -*-
# Compiles every addon/locale/*/LC_MESSAGES/nvda.po into nvda.mo.
# Minimal msgfmt replacement (no plurals, no multiline msgids) so the
# build has zero external dependencies.
#   python tools/build_mo.py

import glob
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ENTRY_RE = re.compile(
	r'msgid\s+((?:"(?:[^"\\]|\\.)*"\s*)+)\s*msgstr\s+((?:"(?:[^"\\]|\\.)*"\s*)+)',
	re.MULTILINE)
_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _joinParts(block):
	out = ""
	for part in _STR_RE.findall(block):
		out += part.encode("latin-1", "backslashreplace").decode(
			"unicode_escape")
	return out


def parsePo(path):
	with open(path, encoding="utf-8") as f:
		# Strip comment lines; the entry regex then sees clean pairs.
		text = "\n".join(
			ln for ln in f.read().split("\n") if not ln.startswith("#"))
	catalog = {}
	for m in _ENTRY_RE.finditer(text):
		msgid = _joinParts(m.group(1))
		msgstr = _joinParts(m.group(2))
		if msgstr:
			catalog[msgid] = msgstr
	return catalog


def writeMo(catalog, path):
	keys = sorted(catalog.keys())
	ids = b""
	strs = b""
	offsets = []
	for k in keys:
		kb = k.encode("utf-8")
		vb = catalog[k].encode("utf-8")
		offsets.append((len(ids), len(kb), len(strs), len(vb)))
		ids += kb + b"\x00"
		strs += vb + b"\x00"
	n = len(keys)
	keyStart = 28 + 16 * n
	valStart = keyStart + len(ids)
	kOffsets = []
	vOffsets = []
	for o1, l1, o2, l2 in offsets:
		kOffsets += [l1, o1 + keyStart]
		vOffsets += [l2, o2 + valStart]
	data = struct.pack("Iiiiiii", 0x950412DE, 0, n, 28, 28 + 8 * n, 0, 0)
	data += struct.pack("i" * len(kOffsets), *kOffsets)
	data += struct.pack("i" * len(vOffsets), *vOffsets)
	data += ids + strs
	with open(path, "wb") as f:
		f.write(data)


def main():
	poFiles = glob.glob(os.path.join(
		ROOT, "addon", "locale", "*", "LC_MESSAGES", "nvda.po"))
	if not poFiles:
		print("No .po files found")
		return 1
	for po in poFiles:
		catalog = parsePo(po)
		mo = po[:-3] + ".mo"
		writeMo(catalog, mo)
		print(f"Compiled {po} -> {mo} ({len(catalog)} messages)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
