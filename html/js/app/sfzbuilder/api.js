// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * The network calls of the SFZ builder.
 * This file knows all the URLs. No other file in the island knows them.
 * @module
 */

import { jq } from './legacy.js'

/**
 * @param {string} url
 * @param {object} [data]
 * @returns {Promise<any>}
 */
function get(url, data) {
    return Promise.resolve(jq().ajax({
        url: url,
        data: data || {},
        dataType: 'json',
        cache: false,
    }))
}

/**
 * Gives the names of the banks and how many samples each one holds.
 * @returns {Promise<{ banks: string[], counts: Record<string, number> }>}
 */
export function listBanks() {
    return get('/sfzbuilder/banks').then((data) => ({
        banks: data.banks || [],
        counts: data.counts || {},
    }))
}

/**
 * Gives the base note and the pads of one bank.
 * @param {string} name
 * @returns {Promise<any>}
 */
export function loadBank(name) {
    return get('/sfzbuilder/bank', { name: name })
}

/**
 * Makes a bank directory.
 * @param {string} name
 * @returns {Promise<any>}
 */
export function createBank(name) {
    return Promise.resolve(jq().ajax({
        url: '/sfzbuilder/bank',
        type: 'POST',
        data: JSON.stringify({ name: name }),
        dataType: 'json',
        cache: false,
    }))
}

/**
 * Gives the audio files of one sample source.
 * @param {string} source One of "bank", "device" or "usb".
 * @param {string} bank The name of the current bank.
 * @returns {Promise<any>}
 */
export function listSamples(source, bank) {
    if (source === 'bank') {
        return get('/sfzbuilder/samples', { bank: bank })
    }
    if (source === 'device') {
        return get('/sfzbuilder/device', { exclude_bank: bank })
    }
    return get('/sfzbuilder/usb')
}

/**
 * Sends audio files to a bank.
 * @param {string} bank
 * @param {File[]|FileList} files
 * @returns {Promise<any>}
 */
export function uploadSamples(bank, files) {
    const form = new FormData()
    form.append('bank', bank)
    for (let i = 0; i < files.length; i++) {
        form.append('file', files[i])
    }
    return Promise.resolve(jq().ajax({
        url: '/sfzbuilder/upload',
        type: 'POST',
        data: form,
        processData: false,
        contentType: false,
        dataType: 'json',
    }))
}

/**
 * Gives the URL that plays one audio file.
 * @param {string} fullname
 * @returns {string}
 */
export function audioUrl(fullname) {
    return '/sfzbuilder/audio/' + encodeURIComponent(fullname)
}

/**
 * Writes the SFZ file of a bank.
 * @param {string} name
 * @param {number} baseNote
 * @param {(object|null)[]} slots
 * @returns {Promise<any>}
 */
export function buildBank(name, baseNote, slots) {
    return Promise.resolve(jq().ajax({
        url: '/sfzbuilder/build',
        type: 'POST',
        data: JSON.stringify({ name: name, base_note: baseNote, slots: slots }),
        dataType: 'json',
        cache: false,
    }))
}
