// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * The SFZ builder island.
 * The legacy code starts the island with `mount`. This is the only seam.
 * @module
 */

import * as api from './api.js'
import * as model from './model.js'
import * as view from './view.js'
import { createStore } from './state.js'
import { toggleClass } from './dom.js'

/** Where the browser keeps the column count between visits. */
const COLS_KEY = 'sfzbuilder.cols'

/** Where the browser keeps the bank that you worked on last. */
const BANK_KEY = 'sfzbuilder.bank'

/**
 * Adds the stylesheet of the island to the page, one time.
 *
 * The island holds its markup, its code and its style in one directory. Thus
 * you can delete the directory and remove all of the feature.
 */
function addStylesheet() {
    if (document.querySelector('link[data-sfzbuilder]')) {
        return
    }
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.type = 'text/css'
    link.href = new URL('./sfzbuilder.css', import.meta.url).href
    link.setAttribute('data-sfzbuilder', '1')
    // The code can load while the stylesheet does not. The panel is then
    // there but has no size and no place, so the screen does not change and
    // the fault gives no other sign. Say it instead.
    link.addEventListener('error', () => {
        console.error('The Sound Bank Builder cannot read', link.href)
        const root = document.getElementById('sfzbuilder-library')
        if (root) {
            root.setAttribute('style', 'position:absolute;top:0;bottom:45px;left:0;right:0;'
                + 'z-index:2;background:#0a0a0a;color:#D91E36;padding:40px;font:13px monospace')
            root.textContent = 'The Sound Bank Builder cannot read its stylesheet: ' + link.href
        }
    })
    document.head.appendChild(link)
}

/**
 * Reads one value that the last visit wrote.
 *
 * A browser can refuse storage: a private window, or a setting that blocks site
 * data. Each call is thus in a try. The panel works without storage; it only
 * forgets what the last visit did.
 *
 * @param {string} key
 * @returns {string|null} Null when there is no value, or when storage fails.
 */
function readSetting(key) {
    try {
        return window.localStorage.getItem(key)
    } catch (e) {
        return null
    }
}

/**
 * Keeps one value for the next visit.
 * @param {string} key
 * @param {string} value
 */
function writeSetting(key, value) {
    try {
        window.localStorage.setItem(key, value)
    } catch (e) {
        /* The panel works without storage. */
    }
}

/**
 * Puts the SFZ builder in an element.
 * @param {HTMLElement} root The panel element.
 * @returns {{ open: () => void, close: () => void, destroy: () => void }}
 */
export function mount(root) {
    addStylesheet()

    const store = createStore(() => { /* the draws below are explicit */ })

    // Which view of the panel the answers coming back belong to.
    //
    // The panel asks for the sample list, the files of the bank and the pad
    // layout in three requests that do not wait for each other. Click bank A
    // and then bank B and the answers for A can land after the answers for B,
    // which drew the pads of A over the bank of B. Each request keeps the
    // number the panel had when it went out, and an answer that comes back to
    // a different number is dropped: the request that replaced it is already
    // on its way.
    let generation = 0

    /** @returns {() => boolean} A test that says whether the answer still fits. */
    function fresh() {
        const mine = generation
        return () => mine === generation
    }

    // One player for the full panel, so only one sample sounds at a time.
    /** @type {HTMLAudioElement|null} */
    let player = null
    /** @type {HTMLElement|null} */
    let playingButton = null

    const el = view.createLayout(root, {
        onAddBank: () => view.promptNewBank(el, createBank),
        onSource: setSource,
        onUpload: uploadFromInput,
        onSearch: (term) => {
            store.update({ search: term })
            drawSamples()
        },
        onPadCount: setPadCount,
        onCols: setCols,
        onBaseNote: setBaseNote,
        onSave: save,
        onRenameBank: () => view.promptRenameBank(el, renameBank),
        onDeleteBank: removeBank,
    })

    /**
     * @param {string} message
     * @param {boolean} [isError]
     */
    function setStatus(message, isError) {
        store.update({ status: message, statusIsError: !!isError })
        view.renderStatus(el, message, !!isError)
    }

    /**
     * Says that the pads hold a change that no save wrote.
     *
     * Everything the sidecar keeps counts: which sample is on which pad, the
     * gain, the root note, the loop mode, the pad count and the base note. The
     * column count does not -- that is how you look at the bank, not what the
     * bank is, and it lives in the browser rather than on the device.
     */
    function markDirty() {
        // No bank open means no work to lose. The panel builds its first pads
        // before it has asked the server for anything -- setPadCount below
        // grows the empty array to eight -- and that is the panel arranging
        // itself, not a change to a bank. Without this test the first bank the
        // panel opened asked whether to drop work that never existed.
        if (!store.get().currentBank) {
            return
        }
        if (store.get().dirty) {
            return
        }
        store.update({ dirty: true })
        drawBankView()
    }

    /** @param {boolean} [saved] */
    function markClean(saved) {
        if (!store.get().dirty) {
            return
        }
        store.update({ dirty: false })
        if (saved !== false) {
            drawBankView()
        }
    }

    /**
     * Asks before a step that would drop the changes the pads hold.
     *
     * The words are the ones the legacy panels use for the same question, so
     * the answer means the same thing wherever you meet it.
     * @returns {boolean} Whether to go on.
     */
    function confirmDiscard() {
        if (!store.get().dirty) {
            return true
        }
        return window.confirm('There are unsaved modifications that will be lost. Are you sure?')
    }

    function stopPreview() {
        if (player) {
            player.pause()
            player = null
        }
        if (playingButton) {
            playingButton.classList.remove('sfz-playing')
            playingButton.innerHTML = '&#9654;'
            playingButton = null
        }
    }

    /**
     * @param {HTMLElement} button
     * @param {string} fullname
     */
    function playPreview(button, fullname) {
        const wasPlaying = button.classList.contains('sfz-playing')
        stopPreview()
        if (wasPlaying) {
            return
        }
        player = new Audio(api.audioUrl(fullname))
        playingButton = button
        button.classList.add('sfz-playing')
        button.innerHTML = '&#9632;'
        player.addEventListener('ended', stopPreview)
        player.addEventListener('error', () => {
            stopPreview()
            setStatus('Cannot play that sample', true)
        })
        player.play()
    }

    /**
     * Gives the URL that plays the sample of a pad.
     *
     * A pad that comes from another place keeps the full path. A pad that comes
     * from the bank keeps the name only, so the name goes to the file list of
     * the bank. A bank that you did not open yet gives no URL and the play
     * control of the pad is off.
     * @param {import('./model.js').Slot} slot
     * @returns {string}
     */
    function previewUrl(slot) {
        if (slot.source) {
            return slot.source
        }
        for (const f of store.get().bankFiles) {
            if (f.basename === slot.sample) {
                return f.fullname
            }
        }
        return ''
    }

    function drawSlots() {
        view.renderSlots(el, store.get(), {
            onAssign: assignSlot,
            onSelect: selectSlot,
            onClear: clearSlot,
            onPlay: playPreview,
            previewUrl: previewUrl,
            onEdit: editSlot,
        })
    }

    function drawSamples() {
        view.renderSamples(el, store.get(), {
            onPlay: playPreview,
            onPick: pickSample,
        })
        // The old panel stopped the sound on every draw, so a filter cut the
        // sample that played. The panel now stops only when the row goes away.
        if (playingButton && !document.contains(playingButton)) {
            stopPreview()
        }
    }

    function drawBanks() {
        view.renderBanks(el, store.get(), selectBank)
    }

    function drawBankView() {
        view.renderBankView(el, store.get())
    }

    /** @param {number} idx */
    function selectSlot(idx) {
        const current = store.get().selectedSlot
        store.update({ selectedSlot: current === idx ? -1 : idx })
        drawSlots()
    }

    /** @param {number} idx */
    function clearSlot(idx) {
        const slots = store.get().slots.slice()
        slots[idx] = null
        store.update({ slots: slots })
        markDirty()
        drawSlots()
    }

    /**
     * Changes one field of one pad.
     *
     * The pads are not drawn again: the change came from a control inside the
     * pad and a redraw would take the focus out of it while you type.
     * @param {number} idx
     * @param {Partial<import('./model.js').Slot>} patch
     */
    function editSlot(idx, patch) {
        const state = store.get()
        const slot = state.slots[idx]
        if (!slot) {
            return
        }
        const slots = state.slots.slice()
        slots[idx] = Object.assign({}, slot, patch)
        store.update({ slots: slots })
        markDirty()
    }

    /**
     * @param {number} idx
     * @param {import('./model.js').SampleFile} entry
     */
    function assignSlot(idx, entry) {
        const state = store.get()
        if (idx < 0 || idx >= state.slots.length) {
            return
        }
        const slots = state.slots.slice()
        slots[idx] = model.slotFromSample(entry, state.source)
        store.update({ slots: slots, selectedSlot: -1 })
        markDirty()
        setStatus(entry.basename + ' put on pad ' + (idx + 1))
        drawSlots()
    }

    /** @param {import('./model.js').SampleFile} entry */
    function pickSample(entry) {
        const idx = store.get().selectedSlot
        if (idx < 0) {
            setStatus('Click a pad first, or drag the sample onto a pad', true)
            return
        }
        assignSlot(idx, entry)
    }

    /** @param {number} count */
    function setPadCount(count) {
        const slots = store.get().slots
        store.update({ padCount: count })
        if (slots.length !== count) {
            store.update({ slots: model.resizePads(slots, count) })
            markDirty()
        }
        drawSlots()
    }

    /** @param {number} cols */
    function setCols(cols) {
        store.update({ cols: cols })
        writeSetting(COLS_KEY, String(cols))
        el.grid.style.setProperty('--sfz-cols', String(cols))
    }

    /** @param {number|null} note */
    function setBaseNote(note) {
        const next = model.clampBaseNote(note)
        if (next !== store.get().baseNote) {
            store.update({ baseNote: next })
            markDirty()
        }
        drawSlots()
    }

    /** @param {string} source */
    function setSource(source) {
        generation++
        store.update({ source: source })
        drawBankView()
        refreshSamples()
    }

    function refreshSamples() {
        const state = store.get()
        const still = fresh()
        api.listSamples(state.source, state.currentBank).then((resp) => {
            if (!still()) {
                return
            }
            if (!resp.ok) {
                setStatus(resp.error, true)
                return
            }
            const files = resp.files || []
            const patch = { files: files }
            if (store.get().source === 'bank') {
                // @ts-ignore - the patch takes both keys.
                patch.bankFiles = files
            }
            store.update(patch)
            drawSamples()
            drawSlots()
        }, () => setStatus('Failed to load the samples', true))
    }

    /**
     * Reads the files of the current bank, whatever list the panel shows.
     * The pads need this list to play a sample that the bank holds.
     * @returns {Promise<void>}
     */
    function refreshBankFiles() {
        const bank = store.get().currentBank
        if (!bank) {
            store.update({ bankFiles: [] })
            return Promise.resolve()
        }
        const still = fresh()
        return api.listSamples('bank', bank).then((resp) => {
            if (resp.ok && still()) {
                store.update({ bankFiles: resp.files || [] })
                drawSlots()
            }
        }, () => { /* The panel works without the play control of a pad. */ })
    }

    /** @returns {Promise<void>} */
    function loadBanks() {
        return api.listBanks().then((resp) => {
            const banks = resp.banks
            const current = store.get().currentBank
            store.update({
                banks: banks,
                bankCounts: resp.counts || {},
                currentBank: current && banks.indexOf(current) < 0 ? '' : current,
            })
            drawBanks()
            drawBankView()
        }, () => {
            setStatus('Failed to load the banks', true)
        })
    }

    // Reads the pad layout that the last save wrote, so a bank opens for edit.
    function loadBankState() {
        const bank = store.get().currentBank
        if (!bank) {
            return
        }
        const still = fresh()
        api.loadBank(bank).then((resp) => {
            if (!still()) {
                return
            }
            if (!resp.ok) {
                setStatus(resp.error, true)
                return
            }
            const saved = resp.slots || []
            if (saved.length === 0) {
                // A bank that was never saved has no layout. The panel would
                // else keep the pads of the bank that was open before, and the
                // pad count and base note with them.
                const padCount = model.DEFAULT_PADS
                store.update({
                    slots: model.resizePads([], padCount),
                    padCount: padCount,
                    baseNote: model.DEFAULT_BASE_NOTE,
                })
                el.padStepper.set(padCount)
                el.baseStepper.set(model.DEFAULT_BASE_NOTE)
                // The two lines above run the same handlers a click on the
                // stepper runs, so they say the bank changed. The bank was
                // read, not changed, so the flag goes down after them, never
                // before.
                markClean()
                drawSlots()
                return
            }
            const aligned = model.alignSavedSlots(saved)
            const baseNote = model.clampBaseNote(resp.base_note)
            store.update({ slots: aligned, padCount: aligned.length, baseNote: baseNote })
            el.padStepper.set(aligned.length)
            el.baseStepper.set(baseNote)
            markClean()
            drawSlots()
        }, () => setStatus('Failed to load the bank', true))
    }

    /** @param {string} name */
    function selectBank(name) {
        if (store.get().currentBank === name) {
            return
        }
        if (!confirmDiscard()) {
            // The row that was clicked wears the selection for a moment before
            // the answer comes back, so the list is drawn again from the state,
            // which still holds the bank that stays open.
            drawBanks()
            return
        }
        stopPreview()
        generation++
        store.update({ currentBank: name, selectedSlot: -1, bankFiles: [], dirty: false })
        // The next visit opens this bank again. See model.pickInitialBank.
        writeSetting(BANK_KEY, name)
        drawBanks()
        drawBankView()
        setStatus('')
        loadBankState()
        refreshSamples()
        if (store.get().source !== 'bank') {
            refreshBankFiles()
        }
    }

    /** @param {string} name */
    function createBank(name) {
        if (!name) {
            setStatus('Type a bank name first', true)
            return
        }
        api.createBank(name).then((resp) => {
            if (!resp.ok) {
                setStatus(resp.error, true)
                return
            }
            store.update({ currentBank: '' })
            loadBanks().then(() => selectBank(resp.name))
        }, () => setStatus('Failed to create the bank', true))
    }

    /**
     * Changes the name of the current bank.
     *
     * The name that reaches the disk is not always the name that was asked
     * for -- a space becomes an underscore -- so the panel opens the bank
     * under the name that the server gives back, not the one it sent.
     * @param {string} name
     */
    function renameBank(name) {
        const from = store.get().currentBank
        if (!from) {
            return
        }
        // The panel opens the bank again under its new name, which reads the
        // layout back from the disk and thus drops whatever the pads hold.
        if (!confirmDiscard()) {
            return
        }
        api.renameBank(from, name).then((resp) => {
            if (!resp.ok) {
                setStatus(resp.error, true)
                return
            }
            // currentBank is cleared first so that selectBank does its work:
            // it returns early when the name it is given is already open, and
            // after a rename of "Kit" to "Kit A" the store still says "Kit".
            store.update({ currentBank: '', dirty: false })
            loadBanks().then(() => {
                selectBank(resp.name)
                setStatus('Renamed to ' + resp.name)
            })
        }, () => setStatus('Rename failed', true))
    }

    /**
     * Removes the current bank and everything in it.
     *
     * A confirm box asks first, the same way the legacy panels ask before a
     * change that cannot be undone. The bank holds the samples that were
     * uploaded to it, so this is not a change you can take back.
     */
    function removeBank() {
        const name = store.get().currentBank
        if (!name) {
            return
        }
        const count = store.get().bankCounts[name]
        const held = typeof count === 'number' && count > 0
            ? ' and the ' + count + ' sample(s) in it'
            : ''
        if (!window.confirm('Delete the bank ' + name + held + '? This cannot be undone.')) {
            return
        }
        api.deleteBank(name).then((resp) => {
            if (!resp.ok) {
                setStatus(resp.error, true)
                return
            }
            stopPreview()
            // The next visit must not try to open the bank that just went
            // away. refreshAll then falls back to the first bank there is.
            writeSetting(BANK_KEY, '')
            generation++
            store.update({ currentBank: '', selectedSlot: -1, bankFiles: [], files: [], dirty: false })
            loadBanks().then(() => {
                const banks = store.get().banks
                if (banks.length > 0) {
                    selectBank(banks[0])
                } else {
                    drawSamples()
                    drawSlots()
                }
                setStatus('Deleted ' + resp.name)
            })
        }, () => setStatus('Delete failed', true))
    }

    function uploadFromInput() {
        const files = el.uploadInput.files
        if (!files || files.length === 0) {
            return
        }
        const list = Array.prototype.slice.call(files)
        el.uploadInput.value = ''
        upload(list)
    }

    /**
     * Sends files to the current bank.
     * @param {File[]} files
     */
    function upload(files) {
        const bank = store.get().currentBank
        if (!bank) {
            setStatus('Select a bank first', true)
            return
        }
        // The server refuses the full batch if one file is not audio, and it
        // refuses it after it writes the files before that one. Thus the panel
        // removes those files first. A drop from the desktop has no filter.
        const split = model.splitAudioFiles(files)
        if (split.accepted.length === 0) {
            setStatus('No audio file in that drop', true)
            return
        }
        setStatus('Uploading ' + split.accepted.length + ' file(s)…')
        api.uploadSamples(bank, split.accepted).then((resp) => {
            if (!resp.ok) {
                setStatus(resp.error, true)
                return
            }
            const skipped = split.rejected.length
            setStatus(resp.files.length + ' file(s) uploaded'
                + (skipped ? ', ' + skipped + ' not audio' : ''), skipped > 0)
            generation++
            store.update({ source: 'bank' })
            drawBankView()
            refreshSamples()
            loadBanks()
        }, () => setStatus('Upload failed', true))
    }

    function save() {
        const state = store.get()
        if (!state.currentBank) {
            setStatus('Select a bank first', true)
            return
        }
        const payload = model.buildPayload(state.slots)
        if (payload.filled === 0) {
            setStatus('Put a sample on a pad first', true)
            return
        }
        api.buildBank(state.currentBank, state.baseNote, payload.aligned).then((resp) => {
            if (!resp.ok) {
                setStatus(resp.error, true)
                return
            }
            markClean()
            setStatus('Saved ' + resp.file + ' with ' + resp.count + ' sample(s)')
            refreshBankFiles()
        }, () => setStatus('Save failed', true))
    }

    // ---- the drop of a file from the desktop ----------------------------
    //
    // This is not the same as the drag of a sample onto a pad. That drag uses
    // jQuery UI, which reads mouse events. A drop from the desktop uses the
    // drag events of the browser and carries a `dataTransfer`. The code below
    // acts on a drop that holds files only, so an internal drag goes through.

    let dragDepth = 0

    /**
     * @param {DragEvent} e
     * @returns {boolean}
     */
    function holdsFiles(e) {
        const types = e.dataTransfer ? e.dataTransfer.types : null
        if (!types) {
            return false
        }
        return Array.prototype.indexOf.call(types, 'Files') >= 0
    }

    /** @param {boolean} on */
    function showOverlay(on) {
        toggleClass(el.overlay, 'sfz-overlay--on', on)
    }

    el.panel.addEventListener('dragenter', (/** @type {any} */ e) => {
        if (!holdsFiles(e)) {
            return
        }
        e.preventDefault()
        // A drag over a child element sends a leave and then an enter. The
        // count keeps the cover until the drag goes past the panel itself.
        dragDepth++
        showOverlay(true)
    })

    el.panel.addEventListener('dragover', (/** @type {any} */ e) => {
        if (!holdsFiles(e)) {
            return
        }
        e.preventDefault()
        if (e.dataTransfer) {
            e.dataTransfer.dropEffect = 'copy'
        }
    })

    el.panel.addEventListener('dragleave', (/** @type {any} */ e) => {
        if (!holdsFiles(e)) {
            return
        }
        dragDepth = Math.max(0, dragDepth - 1)
        if (dragDepth === 0) {
            showOverlay(false)
        }
    })

    el.panel.addEventListener('drop', (/** @type {any} */ e) => {
        if (!holdsFiles(e)) {
            return
        }
        e.preventDefault()
        dragDepth = 0
        showOverlay(false)
        const files = e.dataTransfer ? Array.prototype.slice.call(e.dataTransfer.files) : []
        if (files.length > 0) {
            upload(files)
        }
    })

    // A drop outside the panel must not make the browser open the file.
    /** @param {DragEvent} e */
    function blockOutside(e) {
        if (holdsFiles(e) && !el.panel.contains(/** @type {Node} */ (e.target))) {
            e.preventDefault()
        }
    }
    /** @param {DragEvent} e */
    function blockOutsideDrop(e) {
        if (holdsFiles(e) && !el.panel.contains(/** @type {Node} */ (e.target))) {
            e.preventDefault()
            dragDepth = 0
            showOverlay(false)
        }
    }
    let guarded = false

    function addGuards() {
        if (!guarded) {
            guarded = true
            document.addEventListener('dragover', blockOutside)
            document.addEventListener('drop', blockOutsideDrop)
        }
    }

    function removeGuards() {
        if (guarded) {
            guarded = false
            document.removeEventListener('dragover', blockOutside)
            document.removeEventListener('drop', blockOutsideDrop)
        }
    }

    // ---- the seam --------------------------------------------------------

    function refreshAll() {
        addGuards()
        loadBanks().then(() => {
            const state = store.get()
            if (!state.currentBank) {
                // The panel opens on the bank of the last visit. loadBanks
                // clears the current bank when that bank is gone, so this runs
                // on the first visit and after a bank goes away.
                const pick = model.pickInitialBank(state.banks, readSetting(BANK_KEY))
                if (pick) {
                    selectBank(pick)
                    return
                }
            }
            refreshSamples()
            drawSlots()
        })
    }

    function onClose() {
        stopPreview()
        dragDepth = 0
        showOverlay(false)
        removeGuards()
    }

    setCols(model.clampCols(readSetting(COLS_KEY)))
    el.colStepper.set(store.get().cols)
    setPadCount(store.get().padCount)
    drawBankView()

    return {
        open: refreshAll,
        close: onClose,
        destroy: onClose,
    }
}
