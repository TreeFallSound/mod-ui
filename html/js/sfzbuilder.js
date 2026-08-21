// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later

var SFZBUILDER_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

function sfzBuilderNoteName(note) {
    return SFZBUILDER_NOTE_NAMES[note % 12] + (Math.floor(note / 12) - 1)
}

// One player for the whole panel, so only one sample sounds at a time.
var SFZBUILDER_PLAYER = null
var SFZBUILDER_PLAYING = null

JqueryClass('sfzBuilderBox', {
    init: function (options) {
        var self = $(this)

        options = $.extend({
            addBank: self.find('#sfzbuilder-add-bank'),
            bankList: self.find('#sfzbuilder-bank-list'),
            bankTitle: self.find('#sfzbuilder-bank-title h1'),
            toolbar: self.find('#sfzbuilder-bank-title .toolbar'),
            emptyState: self.find('#sfzbuilder-empty'),
            sourceSelect: self.find('#sfzbuilder-source'),
            uploadInput: self.find('#sfzbuilder-upload'),
            searchBox: self.find('#sfzbuilder-search'),
            sampleList: self.find('#sfzbuilder-sample-list'),
            padCount: self.find('#sfzbuilder-pad-count'),
            baseNote: self.find('#sfzbuilder-base-note'),
            baseName: self.find('#sfzbuilder-base-name'),
            buildButton: self.find('#sfzbuilder-build'),
            slotList: self.find('#sfzbuilder-slot-list'),
            status: self.find('#sfzbuilder-status'),
            isMainWindow: true,
            windowName: "Sound Bank Builder"
        }, options)

        self.data(options)
        self.data('slots', [])
        self.data('banks', [])
        self.data('currentBank', '')
        self.data('files', [])
        self.data('selectedSlot', -1)

        options.open = function () {
            self.sfzBuilderBox('refreshAll')
        }
        options.close = function () {
            self.sfzBuilderBox('stopPreview')
        }

        options.addBank.click(function () {
            self.sfzBuilderBox('promptNewBank')
        })

        options.sourceSelect.change(function () {
            self.sfzBuilderBox('refreshSamples')
        })

        options.uploadInput.change(function () {
            self.sfzBuilderBox('upload')
        })

        options.searchBox.keyup(function () {
            self.sfzBuilderBox('renderSamples')
        })

        options.padCount.change(function () {
            self.sfzBuilderBox('resizeSlots')
        })

        options.baseNote.change(function () {
            self.sfzBuilderBox('renderSlots')
        })

        options.buildButton.click(function () {
            self.sfzBuilderBox('build')
        })

        self.sfzBuilderBox('resizeSlots')
        self.sfzBuilderBox('updateBankView')

        self.window(options)
    },

    setStatus: function (message, error) {
        var options = this.data()
        options.status.text(message || '')
        options.status.toggleClass('error', !!error)
    },

    baseNoteValue: function () {
        var base = parseInt(this.data().baseNote.val(), 10)
        return isNaN(base) ? 36 : Math.max(0, Math.min(127, base))
    },

    // Shows or hides the pads, and keeps the title and the build button in step
    // with the bank that is selected.
    updateBankView: function () {
        var self = this
        var options = self.data()
        var bank = self.data('currentBank')
        options.bankTitle.text(bank || 'Untitled')
        options.emptyState.toggle(!bank)
        options.slotList.toggle(!!bank)
        options.toolbar.toggle(!!bank)
        options.buildButton.prop('disabled', !bank)
        options.baseName.text(sfzBuilderNoteName(self.sfzBuilderBox('baseNoteValue')))
    },

    refreshAll: function () {
        var self = this
        self.sfzBuilderBox('loadBanks', function () {
            self.sfzBuilderBox('refreshSamples')
            self.sfzBuilderBox('renderSlots')
        })
    },

    loadBanks: function (callback) {
        var self = this
        $.ajax({
            url: '/sfzbuilder/banks',
            dataType: 'json',
            success: function (data) {
                var banks = data.banks || []
                self.data('banks', banks)
                var current = self.data('currentBank')
                if (current && banks.indexOf(current) < 0) {
                    self.data('currentBank', '')
                }
                self.sfzBuilderBox('renderBanks')
                self.sfzBuilderBox('updateBankView')
                if (callback) callback()
            },
            error: function () {
                self.sfzBuilderBox('setStatus', 'Failed to load the banks', true)
                if (callback) callback()
            },
            cache: false
        })
    },

    renderBanks: function () {
        var self = this
        var options = self.data()
        var current = self.data('currentBank')
        options.bankList.html('')
        $.each(self.data('banks'), function (i, name) {
            var row = $('<div class="bank-item">').text(name)
            if (name === current) row.addClass('selected')
            row.click(function () {
                self.sfzBuilderBox('selectBank', name)
            })
            options.bankList.append(row)
        })
    },

    selectBank: function (name) {
        var self = this
        if (self.data('currentBank') === name) return
        self.sfzBuilderBox('stopPreview')
        self.data('currentBank', name)
        self.data('selectedSlot', -1)
        self.sfzBuilderBox('renderBanks')
        self.sfzBuilderBox('updateBankView')
        self.sfzBuilderBox('setStatus', '')
        self.sfzBuilderBox('loadBankState')
        self.sfzBuilderBox('refreshSamples')
    },

    // Reads the pad layout that the last build saved, so a bank opens again for edit.
    loadBankState: function () {
        var self = this
        var options = self.data()
        var bank = self.data('currentBank')
        if (!bank) return
        $.ajax({
            url: '/sfzbuilder/bank',
            data: { name: bank },
            dataType: 'json',
            success: function (resp) {
                if (!resp.ok) {
                    self.sfzBuilderBox('setStatus', resp.error, true)
                    return
                }
                var saved = resp.slots || []
                if (saved.length === 0) {
                    self.sfzBuilderBox('renderSlots')
                    return
                }
                var aligned = []
                $.each(saved, function (i, slot) {
                    if (!slot) {
                        aligned.push(null)
                        return
                    }
                    aligned.push({
                        sample: slot.sample,
                        source: null,
                        volume: slot.volume,
                        pitch: slot.pitch_keycenter === undefined ? null : slot.pitch_keycenter,
                        loop: slot.loop_mode || 'one_shot'
                    })
                })
                self.data('slots', aligned)
                options.padCount.val(aligned.length)
                options.baseNote.val(resp.base_note)
                self.sfzBuilderBox('renderSlots')
            },
            error: function () {
                self.sfzBuilderBox('setStatus', 'Failed to load the bank', true)
            },
            cache: false
        })
    },

    promptNewBank: function () {
        var self = this
        var options = self.data()
        if (options.bankList.find('.new-bank').length > 0) return
        var input = $('<input type="text" class="new-bank" placeholder="Bank name" />')
        options.bankList.prepend(input)
        input.focus()
        input.keydown(function (e) {
            if (e.keyCode === 13) {
                var name = $.trim(input.val() || '')
                input.remove()
                self.sfzBuilderBox('createBank', name)
            } else if (e.keyCode === 27) {
                input.remove()
            }
        })
        input.blur(function () {
            input.remove()
        })
    },

    createBank: function (name) {
        var self = this
        if (!name) {
            self.sfzBuilderBox('setStatus', 'Type a bank name first', true)
            return
        }
        $.ajax({
            url: '/sfzbuilder/bank',
            type: 'POST',
            data: JSON.stringify({ name: name }),
            dataType: 'json',
            success: function (resp) {
                if (!resp.ok) {
                    self.sfzBuilderBox('setStatus', resp.error, true)
                    return
                }
                self.data('currentBank', '')
                self.sfzBuilderBox('loadBanks', function () {
                    self.sfzBuilderBox('selectBank', resp.name)
                })
            },
            error: function () {
                self.sfzBuilderBox('setStatus', 'Failed to create the bank', true)
            },
            cache: false
        })
    },

    currentSource: function () {
        return this.data().sourceSelect.val()
    },

    refreshSamples: function () {
        var self = this
        var source = self.sfzBuilderBox('currentSource')
        var url = null
        var data = {}
        if (source === 'bank') {
            url = '/sfzbuilder/samples'
            data = { bank: self.data('currentBank') }
        } else if (source === 'device') {
            url = '/sfzbuilder/device'
            data = { exclude_bank: self.data('currentBank') }
        } else {
            url = '/sfzbuilder/usb'
        }
        $.ajax({
            url: url,
            data: data,
            dataType: 'json',
            success: function (resp) {
                if (!resp.ok) {
                    self.sfzBuilderBox('setStatus', resp.error, true)
                    return
                }
                self.data('files', resp.files || [])
                self.sfzBuilderBox('renderSamples')
            },
            error: function () {
                self.sfzBuilderBox('setStatus', 'Failed to load the samples', true)
            },
            cache: false
        })
    },

    stopPreview: function () {
        if (SFZBUILDER_PLAYER) {
            SFZBUILDER_PLAYER.pause()
            SFZBUILDER_PLAYER = null
        }
        if (SFZBUILDER_PLAYING) {
            SFZBUILDER_PLAYING.removeClass('playing')
            SFZBUILDER_PLAYING = null
        }
    },

    playPreview: function (button, fullname) {
        var self = this
        var wasPlaying = button.hasClass('playing')
        self.sfzBuilderBox('stopPreview')
        if (wasPlaying) return
        SFZBUILDER_PLAYER = new Audio('/sfzbuilder/audio/' + encodeURIComponent(fullname))
        SFZBUILDER_PLAYING = button
        button.addClass('playing')
        SFZBUILDER_PLAYER.addEventListener('ended', function () {
            self.sfzBuilderBox('stopPreview')
        })
        SFZBUILDER_PLAYER.addEventListener('error', function () {
            self.sfzBuilderBox('stopPreview')
            self.sfzBuilderBox('setStatus', 'Cannot play that sample', true)
        })
        SFZBUILDER_PLAYER.play()
    },

    renderSamples: function () {
        var self = this
        var options = self.data()
        var term = (options.searchBox.val() || '').toLowerCase()
        var files = $.grep(self.data('files'), function (f) {
            return !term || f.basename.toLowerCase().indexOf(term) >= 0
        })
        self.sfzBuilderBox('stopPreview')
        options.sampleList.html('')
        $.each(files, function (i, f) {
            var row = $('<li class="sfzbuilder-sample-row">')
            var play = $('<span class="sfzbuilder-play">')
            var name = $('<span class="sfzbuilder-sample-name">').text(f.basename)
            row.append(play, name)
            row.data('sfz-file', f)

            play.click(function (e) {
                e.stopPropagation()
                self.sfzBuilderBox('playPreview', play, f.fullname)
            })

            // A click fills the pad that is selected. This is the path for a touch
            // screen, where a drag is awkward.
            row.click(function () {
                var idx = self.data('selectedSlot')
                if (idx < 0) {
                    self.sfzBuilderBox('setStatus', 'Click a pad first, or drag the sample onto a pad', true)
                    return
                }
                self.sfzBuilderBox('assignSlot', idx, f)
            })

            row.draggable({
                revert: 'invalid',
                appendTo: 'body',
                helper: function () {
                    return $('<div class="sfzbuilder-drag-helper">').text(f.basename)
                },
                zIndex: 10000
            })

            options.sampleList.append(row)
        })
    },

    upload: function () {
        var self = this
        var options = self.data()
        var files = options.uploadInput[0].files
        if (!files || files.length === 0) return
        if (!self.data('currentBank')) {
            options.uploadInput.val('')
            self.sfzBuilderBox('setStatus', 'Select a bank first', true)
            return
        }
        var form = new FormData()
        form.append('bank', self.data('currentBank'))
        for (var i = 0; i < files.length; i++) form.append('file', files[i])
        $.ajax({
            url: '/sfzbuilder/upload',
            type: 'POST',
            data: form,
            processData: false,
            contentType: false,
            dataType: 'json',
            success: function (resp) {
                options.uploadInput.val('')
                if (!resp.ok) {
                    self.sfzBuilderBox('setStatus', resp.error, true)
                    return
                }
                self.sfzBuilderBox('setStatus', resp.files.length + ' file(s) uploaded')
                options.sourceSelect.val('bank')
                self.sfzBuilderBox('refreshSamples')
            },
            error: function () {
                options.uploadInput.val('')
                self.sfzBuilderBox('setStatus', 'Upload failed', true)
            }
        })
    },

    assignSlot: function (idx, entry) {
        var self = this
        var slots = self.data('slots')
        if (idx < 0 || idx >= slots.length) return
        slots[idx] = {
            sample: entry.basename,
            source: self.sfzBuilderBox('currentSource') === 'bank' ? null : entry.fullname,
            volume: 0,
            pitch: null,
            loop: 'one_shot'
        }
        self.data('selectedSlot', -1)
        self.sfzBuilderBox('setStatus', entry.basename + ' put on pad ' + (idx + 1))
        self.sfzBuilderBox('renderSlots')
    },

    resizeSlots: function () {
        var self = this
        var options = self.data()
        var count = Math.max(1, Math.min(128, parseInt(options.padCount.val(), 10) || 1))
        var slots = self.data('slots')
        if (slots.length !== count) {
            var next = []
            for (var i = 0; i < count; i++) next.push(slots[i] || null)
            self.data('slots', next)
        }
        self.sfzBuilderBox('renderSlots')
    },

    renderSlots: function () {
        var self = this
        var options = self.data()
        var slots = self.data('slots')
        var base = self.sfzBuilderBox('baseNoteValue')
        var selected = self.data('selectedSlot')

        options.baseName.text(sfzBuilderNoteName(base))
        options.slotList.html('')

        for (var i = 0; i < slots.length; i++) {
            (function (idx) {
                var slot = slots[idx]
                var note = base + idx
                var el = $('<div class="sfzbuilder-slot">')

                if (idx === selected) el.addClass('selected')

                el.append($('<span class="slot-note">').text(
                    note <= 127 ? note + ' (' + sfzBuilderNoteName(note) + ')' : 'out of range'))

                if (slot) {
                    el.addClass('filled')
                    var remove = $('<span class="slot-remove">').text('×').attr('title', 'Clear this pad')
                    remove.click(function (e) {
                        e.stopPropagation()
                        slots[idx] = null
                        self.sfzBuilderBox('renderSlots')
                    })
                    el.append(remove)
                    el.append($('<span class="slot-name">').text(slot.sample).attr('title', slot.sample))

                    var controls = $('<div class="slot-controls">')
                    controls.click(function (e) { e.stopPropagation() })

                    controls.append($('<label>').text('Gain'))
                    var gain = $('<input type="number" step="1" min="-144" max="48">').val(slot.volume)
                    gain.change(function () {
                        var v = parseFloat(gain.val())
                        slots[idx].volume = isNaN(v) ? null : v
                    })
                    controls.append(gain)

                    controls.append($('<label>').text('Root'))
                    var root = $('<input type="number" min="0" max="127" placeholder="auto">')
                    if (slot.pitch !== null && slot.pitch !== undefined) root.val(slot.pitch)
                    root.change(function () {
                        var v = parseInt(root.val(), 10)
                        slots[idx].pitch = isNaN(v) ? null : v
                    })
                    controls.append(root)

                    var loop = $('<select>')
                        .append($('<option value="one_shot">Full play</option>'))
                        .append($('<option value="no_loop">Cut on release</option>'))
                    loop.val(slot.loop)
                    loop.change(function () {
                        slots[idx].loop = loop.val()
                    })
                    controls.append(loop)
                    el.append(controls)
                } else {
                    el.append($('<span class="slot-empty">').text('Free pad'))
                }

                // Each pad is its own drop target, so the sample lands where you drop it.
                el.droppable({
                    accept: '.sfzbuilder-sample-row',
                    hoverClass: 'drop-hover',
                    tolerance: 'pointer',
                    drop: function (event, ui) {
                        var entry = ui.draggable.data('sfz-file')
                        if (entry) self.sfzBuilderBox('assignSlot', idx, entry)
                    }
                })

                el.click(function () {
                    self.data('selectedSlot', self.data('selectedSlot') === idx ? -1 : idx)
                    self.sfzBuilderBox('renderSlots')
                })

                options.slotList.append(el)
            })(i)
        }
    },

    build: function () {
        var self = this
        var slots = self.data('slots')
        if (!self.data('currentBank')) {
            self.sfzBuilderBox('setStatus', 'Select a bank first', true)
            return
        }
        var filled = 0
        // Send the pad-aligned array, so a free pad keeps its note number.
        var aligned = []
        $.each(slots, function (i, slot) {
            if (!slot) {
                aligned.push(null)
                return
            }
            filled++
            aligned.push({
                sample: slot.sample,
                source: slot.source,
                volume: slot.volume,
                pitch_keycenter: slot.pitch,
                loop_mode: slot.loop
            })
        })
        if (filled === 0) {
            self.sfzBuilderBox('setStatus', 'Put a sample on a pad first', true)
            return
        }
        $.ajax({
            url: '/sfzbuilder/build',
            type: 'POST',
            data: JSON.stringify({
                name: self.data('currentBank'),
                base_note: self.sfzBuilderBox('baseNoteValue'),
                slots: aligned
            }),
            dataType: 'json',
            success: function (resp) {
                if (!resp.ok) {
                    self.sfzBuilderBox('setStatus', resp.error, true)
                    return
                }
                self.sfzBuilderBox('setStatus', 'Built ' + resp.file + ' with ' + resp.count + ' sample(s)')
            },
            error: function () {
                self.sfzBuilderBox('setStatus', 'Build failed', true)
            },
            cache: false
        })
    }
})
