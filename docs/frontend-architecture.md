# Frontend Architecture

Status: proposal.
Branch: `feat/sfzbuilder`.
Date: 2026-09-03.

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

An island puts its design values in CSS custom properties on its root element.
The LESS rules then read these properties.
Custom properties operate at run time.
Thus you can change the density for the small screen of the pi-stomp.

### 4.6 Keep the model pure. Keep the view thin

Put the calculations in a model file.
The model has no DOM code and no network code.
Test the model with the `node:test` module.

Do not write tests for the elements that the view makes.
The cost of these tests is high. The value is low.

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

```css
.sfz-root {
    --sfz-bg: #111;
    --sfz-accent: #f29446;
    --sfz-pad-min: 150px;
    --sfz-gap: 8px;
}

.sfz-pad-grid {
    display: grid;
    gap: var(--sfz-gap);
    grid-template-columns: repeat(auto-fill, minmax(var(--sfz-pad-min), 1fr));
}
```

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

**The legacy problems continue.**
This design does not repair `pedalboard.js` or `modgui.js`.
It stops the growth of the problem. It does not remove the problem.

## 7. Current PR -- sfz builder!

| Question | Decision |
|---|---|
| Directory | Use `html/js/app/<feature>/`. |
| Number of commits | Two. Commit 1 gives the structure. Commit 2 gives the new design. |
| Continuous integration | Add a workflow. |
| The `?v=` parameter | Do not change it. `html/js/app/` gets `no-cache` instead. |
| Tokens | Write tokens for the SFZ builder only. |

Commit 1 must not change the appearance of the SFZ builder.
Use `docs/sfzbuilder-inventory.md` to test commit 1.
Commit 2 then changes the appearance only.
Thus a visual difference in commit 2 is always intentional.

### Open questions

1. Which steps does the workflow run in commit 1?
   The JavaScript tests do not exist before commit 1.
   The workflow can start with `py_compile` and `pytest`.
2. When do we add a bundler and TypeScript?
3. Which shared directory do two islands use? Do not make this directory before two islands need it.
