// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * The state of the SFZ builder.
 * The view is a function of this state.
 * Only `update` changes the state. Thus there is one place to write log messages.
 * @module
 */
import { DEFAULT_PADS } from './model.js'

/**
 * @typedef {object} SfzState
 * @property {string[]} banks
 * @property {Record<string, number>} bankCounts How many samples each bank holds.
 * @property {string} currentBank
 * @property {import('./model.js').SampleFile[]} bankFiles The files of the current bank.
 * @property {import('./model.js').SampleFile[]} files The files that the list shows.
 * @property {(import('./model.js').Slot|null)[]} slots
 * @property {number} selectedSlot The index of the selected pad, or -1.
 * @property {number} baseNote
 * @property {number} padCount
 * @property {number} cols How many pads on each line.
 * @property {string} source
 * @property {string} search
 * @property {string} status
 * @property {boolean} statusIsError
 */

/**
 * Makes the first state.
 * @returns {SfzState}
 */
export function initialState() {
    return {
        banks: [],
        bankCounts: {},
        currentBank: '',
        bankFiles: [],
        files: [],
        slots: [],
        selectedSlot: -1,
        baseNote: 36,
        padCount: DEFAULT_PADS,
        cols: 4,
        source: 'bank',
        search: '',
        status: '',
        statusIsError: false,
    }
}

/**
 * Makes a store that holds the state.
 * @param {(state: SfzState) => void} onChange Runs after each change.
 */
export function createStore(onChange) {
    let state = initialState()
    return {
        /** @returns {SfzState} */
        get() {
            return state
        },
        /**
         * Changes the state and then draws the panel.
         * @param {Partial<SfzState>} patch
         */
        update(patch) {
            state = Object.assign({}, state, patch)
            onChange(state)
        },
    }
}
