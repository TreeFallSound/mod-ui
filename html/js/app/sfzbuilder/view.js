// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * The markup and the drawing code of the SFZ builder.
 *
 * This file makes every element of the panel (architecture rule 4.3).
 * index.html holds an empty container only. Thus the full feature is in one
 * directory and the legacy markup does not limit the design.
 *
 * The file uses jQuery for one thing only: the drag of a sample onto a pad.
 * jQuery UI gives `draggable` and `droppable`, which the old panel used and
 * which work with a touch screen through the same code path.
 * @module
 */

import { jq } from './legacy.js'
import { h, clear, toggleClass, show, clickable } from './dom.js'
import * as model from './model.js'

/** What the title says when no bank is open. */
const NO_BANK_TITLE = 'No bank'

/**
 * Makes a stepper: a minus button, a value and a plus button.
 *
 * The panel has no bare number box. A number box is hard to hit with a finger,
 * on a tablet or a phone, and shows no limit.
 *
 * A stepper can hold no value when `nullable` is true. The gain and the root
 * note of a pad have no value by default, which the SFZ file needs: a pad with
 * no root note plays its sample at the written speed. The box is then empty and
 * shows the placeholder. A minus or a plus starts from `spec.start`.
 *
 * @param {object} spec
 * @param {number} spec.min
 * @param {number} spec.max
 * @param {number|null} spec.value
 * @param {(value: number|null) => void} spec.onSet Runs after each change.
 * @param {boolean} [spec.token] True draws the value as a note token.
 * @param {boolean} [spec.nullable] True lets the value be empty.
 * @param {number} [spec.start] The value that a click gives to an empty box.
 * @param {string} [spec.className]
 * @param {string} [spec.placeholder]
 * @param {string} [spec.title]
 * @returns {{ node: HTMLElement, set: (value: number|null) => void, get: () => number|null }}
 */
export function makeStepper(spec) {
    /** @type {number|null} */
    let value = spec.value
    /** @type {HTMLInputElement|null} */
    let input = null
    /** @type {HTMLElement} */
    let box

    const minus = h('button', { type: 'button', html: '&minus;', title: 'Less' })
    const plus = h('button', { type: 'button', text: '+', title: 'More' })

    if (spec.token) {
        // The box is a span, so it needs the tab order and the keys of a button
        // given to it. This happens one time here and not in drawToken, which
        // runs again after every change and would else add a listener each time.
        box = clickable(h('span.sfz-tokenbox'), openEditor)
    } else {
        input = /** @type {HTMLInputElement} */ (h('input', {
            type: 'text',
            inputmode: 'numeric',
            value: value === null ? '' : String(value),
            placeholder: spec.placeholder || '',
        }))
        box = input
    }

    const node = h('span.sfz-step' + (spec.className ? '.' + spec.className : ''),
        { title: spec.title || '' }, [minus, box, plus])

    /** @param {number|null} next */
    function set(next) {
        if (next === null || isNaN(next)) {
            value = spec.nullable ? null : spec.min
        } else {
            value = Math.max(spec.min, Math.min(spec.max, next))
        }
        draw()
        spec.onSet(value)
    }

    /** Gives the value that a minus or a plus starts from. */
    function base() {
        if (value !== null) {
            return value
        }
        const start = typeof spec.start === 'number' ? spec.start : spec.min
        return Math.max(spec.min, Math.min(spec.max, start))
    }

    function draw() {
        if (input) {
            input.value = value === null ? '' : String(value)
        } else {
            drawToken()
        }
        // @ts-ignore - a button has `disabled`.
        minus.disabled = value !== null && value <= spec.min
        // @ts-ignore
        plus.disabled = value !== null && value >= spec.max
    }

    // The token box shows "36 C2". A click turns it into a box that takes a
    // number, so you can go to a far note without many clicks.
    function drawToken() {
        clear(box)
        // A button again: the box holds text only in this condition.
        box.setAttribute('role', 'button')
        box.appendChild(noteTokenNode(value === null ? spec.min : value))
    }

    /** Turns the token box into the field that takes a number. */
    function openEditor() {
        const edit = /** @type {HTMLInputElement} */ (h('input.sfz-token-edit', {
            type: 'text',
            inputmode: 'numeric',
            value: String(value),
        }))
        let done = false
        function commit() {
            if (done) {
                return
            }
            done = true
            set(parseInt(edit.value, 10))
        }
        clear(box)
        // The box now holds a field that takes a number. The children of a
        // button are presentational, so the role goes away while the field is
        // open, or a screen reader could say nothing of what you type.
        box.removeAttribute('role')
        box.appendChild(edit)
        edit.focus()
        edit.select()
        edit.addEventListener('blur', commit)
        edit.addEventListener('keydown', (/** @type {any} */ e) => {
            if (e.key === 'Enter') {
                commit()
            } else if (e.key === 'Escape') {
                done = true
                drawToken()
                box.focus()
            }
        })
    }

    minus.addEventListener('click', () => set(value === null ? base() : value - 1))
    plus.addEventListener('click', () => set(value === null ? base() : value + 1))
    if (input) {
        // An empty box means "no value". Thus you can go back to the automatic
        // condition after you give a number.
        const read = () => {
            const text = (input ? input.value : '').trim()
            return text === '' ? null : parseInt(text, 10)
        }
        input.addEventListener('change', () => set(read()))
        input.addEventListener('keydown', (/** @type {any} */ e) => {
            if (e.key === 'Enter') {
                set(read())
            }
        })
    }

    draw()
    return { node: node, set: set, get: () => value }
}

/**
 * Makes the element that shows a MIDI note.
 * The panel shows a note in three places. All three use this element, so the
 * idea has one appearance.
 * @param {number} note
 * @returns {HTMLElement}
 */
export function noteTokenNode(note) {
    const token = model.noteToken(note)
    return h('span.sfz-note' + (token.inRange ? '' : '.sfz-note--out'), {}, [
        h('span.sfz-note-num', { text: token.inRange ? String(note) : '--' }),
        h('span.sfz-note-name', { text: token.name }),
    ])
}

/**
 * Makes the full panel inside the container.
 *
 * @param {HTMLElement} root The element of the panel, `#sfzbuilder-library`.
 * @param {object} handlers
 * @param {() => void} handlers.onAddBank
 * @param {(source: string) => void} handlers.onSource
 * @param {() => void} handlers.onUpload
 * @param {(term: string) => void} handlers.onSearch
 * @param {(count: number) => void} handlers.onPadCount
 * @param {(cols: number) => void} handlers.onCols
 * @param {(note: number) => void} handlers.onBaseNote
 * @param {() => void} handlers.onSave
 * @param {() => void} handlers.onRenameBank
 * @param {() => void} handlers.onDeleteBank
 */
export function createLayout(root, handlers) {
    clear(root)

    const bankList = h('div.sfz-bank-list')
    const addBank = h('button.sfz-add', { type: 'button', text: '+ New', onclick: handlers.onAddBank })
    const rail = h('div.sfz-rail', {}, [
        h('div.sfz-rail-head', {}, [h('span.sfz-lbl', { text: 'Banks' }), addBank]),
        bankList,
    ])

    // "Untitled" said that the bank had no name. A bank always has a name; what
    // the panel means here is that no bank is open, which is a different idea.
    const title = h('h2.sfz-title', { text: NO_BANK_TITLE })
    const saveButton = h('button.sfz-btn.sfz-save', { type: 'button', text: 'Save', title: 'Write the SFZ file of this bank' , onclick: handlers.onSave })
    const renameButton = h('button.sfz-btn.sfz-btn--quiet', {
        type: 'button', text: 'Rename', title: 'Change the name of this bank',
        onclick: handlers.onRenameBank,
    })
    const deleteButton = h('button.sfz-btn.sfz-btn--quiet.sfz-btn--danger', {
        type: 'button', text: 'Delete', title: 'Remove this bank and every file in it',
        onclick: handlers.onDeleteBank,
    })
    // The mark that says the pads hold a change no save wrote. It is a sibling
    // of the title and not a character added to it, so the name of the bank
    // stays the text of the title alone -- the ellipsis of a long name would
    // else eat the mark, and a screen reader would read it as part of the name.
    const dirtyMark = h('span.sfz-dirty', { text: 'Unsaved', hidden: true })
    const status = h('span.sfz-status')

    const padStepper = makeStepper({
        min: model.MIN_PADS, max: model.MAX_PADS, value: model.DEFAULT_PADS,
        title: 'How many pads this bank has',
        // A stepper that is not nullable never gives null. The clamp says so
        // to the type checker and costs nothing.
        onSet: (v) => handlers.onPadCount(model.clampPadCount(v)),
    })
    const colStepper = makeStepper({
        min: model.MIN_COLS, max: model.MAX_COLS, value: model.DEFAULT_COLS,
        title: 'How many pads on each line',
        onSet: (v) => handlers.onCols(model.clampCols(v)),
    })
    const baseStepper = makeStepper({
        min: 0, max: model.MAX_NOTE, value: model.DEFAULT_BASE_NOTE, token: true,
        title: 'The MIDI note of the first pad',
        onSet: (v) => handlers.onBaseNote(model.clampBaseNote(v)),
    })

    const tools = h('div.sfz-tools', {}, [
        h('span.sfz-field', {}, [h('span.sfz-lbl', { text: 'Pads' }), padStepper.node]),
        h('span.sfz-field', {}, [h('span.sfz-lbl', { text: 'Cols' }), colStepper.node]),
        h('span.sfz-field', {}, [h('span.sfz-lbl', { text: 'Base' }), baseStepper.node]),
    ])

    const grid = h('div.sfz-grid')
    const emptyState = h('div.sfz-empty-state', {}, [
        h('h3', { text: 'No sound bank selected' }),
        h('div.sfz-gesture', {}, [
            h('div', {}, [h('span.sfz-gesture-box', { text: '+' }), h('span', { text: 'New bank' })]),
            h('div', {}, [h('span.sfz-gesture-box', { html: '&#8681;' }), h('span', { text: 'Drop audio' })]),
            h('div', {}, [h('span.sfz-gesture-box', { html: '&#9654;' }), h('span', { text: 'Drag to a pad' })]),
        ]),
    ])

    const center = h('div.sfz-center', {}, [
        // The status sits on the title line, not in the tool row. The tool row
        // is hidden while no bank is open, and that is exactly when the panel
        // has the most to say ("Select a bank first"); the head is never
        // hidden. In the tool row it also wrapped onto a line of its own as
        // soon as the centre column went under about 490px, which read as an
        // empty line under the title.
        h('div.sfz-head', {}, [
            h('div.sfz-head-top', {}, [title, dirtyMark, status,
                h('div.sfz-head-right', {}, [renameButton, deleteButton, saveButton])]),
            tools,
        ]),
        grid,
        emptyState,
    ])

    /** @type {HTMLElement[]} */
    const sourceButtons = []
    const sourceBar = h('div.sfz-seg')
    for (const entry of [['bank', 'Bank'], ['device', 'Device'], ['usb', 'USB']]) {
        const button = h('button', {
            type: 'button',
            text: entry[1],
            'data-source': entry[0],
            'aria-pressed': entry[0] === 'bank' ? 'true' : 'false',
            onclick: () => handlers.onSource(entry[0]),
        })
        sourceButtons.push(button)
        sourceBar.appendChild(button)
    }

    const uploadInput = /** @type {HTMLInputElement} */ (h('input', {
        type: 'file', multiple: true, accept: 'audio/*', onchange: handlers.onUpload,
    }))
    const search = /** @type {HTMLInputElement} */ (h('input.sfz-search', {
        type: 'search', placeholder: 'FILTER…', autocomplete: 'off',
        oninput: () => handlers.onSearch(search.value || ''),
    }))
    const sampleList = h('ul.sfz-sample-list')

    const samples = h('div.sfz-samples', {}, [
        h('div.sfz-samples-head', {}, [
            h('span.sfz-lbl', { text: 'Samples' }),
            sourceBar,
            h('label.sfz-btn.sfz-upload', {}, ['Upload', uploadInput]),
            search,
        ]),
        sampleList,
    ])

    const overlaySub = h('div.sfz-overlay-sub')
    const overlay = h('div.sfz-overlay', {}, [
        h('div.sfz-overlay-big', { text: 'Drop audio files' }),
        overlaySub,
    ])

    // The shared header bar of the other panels. main.less draws it, so the
    // classes and the structure must be the same as the other panels. The one
    // difference is in main.less: this panel does not draw the MOD icon.
    const header = h('header', {}, [
        h('h1.bottom.top', { text: 'Sound Bank Builder' }),
    ])

    const panel = h('div.sfz-panel', {}, [rail, center, samples, overlay])
    root.appendChild(header)
    root.appendChild(panel)

    return {
        root, header, panel, rail, bankList, addBank,
        title, saveButton, renameButton, deleteButton, tools, status, dirtyMark,
        grid, emptyState,
        sourceButtons, uploadInput, search, sampleList,
        overlay, overlaySub,
        padStepper, colStepper, baseStepper,
    }
}

/** @typedef {ReturnType<typeof createLayout>} Elements */

/**
 * Shows the status message.
 * @param {Elements} el
 * @param {string} message
 * @param {boolean} isError
 */
export function renderStatus(el, message, isError) {
    el.status.textContent = message || ''
    toggleClass(el.status, 'sfz-status--err', isError)
}

/**
 * Keeps the title, the tools and the Save button in step with the bank.
 * @param {Elements} el
 * @param {import('./state.js').SfzState} state
 */
export function renderBankView(el, state) {
    const bank = state.currentBank
    el.title.textContent = bank || NO_BANK_TITLE
    show(el.emptyState, !bank)
    show(el.grid, !!bank)
    show(el.tools, !!bank)
    el.dirtyMark.hidden = !bank || !state.dirty
    for (const button of [el.saveButton, el.renameButton, el.deleteButton]) {
        // @ts-ignore - a button has `disabled`.
        button.disabled = !bank
    }
    el.overlaySub.textContent = bank
        ? 'WAV · FLAC · AIFF · OGG · MP3 — added to ' + bank
        : 'Select a bank first'
    el.grid.style.setProperty('--sfz-cols', String(state.cols))
    for (const button of el.sourceButtons) {
        button.setAttribute('aria-pressed', button.getAttribute('data-source') === state.source ? 'true' : 'false')
    }
}

/**
 * Draws the list of the banks.
 * @param {Elements} el
 * @param {import('./state.js').SfzState} state
 * @param {(name: string) => void} onSelect
 */
export function renderBanks(el, state, onSelect) {
    clear(el.bankList)
    for (const name of state.banks) {
        const row = clickable(h('div.sfz-bank' + (name === state.currentBank ? '.sfz-bank--on' : ''), {
            title: name,
            'aria-pressed': name === state.currentBank ? 'true' : 'false',
        }, [
            h('span.sfz-bank-name', { text: name }),
            h('span.sfz-bank-count', { text: countLabel(state.bankCounts[name]) }),
        ]), () => onSelect(name))
        el.bankList.appendChild(row)
    }
}

/**
 * @param {number|undefined} count
 * @returns {string}
 */
function countLabel(count) {
    return typeof count === 'number' ? String(count) : ''
}

/**
 * Turns the title into a field that takes a new name for the bank.
 *
 * The rename happens where the name is, the same way a new bank is named in
 * the place the row will take. The panel opens no dialog of its own: the one
 * dialog it uses is the browser confirm before a delete, which is what the
 * legacy code does for a change that cannot be undone.
 * @param {Elements} el
 * @param {(name: string) => void} onCommit
 */
export function promptRenameBank(el, onCommit) {
    const current = el.title.textContent || ''
    if (el.title.parentNode === null || el.title.hidden) {
        return
    }
    const input = /** @type {HTMLInputElement} */ (h('input.sfz-title-edit', {
        type: 'text', value: current, 'aria-label': 'The name of this bank',
    }))
    el.title.hidden = true
    el.title.parentNode.insertBefore(input, el.title)
    input.focus()
    input.select()

    let done = false
    /** @param {boolean} back Whether the focus goes to the Rename button. */
    function close(back) {
        done = true
        el.title.hidden = false
        if (input.parentNode) {
            input.parentNode.removeChild(input)
        }
        if (back) {
            el.renameButton.focus()
        }
    }
    input.addEventListener('keydown', (/** @type {any} */ e) => {
        if (e.key === 'Enter') {
            const name = (input.value || '').trim()
            close(true)
            if (name && name !== current) {
                onCommit(name)
            }
        } else if (e.key === 'Escape') {
            // A stray Escape must not reach the window manager and close the
            // panel with the field still open.
            e.stopPropagation()
            close(true)
        }
    })
    input.addEventListener('blur', () => {
        if (!done) {
            close(false)
        }
    })
}

/**
 * Opens the box that takes the name of a new bank.
 * @param {Elements} el
 * @param {(name: string) => void} onCommit
 */
export function promptNewBank(el, onCommit) {
    if (el.bankList.querySelector('.sfz-new-bank')) {
        return
    }
    const input = /** @type {HTMLInputElement} */ (h('input.sfz-new-bank', {
        type: 'text', placeholder: 'Bank name',
    }))
    el.bankList.insertBefore(input, el.bankList.firstChild)
    input.focus()
    let done = false
    function close() {
        if (input.parentNode) {
            input.parentNode.removeChild(input)
        }
    }
    input.addEventListener('keydown', (/** @type {any} */ e) => {
        if (e.key === 'Enter') {
            done = true
            const name = (input.value || '').trim()
            close()
            onCommit(name)
        } else if (e.key === 'Escape') {
            done = true
            close()
        }
    })
    input.addEventListener('blur', () => {
        if (!done) {
            close()
        }
    })
}

/**
 * Draws the list of the samples.
 * @param {Elements} el
 * @param {import('./state.js').SfzState} state
 * @param {{ onPlay: (button: HTMLElement, fullname: string) => void, onPick: (file: import('./model.js').SampleFile) => void }} handlers
 */
export function renderSamples(el, state, handlers) {
    const $ = jq()
    const files = model.filterFiles(state.files, state.search)
    clear(el.sampleList)

    if (files.length === 0) {
        el.sampleList.appendChild(h('li.sfz-sample-none', {
            text: state.search ? 'No sample has that name' : 'No sample here',
        }))
        return
    }

    for (const f of files) {
        const play = h('button.sfz-sample-play', {
            type: 'button',
            html: '&#9654;',
            title: 'Play this sample',
            onclick: (/** @type {Event} */ e) => {
                e.stopPropagation()
                handlers.onPlay(play, f.fullname)
            },
        })
        // A click fills the pad that is selected. This is the path for a touch
        // screen, where a drag is awkward, and for the keyboard.
        //
        // The row holds a play button, so it keeps the listitem role that a li
        // inside a ul already has. A button role would let a screen reader drop
        // that play button.
        const row = clickable(h('li.sfz-sample', {
            title: f.fullname,
            'aria-label': f.basename + ', put on the pad that is selected',
        }, [
            play,
            h('span.sfz-sample-name', { text: f.basename }),
            h('span.sfz-sample-size', { text: model.formatSize(f.size) }),
        ]), () => handlers.onPick(f), null)

        const $row = $(row)
        $row.data('sfz-file', f)
        $row.draggable({
            revert: 'invalid',
            // The helper goes on the body so that the panel, which hides what
            // goes past its edge, does not cut it.
            appendTo: 'body',
            helper: () => $(h('div.sfz-drag-helper', {}, [
                h('span.sfz-drag-mark', { html: '&#9654;' }),
                h('span.sfz-drag-name', { text: f.basename }),
            ])),
            // The pointer holds the helper near its left edge, so the name is
            // beside the pointer and the pad below stays visible.
            cursorAt: { left: 14, top: 14 },
            // A click puts the sample on the pad that is selected. A drag needs
            // a longer movement, so a small movement does not eat the click.
            distance: 6,
            zIndex: 10000,
            start: () => row.classList.add('sfz-sample--dragging'),
            stop: () => row.classList.remove('sfz-sample--dragging'),
        })

        el.sampleList.appendChild(row)
    }
}

/**
 * Draws the pads.
 *
 * The gain, root and loop controls send one field each to `onEdit`. They do not
 * draw the pads again, so the focus stays in the box while you type.
 *
 * @param {Elements} el
 * @param {import('./state.js').SfzState} state
 * @param {object} handlers
 * @param {(index: number, file: import('./model.js').SampleFile) => void} handlers.onAssign
 * @param {(index: number) => void} handlers.onSelect
 * @param {(index: number) => void} handlers.onClear
 * @param {(button: HTMLElement, fullname: string) => void} handlers.onPlay
 * @param {(slot: import('./model.js').Slot) => string} handlers.previewUrl
 * @param {(index: number, patch: Partial<import('./model.js').Slot>) => void} handlers.onEdit
 */
export function renderSlots(el, state, handlers) {
    const $ = jq()
    clear(el.grid)
    el.grid.style.setProperty('--sfz-cols', String(state.cols))

    state.slots.forEach((slot, idx) => {
        const note = model.padNote(state.baseNote, idx)

        const head = h('div.sfz-pad-head', {}, [
            h('span.sfz-pad-idx', { text: padIndex(idx) }),
            h('div.sfz-pad-meta', {}, [
                noteTokenNode(note),
                slot ? h('button.sfz-pad-clear', {
                    type: 'button',
                    html: '&times;',
                    title: 'Clear this pad',
                    onclick: (/** @type {Event} */ e) => {
                        e.stopPropagation()
                        handlers.onClear(idx)
                    },
                }) : null,
            ]),
        ])

        if (slot) {
            const preview = handlers.previewUrl(slot)
            const play = h('button.sfz-pad-play', {
                type: 'button',
                html: '&#9654;',
                title: preview ? 'Play this sample' : 'This sample is not here yet',
                disabled: !preview,
                onclick: (/** @type {Event} */ e) => {
                    e.stopPropagation()
                    if (preview) {
                        handlers.onPlay(play, preview)
                    }
                },
            })
            head.appendChild(play)
            head.appendChild(h('div.sfz-pad-file', { text: slot.sample, title: slot.sample }))
        }

        // A pad is a group, not a button. It holds the clear and play buttons,
        // two steppers and the loop menu, and the children of a button are
        // presentational: a screen reader may drop every one of them. A group
        // keeps its children. aria-pressed belongs to a button, so the
        // selection is said in the label instead.
        const pad = clickable(h('div.sfz-pad'
            + (slot ? '.sfz-pad--filled' : '.sfz-pad--empty')
            + (idx === state.selectedSlot ? '.sfz-pad--on' : ''),
            {
                'aria-label': 'Pad ' + (idx + 1) + ', note ' + model.noteToken(note).name
                    + (slot ? ', ' + slot.sample : ', free')
                    + (idx === state.selectedSlot ? ', selected' : ''),
            },
            [head, slot ? padProps(slot, idx, handlers.onEdit) : h('div.sfz-pad-free', { text: '— FREE —' })]),
            () => handlers.onSelect(idx), 'group')

        // Each pad takes its own drop, so a sample lands where you put it.
        $(pad).droppable({
            accept: '.sfz-sample',
            // --target marks every pad while a drag runs, so you can see where
            // a sample can go. --drop marks the pad under the pointer.
            activeClass: 'sfz-pad--target',
            hoverClass: 'sfz-pad--drop',
            tolerance: 'pointer',
            drop: (/** @type {any} */ _e, /** @type {any} */ ui) => {
                const entry = ui.draggable.data('sfz-file')
                if (entry) {
                    handlers.onAssign(idx, entry)
                }
            },
        })

        el.grid.appendChild(pad)
    })
}

/**
 * @param {number} idx
 * @returns {string}
 */
function padIndex(idx) {
    const n = idx + 1
    return n < 10 ? '0' + n : String(n)
}

/**
 * Makes the gain, root and loop controls of one pad.
 * One control on each line. This keeps a pad legible at six columns.
 *
 * A control sends the index of its pad and the one field it changed, never the
 * pad object it was drawn from. The pads are not drawn again while you edit --
 * the focus has to stay in the box you are typing in -- so a control that held
 * the object would go on writing into a pad that the store had already
 * replaced.
 * @param {import('./model.js').Slot} slot The values the controls open with.
 * @param {number} idx
 * @param {(index: number, patch: Partial<import('./model.js').Slot>) => void} onEdit
 * @returns {HTMLElement}
 */
function padProps(slot, idx, onEdit) {
    const gain = makeStepper({
        min: -144, max: 48, value: typeof slot.volume === 'number' ? slot.volume : null,
        nullable: true, start: 0, placeholder: '0',
        className: 'sfz-step--mini',
        title: 'Gain in dB. An empty box means no change.',
        onSet: (v) => onEdit(idx, { volume: v }),
    })

    // The root note has no value by default. sfizz then plays the sample at the
    // written speed, which is correct for a drum hit. An empty box keeps that.
    const root = makeStepper({
        min: 0, max: model.MAX_NOTE,
        value: typeof slot.pitch === 'number' ? slot.pitch : null,
        nullable: true, start: model.DEFAULT_BASE_NOTE, placeholder: 'AUTO',
        className: 'sfz-step--mini',
        title: 'The note that plays the sample at the written speed. Empty is automatic.',
        onSet: (v) => onEdit(idx, { pitch: v }),
    })

    const loop = /** @type {HTMLSelectElement} */ (h('select.sfz-select', {
        title: 'What happens when you release the pad',
        onchange: () => onEdit(idx, { loop: loop.value }),
    }, [
        h('option', { value: 'one_shot', text: 'ONE_SHOT' }),
        h('option', { value: 'no_loop', text: 'NO_LOOP' }),
    ]))
    loop.value = slot.loop

    const props = h('div.sfz-props', {}, [
        h('span.sfz-prop', {}, [h('span.sfz-lbl', { text: 'Gain' }), gain.node]),
        h('span.sfz-prop', {}, [h('span.sfz-lbl', { text: 'Root' }), root.node]),
        loop,
    ])
    props.addEventListener('click', (e) => e.stopPropagation())
    return props
}
