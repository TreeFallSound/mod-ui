// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * Pure functions for the SFZ builder.
 * This file has no DOM code and no network code.
 * @module
 */

/**
 * @typedef {object} Slot
 * @property {string} sample Bank-local file name.
 * @property {string|null} source Absolute path, if the file is outside the bank.
 * @property {number|null} volume Gain in dB.
 * @property {number|null} pitch Root note, or null for automatic.
 * @property {string} loop One of "one_shot" or "no_loop".
 */

/**
 * @typedef {object} SampleFile
 * @property {string} basename
 * @property {string} fullname
 * @property {number} [size] The size in bytes, if the server gives it.
 */

export const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

/**
 * The audio types that the server accepts.
 * Keep this list the same as AUDIO_EXTENSIONS in mod/sfzbuilder.py.
 * The server refuses a batch that holds one other file, so the panel removes
 * those files before the upload.
 */
export const AUDIO_EXTENSIONS = [
    '.aif', '.aifc', '.aiff', '.au', '.bwf', '.flac', '.htk', '.iff', '.mat4', '.mat5',
    '.oga', '.ogg', '.opus', '.paf', '.pvf', '.pvf5', '.sd2', '.sf', '.snd', '.svx',
    '.vcc', '.w64', '.wav', '.xi',
    '.3g2', '.3gp', '.aac', '.ac3', '.amr', '.ape', '.mp2', '.mp3', '.mpc', '.wma',
]

export const DEFAULT_BASE_NOTE = 36
export const MAX_NOTE = 127
export const MIN_PADS = 1
export const MAX_PADS = 128
export const MIN_COLS = 2
export const MAX_COLS = 6
export const DEFAULT_COLS = 4

/**
 * Gives the name of a MIDI note. Example: 36 gives "C2".
 * @param {number} note
 * @returns {string}
 */
export function noteName(note) {
    return NOTE_NAMES[note % 12] + (Math.floor(note / 12) - 1)
}

/**
 * Reads a base note from a text value.
 * An invalid value gives the default base note.
 * @param {string|number|null|undefined} value
 * @returns {number} A number from 0 to 127.
 */
export function clampBaseNote(value) {
    const base = parseInt(String(value), 10)
    return isNaN(base) ? DEFAULT_BASE_NOTE : Math.max(0, Math.min(MAX_NOTE, base))
}

/**
 * Reads a pad count from a text value.
 * @param {string|number|null|undefined} value
 * @returns {number} A number from 1 to 128.
 */
export function clampPadCount(value) {
    return Math.max(MIN_PADS, Math.min(MAX_PADS, parseInt(String(value), 10) || MIN_PADS))
}

/**
 * Changes the number of pads. Each pad keeps its index.
 * @param {(Slot|null)[]} slots
 * @param {number} count
 * @returns {(Slot|null)[]} A new array. The input array does not change.
 */
export function resizePads(slots, count) {
    /** @type {(Slot|null)[]} */
    const next = []
    for (let i = 0; i < count; i++) {
        next.push(slots[i] || null)
    }
    return next
}

/**
 * Gives the note number of a pad.
 * @param {number} baseNote
 * @param {number} index
 * @returns {number}
 */
export function padNote(baseNote, index) {
    return baseNote + index
}

/**
 * Reads a column count from a text value.
 * @param {string|number|null|undefined} value
 * @returns {number} A number from 2 to 6.
 */
export function clampCols(value) {
    const cols = parseInt(String(value), 10)
    return isNaN(cols) ? DEFAULT_COLS : Math.max(MIN_COLS, Math.min(MAX_COLS, cols))
}

/**
 * Gives the parts of the note of a pad.
 *
 * A bank can hold 128 pads and the base note can be more than 0. Thus the last
 * pads can go past note 127. Such a pad gets no note and the panel shows this.
 * @param {number} note
 * @returns {{ note: number, name: string, inRange: boolean }}
 */
export function noteToken(note) {
    const inRange = note >= 0 && note <= MAX_NOTE
    return { note: note, name: inRange ? noteName(note) : '--', inRange: inRange }
}

/**
 * Gives a short size for a file. Example: 412000 gives "402 KB".
 * @param {number|null|undefined} bytes
 * @returns {string} An empty string if the size is unknown.
 */
export function formatSize(bytes) {
    if (typeof bytes !== 'number' || !isFinite(bytes) || bytes < 0) {
        return ''
    }
    if (bytes < 1024) {
        return bytes + ' B'
    }
    if (bytes < 1024 * 1024) {
        return Math.round(bytes / 1024) + ' KB'
    }
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

/**
 * Changes the saved pads from the server into the pads that the panel uses.
 * @param {any[]} saved
 * @returns {(Slot|null)[]}
 */
export function alignSavedSlots(saved) {
    /** @type {(Slot|null)[]} */
    const aligned = []
    for (const slot of saved) {
        if (!slot) {
            aligned.push(null)
            continue
        }
        aligned.push({
            sample: slot.sample,
            source: null,
            volume: slot.volume,
            pitch: slot.pitch_keycenter === undefined ? null : slot.pitch_keycenter,
            loop: slot.loop_mode || 'one_shot',
        })
    }
    return aligned
}

/**
 * Makes the data for the build request.
 * An empty pad stays in the array as null. Thus the other pads keep their notes.
 * @param {(Slot|null)[]} slots
 * @returns {{ aligned: (object|null)[], filled: number }}
 */
export function buildPayload(slots) {
    /** @type {(object|null)[]} */
    const aligned = []
    let filled = 0
    for (const slot of slots) {
        if (!slot) {
            aligned.push(null)
            continue
        }
        filled++
        aligned.push({
            sample: slot.sample,
            source: slot.source,
            volume: slot.volume,
            pitch_keycenter: slot.pitch,
            loop_mode: slot.loop,
        })
    }
    return { aligned, filled }
}

/**
 * Selects the samples that match a search term.
 * The search ignores the case of the letters.
 * @param {SampleFile[]} files
 * @param {string} term
 * @returns {SampleFile[]}
 */
export function filterFiles(files, term) {
    const needle = (term || '').toLowerCase()
    if (!needle) {
        return files.slice()
    }
    return files.filter((f) => f.basename.toLowerCase().indexOf(needle) >= 0)
}

/**
 * Makes the pad data for a sample that the user assigns.
 * @param {SampleFile} entry
 * @param {string} source The current sample source: "bank", "device" or "usb".
 * @returns {Slot}
 */
export function slotFromSample(entry, source) {
    return {
        sample: entry.basename,
        source: source === 'bank' ? null : entry.fullname,
        volume: 0,
        pitch: null,
        loop: 'one_shot',
    }
}

/**
 * Tells if the server accepts a file name.
 * @param {string} name
 * @returns {boolean}
 */
export function isAudioName(name) {
    const lower = (name || '').toLowerCase()
    return AUDIO_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

/**
 * Divides dropped files into the files that the server accepts and the others.
 *
 * The upload control uses `accept="audio/*"`, but a drop from the desktop has
 * no filter. A folder frequently holds an image or a hidden file. The server
 * refuses the full batch in that condition, so the panel removes those files.
 * @param {{ name: string }[]} files
 * @returns {{ accepted: any[], rejected: any[] }}
 */
export function splitAudioFiles(files) {
    /** @type {any[]} */
    const accepted = []
    /** @type {any[]} */
    const rejected = []
    for (const file of files) {
        if (isAudioName(file.name)) {
            accepted.push(file)
        } else {
            rejected.push(file)
        }
    }
    return { accepted, rejected }
}
