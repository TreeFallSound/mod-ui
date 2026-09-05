// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later

import { test } from 'node:test'
import assert from 'node:assert/strict'
import * as model from '../../html/js/app/sfzbuilder/model.js'

test('noteName gives the name of a MIDI note', () => {
    assert.equal(model.noteName(0), 'C-1')
    assert.equal(model.noteName(36), 'C2')
    assert.equal(model.noteName(37), 'C#2')
    assert.equal(model.noteName(60), 'C4')
    assert.equal(model.noteName(127), 'G9')
})

test('clampBaseNote keeps the value between 0 and 127', () => {
    assert.equal(model.clampBaseNote('36'), 36)
    assert.equal(model.clampBaseNote(-5), 0)
    assert.equal(model.clampBaseNote(200), 127)
})

test('clampBaseNote gives the default value for bad input', () => {
    assert.equal(model.clampBaseNote(''), 36)
    assert.equal(model.clampBaseNote('abc'), 36)
    assert.equal(model.clampBaseNote(null), 36)
})

test('clampPadCount keeps the value between 1 and 128', () => {
    assert.equal(model.clampPadCount('8'), 8)
    assert.equal(model.clampPadCount(0), 1)
    assert.equal(model.clampPadCount(999), 128)
    assert.equal(model.clampPadCount('abc'), 1)
})

test('resizePads keeps each pad at its index', () => {
    const kick = { sample: 'kick.wav', source: null, volume: 0, pitch: null, loop: 'one_shot' }
    const slots = [null, kick, null]
    assert.deepEqual(model.resizePads(slots, 2), [null, kick])
})

test('resizePads adds empty pads at the end', () => {
    assert.deepEqual(model.resizePads([], 3), [null, null, null])
})

test('resizePads does not change the input array', () => {
    const slots = [null, null]
    model.resizePads(slots, 5)
    assert.equal(slots.length, 2)
})

test('noteToken gives the number and the name', () => {
    assert.deepEqual(model.noteToken(36), { note: 36, name: 'C2', inRange: true })
})

test('noteToken marks a note above 127 as out of range', () => {
    assert.deepEqual(model.noteToken(128), { note: 128, name: '--', inRange: false })
})

test('clampCols keeps the count from 2 to 6', () => {
    assert.equal(model.clampCols('4'), 4)
    assert.equal(model.clampCols(1), 2)
    assert.equal(model.clampCols(99), 6)
    assert.equal(model.clampCols(null), model.DEFAULT_COLS)
    assert.equal(model.clampCols('abc'), model.DEFAULT_COLS)
})

test('formatSize gives a short size', () => {
    assert.equal(model.formatSize(0), '0 B')
    assert.equal(model.formatSize(512), '512 B')
    assert.equal(model.formatSize(412000), '402 KB')
    assert.equal(model.formatSize(1258291), '1.2 MB')
})

test('formatSize gives nothing for an unknown size', () => {
    assert.equal(model.formatSize(null), '')
    assert.equal(model.formatSize(undefined), '')
    assert.equal(model.formatSize(-1), '')
})

test('isAudioName accepts the types that the server accepts', () => {
    assert.equal(model.isAudioName('Kick_01.wav'), true)
    assert.equal(model.isAudioName('LOUD.WAV'), true)
    assert.equal(model.isAudioName('pad.flac'), true)
    assert.equal(model.isAudioName('take.aiff'), true)
    assert.equal(model.isAudioName('notes.txt'), false)
    assert.equal(model.isAudioName('cover.png'), false)
    assert.equal(model.isAudioName('wav'), false)
    assert.equal(model.isAudioName(''), false)
})

// The server refuses the full batch if one file is not audio, and it refuses it
// after it writes the files before that one. Thus the panel divides the files
// first. A drop from the desktop has no filter.
test('splitAudioFiles divides a drop into audio and the rest', () => {
    const files = [
        { name: 'Kick.wav' },
        { name: '.DS_Store' },
        { name: 'Snare.FLAC' },
        { name: 'cover.jpg' },
    ]
    const split = model.splitAudioFiles(files)
    assert.deepEqual(split.accepted.map((f) => f.name), ['Kick.wav', 'Snare.FLAC'])
    assert.deepEqual(split.rejected.map((f) => f.name), ['.DS_Store', 'cover.jpg'])
})

test('splitAudioFiles gives two empty lists for an empty drop', () => {
    const split = model.splitAudioFiles([])
    assert.deepEqual(split.accepted, [])
    assert.deepEqual(split.rejected, [])
})

test('alignSavedSlots keeps the empty pads', () => {
    const saved = [null, { sample: 'snare.wav', volume: -3, pitch_keycenter: 40, loop_mode: 'no_loop' }]
    const aligned = model.alignSavedSlots(saved)
    assert.equal(aligned[0], null)
    assert.deepEqual(aligned[1], {
        sample: 'snare.wav', source: null, volume: -3, pitch: 40, loop: 'no_loop',
    })
})

test('alignSavedSlots gives the default values for missing fields', () => {
    const aligned = model.alignSavedSlots([{ sample: 'hat.wav', volume: 0 }])
    assert.equal(aligned[0].pitch, null)
    assert.equal(aligned[0].loop, 'one_shot')
})

test('buildPayload sends null for an empty pad', () => {
    const slots = [
        null,
        { sample: 'kick.wav', source: null, volume: 0, pitch: null, loop: 'one_shot' },
    ]
    const payload = model.buildPayload(slots)
    assert.equal(payload.filled, 1)
    assert.equal(payload.aligned[0], null)
    assert.deepEqual(payload.aligned[1], {
        sample: 'kick.wav', source: null, volume: 0, pitch_keycenter: null, loop_mode: 'one_shot',
    })
})

test('buildPayload counts no full pads in an empty bank', () => {
    assert.equal(model.buildPayload([null, null]).filled, 0)
})

test('filterFiles ignores the case of the letters', () => {
    const files = [{ basename: 'Kick.wav', fullname: '/a/Kick.wav' }, { basename: 'snare.wav', fullname: '/a/snare.wav' }]
    assert.deepEqual(model.filterFiles(files, 'KICK'), [files[0]])
})

test('filterFiles gives every file for an empty term', () => {
    const files = [{ basename: 'a.wav', fullname: '/a.wav' }]
    assert.equal(model.filterFiles(files, '').length, 1)
})

test('slotFromSample keeps the path for a file outside the bank', () => {
    const file = { basename: 'kick.wav', fullname: '/media/usb/kick.wav' }
    assert.equal(model.slotFromSample(file, 'usb').source, '/media/usb/kick.wav')
    assert.equal(model.slotFromSample(file, 'bank').source, null)
})

test('pickInitialBank opens the bank of the last visit', () => {
    assert.equal(model.pickInitialBank(['Drums', 'Keys'], 'Keys'), 'Keys')
})

test('pickInitialBank gives the first bank when the last one is gone', () => {
    assert.equal(model.pickInitialBank(['Drums', 'Keys'], 'Deleted'), 'Drums')
})

test('pickInitialBank gives the first bank when nothing is remembered', () => {
    assert.equal(model.pickInitialBank(['Drums', 'Keys'], null), 'Drums')
    assert.equal(model.pickInitialBank(['Drums'], ''), 'Drums')
    assert.equal(model.pickInitialBank(['Drums'], undefined), 'Drums')
})

test('pickInitialBank gives no bank when the device has none', () => {
    assert.equal(model.pickInitialBank([], 'Keys'), '')
    assert.equal(model.pickInitialBank([], null), '')
})
