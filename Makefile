# pi-Stomp: the checks of this repository.
#
# Each target finds its own files. Do not write a file name here and do not
# write a file name in .github/workflows/ci.yml. A new test must run without a
# change to this file.
#
# Note for the packaging: debian/rules in pi-gen-pistomp overrides every
# dh_auto_* step, so debhelper does not run these targets.

PYTHON ?= python3
NODE ?= node

# The server files that must compile. py_compile reads one file at a time, so
# this list is not test discovery; it is a syntax gate on the files that the
# device runs first.
PY_COMPILE_FILES = mod/host.py mod/session.py mod/webserver.py mod/sfzbuilder.py setup.py

# unittest discover reads every test*.py file under test/.
# node --test finds every *.test.js file below the directory that it runs in.
# The recipe changes to JS_TEST_DIR first, because a directory that you give to
# node --test as an argument is read as a file, and a glob needs a new version
# of node. This form works with node 18 and later.
JS_TEST_DIR = test/js

.PHONY: test test-py test-js typecheck smoke compile utils clean-utils help

## test: run every check
test: compile test-py test-js typecheck smoke

## compile: check that the server files parse
compile:
	$(PYTHON) -m py_compile $(PY_COMPILE_FILES)

## test-py: run every Python test under test/
test-py:
	$(PYTHON) -m unittest discover -s test -v

## test-js: run every JavaScript test under test/js/
test-js:
	cd $(JS_TEST_DIR) && $(NODE) --test

## typecheck: check the JSDoc types of the islands
typecheck:
	npx -y -p typescript@5 tsc --noEmit

## smoke: draw the SFZ builder in headless Chrome and check what it drew
smoke:
	./test/browser/run.sh

## utils: build libmod_utils.so
utils:
	$(MAKE) -C utils

## clean-utils: remove the build of libmod_utils.so
clean-utils:
	$(MAKE) -C utils clean

## help: show the targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
