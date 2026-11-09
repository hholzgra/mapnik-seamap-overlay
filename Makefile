.PHONY: check icons taginfo

check:
	pre-commit run --all-files

# 16x16 PNG versions of all SVG symbols for taginfo.json
icons:
	tools/svg2png-icons.py

taginfo: icons
	tools/make-taginfo.py
