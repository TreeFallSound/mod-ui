# Frontend Architecture

Status: in use. The SFZ builder is built this way and continuous integration
holds the rules below.
Branch: `feat/sfzbuilder`.
Date: 2026-09-03. Last change: 2026-09-04.

---

## 1. Purpose

This document gives the design for new frontend code in mod-ui.
It also gives the reasons for the design.
The SFZ builder is the first feature that uses this design.

## 2. Technical names

This document uses these technical names:

- **Legacy code**: the JavaScript files in `html/js/`. This code is in the global scope.
- **Island**: a group of files for one feature. An island has no global names.
- **Seam**: the one point where the legacy code starts an island.
- **Token**: a CSS custom property that holds one design value.
- **Model**: a file that has only pure functions. A model does not touch the DOM.

## 3. The problem

The frontend has 17726 lines of JavaScript in 29 files.
All of this code is in the global scope.
The file `index.html` loads the code with 41 script elements.
The order of these elements is important.

The repository has no module system and no bundler.
It has no JavaScript tests.
It has no continuous integration.
It has no configuration file for a linter, a formatter or a type checker.

These conditions cause four problems:

1. You cannot find the callers of a function, because all names are global.
2. You cannot test the logic, because the logic and the DOM code are in the same functions.
3. You must change `index.html` for each new feature, because that file holds all the markup.
4. The tools cannot help you, because no type checker examines the code.

The team will not rewrite the legacy code.
The file `pedalboard.js` has 3040 lines.
The file `modgui.js` has 2711 lines.
These files must continue to work.

## 4. The proposal

Write each new feature as an island.
Do not change the legacy code.
The legacy code and the islands stay together for a long time.
This is the correct condition. It is not a temporary condition.

These are the seven rules.

### 4.1 Use ES modules. Do not use a bundler

Write islands as ES modules.
The browser loads these modules with the `import` keyword.
Tornado sends JavaScript files with the correct type.

A bundler needs a `package.json` file in the root directory.
A bundler also needs changes to the device package in `pi-gen-pistomp`.
We do not do this work now.
Write the code so that a bundler is easy to add later.

### 4.2 Keep one seam

The legacy code starts an island at one point only.
An island does not read global variables directly.
If an island needs data from the legacy code, write an adapter file.
The adapter is the only file that knows the global names.

### 4.3 Each island makes its own markup

Today the markup is in `index.html`. The JavaScript finds the markup by ID.
This is the reason that `index.html` is very large.

An island gets one empty element from `index.html`.
The island makes all of its other elements.
This rule makes `index.html` smaller with each new feature.

### 4.4 Use JSDoc types and `// @ts-check`

Put `// @ts-check` at the top of each island file.
Write the types in JSDoc comments.
The type checker then finds errors in the editor and in continuous integration.

This method needs no build step.
The files stay as plain JavaScript. The browser loads them directly.
TypeScript gives more, but TypeScript needs a bundler.
A change from JSDoc to TypeScript is mechanical. Do it when a bundler exists.

### 4.5 Use CSS tokens

The file `less/variables.less` has 841 lines.
These are LESS variables. LESS variables are constants. They are gone after the compile.

An island puts its design values in CSS custom properties.
The LESS rules then read these properties.
Custom properties operate at run time. A LESS variable does not exist after the
compile, so nothing can read it and nothing can change it.

Three things follow from that, and they are the reason for the rule:

* One value changes every rule that reads it. The accent of the SFZ builder
  moved from orange to purple in one line.
* A media query, or a class on the panel, can give a token a different value.
  A LESS variable cannot do this at all.
* A test can read a token. See the note on the accent below.

mod-ui is a web page in a browser -- a laptop, and sometimes a tablet or a
phone. It is **not** what the LCD of the pi-stomp shows: that screen belongs to
the `pi-stomp` application, which talks to this server over WebSocket and MIDI
and draws nothing from `html/`. Do not size a panel for that LCD.

Put the tokens on `:root`, not on the root element of the island, and start
every name with the name of the island, for example `--sfz-`.
A token on the island cannot be read outside it, and jQuery UI puts the helper
of a drag on the `body`, which is outside it.
A `var()` that does not resolve makes the whole property invalid, so the helper
of the SFZ builder was black text on nothing.
The prefix is what keeps a token at the root from meeting a legacy name.

A test names a token. A test never names the value of a token.
The smoke test of the SFZ builder held `rgb(242, 148, 70)` in two places, and
both broke on the day the accent changed, although nothing was wrong.
It now reads `--sfz-accent` through a probe element, which also proves the token
reaches the `body`, which is the fault the check was written for.

### 4.6 Keep the model pure. Keep the view thin

Put the calculations in a model file.
The model has no DOM code and no network code.
Test the model with the `node:test` module.

Do not write a unit test for the elements that the view makes.
The cost of these tests is high. The value is low.

Write one smoke test instead. It draws the panel in headless Chrome and asks the
questions that only a browser can answer: the computed style, where the focus
sits, the tab order, and a drag from a list onto a pad.
`test/browser/` holds it and `make smoke` runs it.
This test is cheap because there is one of it, and it has found faults that no
unit test could reach: a stylesheet that did not load, a value that changed the
width of its own control, and a control that the keyboard could not reach.

A check in this test says what it wants, not what the code does today.
When a check fails, read it again before you change the panel. Two checks of the
tab order were themselves wrong: one assumed that pad 1 held controls, and one
let the last pad reach past the grid to the end of the panel.

### 4.7 Make the state explicit

Keep the state in one object.
Change the state with one function.
The view is a function of the state.

This is not a framework. This is approximately 30 lines of code.
The result is one place to write log messages. It is also one place to stop the debugger.

### 4.8 Vendor the dependencies

Do not use npm for browser code.
Do not load a file from a CDN. The device is frequently offline.

If an island needs a third-party library, do these steps:

1. Make sure that the library has an ES module build.
2. Copy the file into `html/js/app/vendor/`.
3. Write the version and the source URL in a comment at the top of the file.
4. Import the file with a relative path.

Prefer the browser APIs.
A small quantity of your own code is better than a large dependency.
Example: the Web Audio API can calculate the peaks for a waveform.

### 4.9 Put each new directory in `setup.py`

`setup.py` gives the file list of the package.
It names each directory of `html/` with a glob that is **not** recursive.

    (('share/mod/html/js'), glob('html/js/*.js')),

A new directory is thus absent from the package.
The server on the device then gives 404 for each file in it.

An island makes all of its own markup (rule 4.3).
Thus a file that is absent gives an empty panel and **no other sign**.
This is a hard fault to find.

When you make an island, do these steps:

1. Add one line for the code: `glob('html/js/app/<feature>/*.js')`.
2. Add one line for the style: `glob('html/js/app/<feature>/*.css')`.
3. Run `python3 -m unittest discover -s test -p "test_setup_data_files.py"`.

`test/test_setup_data_files.py` runs the same globs that `setup.py` runs and
asks that each file under `html/js/app/` is in one of them. CI runs this test.

The seam also writes a message on the panel when the island does not load, so
the next fault of this class is visible in the browser.

### 4.10 Give the panel back to the keyboard

`main.less` holds this rule:

    * {
      outline: 0 !important
    }

It takes the focus ring that the browser draws off every element of the page,
and thus off every island.
A person on the keyboard then has no sign at all of where the focus sits.

An island puts a ring back, inside itself only:

    #sfzbuilder-library :focus {
      outline: 2px solid var(--sfz-focus) !important;
      outline-offset: -2px;
    }
    #sfzbuilder-library :focus:not(:focus-visible) {
      outline: 0 !important;
    }

The `!important` is not decoration. Nothing except `!important` beats an
`!important` declaration, and the rule above is the one that has to win.
The offset is negative so that the ring is drawn inside the edge of the element:
a ring outside the edge is cut by any list or grid that scrolls.
The second rule takes the ring off a press, which matters wherever the page is
opened by touch -- a tablet or a phone -- where a tap would else leave a ring
behind.
A browser that does not know `:focus-visible` drops that rule and shows the ring
for a press as well, which is the safe way for it to fail.

Then three rules about the elements themselves.

**An element that takes a click must take focus.**
A `div` or a `li` with an `onclick` and no `tabindex` cannot be reached by the
keyboard, and an element that cannot hold the focus cannot show a focus ring.
Give it `tabindex="0"`, a role, and the two keys that activate a button.
`clickable()` in `dom.js` does all three.
Act on a key only when the element itself has the focus: a press on a button
inside it sends a click of its own, and the keydown goes up to the element as
well, so without the test it acts two times.

**Do not put a role on a container that drops what is inside it.**
The children of `button`, `option`, `tab`, `menuitem`, `checkbox`, `radio` and
`switch` are presentational: a screen reader is free to read the element as one
piece of text and drop every control inside it.
A pad of the SFZ builder holds nine controls and wore `role="button"` for a
while, which hid all nine.
A pad is a `group`. A sample row keeps the `listitem` that a `li` in a `ul`
already has. A bank row holds text only, so it is a `button`.
An element that gains a control while it is open, such as the note stepper when
a click turns it into a field, drops its role while the field is there.

**Keep the order of the document.**
Do not write a positive `tabindex`. It pulls the element in front of the whole
page. Do not write a negative one either, which takes the control out of reach.
`tabindex="0"` everywhere means the order is the order you drew the elements in.
A long panel is thus a long tab order -- the SFZ builder has about ten stops for
each pad it holds -- and that is accepted for now. A shorter path is a question
of its own, in section 7.

### 4.11 Take down with jQuery what you put up with jQuery

An island writes its own elements with the browser API (rule 4.3), and
`clear()` in `dom.js` removes them with `removeChild`.

This is wrong for an element that carries a jQuery UI widget.
jQuery UI 1.10 keeps a `draggable` and a `droppable` in `$.ui.ddmanager` and in
the jQuery data cache, and it removes them only through the `cleanData` hook of
jQuery, which a native `removeChild` never runs.
The entries thus stay after the element is gone. They hold the element, so it is
never collected, and jQuery UI walks the whole list of droppables on each move
of a drag.

Use the jQuery `empty()` or `remove()` on any subtree that holds a widget, or
destroy each widget before you remove it.

`clear()` in `dom.js` is the one place an island takes elements down, so it
calls the jQuery `empty()` when jQuery is there and falls back to `removeChild`
when it is not. An island that keeps its teardown in one function of its own
gets this right everywhere at once.

The smoke test counts the entries in `$.ui.ddmanager` and in the jQuery data
cache across eight redraws and asks that neither one grows. Before the fix, the
pads and the sample rows of the SFZ builder leaked eighty droppables and
ninety-six data entries over those eight draws, and the panel draws again on
every click of a pad and every keystroke of the filter.

### 4.12 Read what `main.less` already declares on every element

`main.less` holds a second rule of the same shape as the one in 4.10:

    * {
      font-family: "cooper hewitt", Sans-serif !important;
    }

A universal selector with `!important` is the strongest thing a stylesheet can
say about a property.
It is not beaten by a longer selector, by a later rule, or by the identifier
that every island rule starts with.
It also lands on each element of the panel one by one, so it beats inheritance
as well: the island named `var(--sfz-mono)` on `#sfzbuilder-library`, the rule
above named the page font on every child of it, and the child won.
The panel thus drew in the page font from the day it was written, and read
nothing at all from its two font tokens.
Nothing failed and nothing was logged; the header was where you saw it, as a
title in the wrong font, wide enough in that font to push the tool row onto a
line of its own.

Two things follow.

**Grep `main.less` for `!important` before you write a stylesheet.**
There are only a few such rules and they are the ones that will silently
overrule you. Today they cover `outline` and `font-family`.

**A property you have to win, you win on every element, not on the panel.**

    #sfzbuilder-library,
    #sfzbuilder-library * {
      font-family: var(--sfz-mono) !important;
    }

The descendant half of the selector is what does the work.
A later rule of the island that names a class -- the status line asks for the
sans token -- still wins, because a class beats the `*`.
An element the island puts outside the panel needs the same treatment: the drag
helper of the SFZ builder lives on the body and carries a pair of rules of its
own.

**Have a test read it.**
A rule that loses is invisible in the file, so the smoke test reads the computed
`font-family` of the title and of an element nested inside the panel and
compares each against the token, as 4.5 asks.
The nested element is the part that matters: the panel had the right family on
itself while everything inside it had the page font.

## 5. Examples

### 5.1 The seam

The island supplies a `mount` function:

```js
// html/js/app/sfzbuilder/mount.js
// @ts-check

/**
 * Puts the SFZ builder in an element.
 * @param {HTMLElement} root An empty element.
 * @returns {{ destroy: () => void }}
 */
export function mount(root) { /* ... */ }
```

The legacy code calls this function with a dynamic import:

```js
// html/js/desktop.js  (legacy)
JqueryClass('sfzBuilderBox', {
    init: function () {
        var self = $(this)
        import('./app/sfzbuilder/mount.js').then(function (module) {
            self.data('island', module.mount(self[0]))
        })
    }
})
```

A dynamic import operates in a classic script.
Thus `index.html` needs no new script element.

### 5.2 The model and its test

```js
// html/js/app/sfzbuilder/model.js
// @ts-check

/**
 * Changes the number of pads. Each pad keeps its index.
 * @param {(Slot|null)[]} slots
 * @param {number} count The new number of pads, 1 to 128.
 * @returns {(Slot|null)[]} A new array. The input array does not change.
 */
export function resizePads(slots, count) {
    const next = []
    for (let i = 0; i < count; i++) next.push(slots[i] ?? null)
    return next
}
```

```js
// test/js/model.test.js
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { resizePads } from '../../html/js/app/sfzbuilder/model.js'

test('resizePads keeps each pad at its index', () => {
    const slots = [null, { sample: 'kick.wav' }, null]
    assert.deepEqual(resizePads(slots, 2), [null, { sample: 'kick.wav' }])
})
```

This test needs no browser and no build step.
Run it with `node --test test/js/`.

### 5.3 The tokens

The tokens go on `:root`, so that they reach an element the island puts on the
`body`, and every name carries the prefix of the island.

```css
:root {
    --sfz-bg: #111;
    --sfz-accent: #883996;
    --sfz-focus: #e8e8e8;
    --sfz-pad-min: 150px;
    --sfz-gap: 8px;
}

#sfzbuilder-library .sfz-pad-grid {
    display: grid;
    gap: var(--sfz-gap);
    grid-template-columns: repeat(auto-fill, minmax(var(--sfz-pad-min), 1fr));
}
```

Each rule starts at the identifier of the panel. `main.css` holds rules for the
bare elements -- `button`, `input`, `select`, `ul` -- and the identifier gives
the rules of the island the greater weight.

### 5.4 The cache

The script elements in `index.html` use a `?v={{version}}` parameter.
This parameter stops the browser from using an old file.
We keep this parameter now. We do not change the 41 script elements.

An island is different.
The legacy code loads an island with a dynamic import, and the island makes its
own `<link>` for its stylesheet.
Neither of these has a version parameter.

We first accepted this risk. The risk became a fault on the device:

* `TimelessStaticFileHandler` gives **every** static file `Cache-Control:
  public, max-age=31536000` and no ETag.
* `{{version}}` is `IMAGE_VERSION`, which the server reads from
  `/etc/mod-release/release`. That value does **not** change when you copy new
  files onto a device.
* Thus the browser held the island files for one year -- and held the **404**
  from a build that did not have those files yet.
* An island makes all of its own markup. A file that the browser cannot read
  gives an empty panel and **no other sign**.

`IslandStaticFileHandler` in `mod/webserver.py` now serves `html/js/app/` with
`Cache-Control: no-cache` and an ETag. The browser asks each time and the server
answers 304 when the file did not change.
The 41 script elements of `index.html` do not change.

### 5.5 The checks

The `Makefile` holds every check. Continuous integration calls the targets and
names no test file, so a new test runs without a change to either one.

| Target | What it answers |
|---|---|
| `make compile` | Do the server files parse? |
| `make test-py` | Does the model on the server behave? `unittest discover` finds `test/test_*.py`. |
| `make test-js` | Does the model in the browser behave? `node --test` finds `test/js/**/*.test.js`, with no browser and no build step. |
| `make typecheck` | Do the JSDoc types hold? `tsc --noEmit` over `html/js/app/`. |
| `make smoke` | Does the panel draw, style, focus and drag in a real browser? |
| `make test` | All of the above. Run this before you push. |

`test/test_setup_data_files.py` belongs to `make test-py` and is the check that
rule 4.9 asks for: it runs the globs of `setup.py` and asks that every file
under `html/js/app/` is in one of them.

## 6. Tradeoffs

**No bundler.**
The browser makes one request for each module file.
This is slow on the internet. It is fast on the local network.
We accept this cost. We do not accept the cost of a build step now.

**JSDoc types, not TypeScript.**
JSDoc is longer than TypeScript syntax.
Some advanced types are difficult to write.
But JSDoc needs no build step. This is more important now.

**Two code styles in one repository.**
New code and legacy code look different.
This can be a problem for a new person.
The directory `html/js/app/` makes the boundary clear.

**The islands do not share code at first.**
The second island can find that it needs code from the first island.
Then you must move that code to a shared directory.
Do not make a shared directory before two islands need it.

**The island files ask the server each time.**
An island file carries no version parameter, so `IslandStaticFileHandler` gives
it `Cache-Control: no-cache`.
The browser thus makes one small request for each island file on each visit.
The server answers 304 and sends no body.
On the local network this cost is small. It is smaller than the cost of a panel
that is empty because the browser holds an old file.

**One test needs a browser.**
`make smoke` needs headless Chrome, so it is the one check that does not run
from Python and node alone.
It is worth the cost: it is the only place that can answer a question about the
computed style, the focus or a drag, and those are the faults that an island
makes, because an island draws everything itself.

**The legacy problems continue.**
This design does not repair `pedalboard.js` or `modgui.js`.
It stops the growth of the problem. It does not remove the problem.

## 7. The SFZ builder

The SFZ builder is the first island. What was decided, and what it became:

| Question | Decision | Outcome |
|---|---|---|
| Directory | Use `html/js/app/<feature>/`. | `html/js/app/sfzbuilder/`: `mount.js`, `view.js`, `model.js`, `state.js`, `api.js`, `dom.js`, `legacy.js`, `sfzbuilder.css`. |
| Number of commits | Two. Commit 1 gives the structure. Commit 2 gives the new design. | Held. `docs/sfzbuilder-inventory.md` was the test for commit 1. |
| Continuous integration | Add a workflow. | `.github/workflows/ci.yml`, two jobs, calling the targets of section 5.5. |
| The `?v=` parameter | Do not change it. `html/js/app/` gets `no-cache` instead. | `IslandStaticFileHandler` in `mod/webserver.py`. See section 5.4. |
| Tokens | Write tokens for the SFZ builder only. | On `:root`, each name prefixed `--sfz-`. See rule 4.5. |

Open question 1 of the earlier draft asked which steps the workflow runs in
commit 1. It runs all of them: `compile`, `test-py`, `test-js`, `typecheck` and
`smoke`.

### What the first island taught

Each of these is now a rule above, and each came from a fault in the panel.

1. A file that the server does not send gives an empty panel and no other sign,
   because the island draws everything. Hence the `setup.py` check (4.9), the
   message on the seam, and the check that the stylesheet loaded.
2. The browser held those files, and their 404, for a year (5.4).
3. A token that does not reach the `body` makes a drag helper of black text on
   nothing (4.5).
4. `* { outline: 0 !important }` in `main.less` takes the focus ring off the
   panel, and several controls could not hold focus in any case (4.10).
5. A value that changes width moves the control under the pointer. A stepper
   holds one width whatever it shows.
6. A test that names a colour breaks when the design changes and says nothing
   when the code breaks (4.5).
7. An island draws its own elements, so it takes them down itself, and a native
   `removeChild` leaks every jQuery UI widget on them (4.11).
8. `* { font-family: ... !important }` in `main.less` beat the font tokens on
   every element of the panel, and the panel drew in the page font from the day
   it was written (4.12). The same shape of rule as 4: read what `main.less`
   already says about a property before you say it yourself.
9. Space between two rows of a header belongs in a `gap`, not in a margin on
   the row above. The tool row of the SFZ builder is hidden while no bank is
   open, and the margin under the title row was drawn all the same.

### Open questions

1. When do we add a bundler and TypeScript?
2. Which shared directory do two islands use? Do not make this directory before
   two islands need it.
3. How does a long panel keep a short path for the keyboard? The SFZ builder
   puts every pad and every control inside it in the tab order, which is correct
   and slow at 128 pads. A roving `tabindex` with the arrow keys is the usual
   answer, and it is not built (4.10).
