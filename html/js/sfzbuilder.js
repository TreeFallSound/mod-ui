// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * The seam between the legacy code and the SFZ builder island.
 *
 * This file is a classic script. `desktop.js` calls `sfzBuilderBox` and the
 * window manager needs the registration at once. Thus this file calls
 * `self.window(options)` without a wait, and loads the island in the
 * background. The panel opens later, so the island is ready in time.
 *
 * See docs/frontend-architecture.md, rule 4.2.
 */

/*
 * Writes why the panel is empty.
 *
 * index.html holds an empty container, because the island makes every element.
 * Thus a file that the server does not give makes an empty panel and no other
 * sign. The message below uses inline style, because the stylesheet of the
 * island can be the file that is absent.
 */
function sfzBuilderShowLoadError(root, err) {
    var text = (err && (err.message || err)) || 'unknown error'
    root.innerHTML = ''
    var box = document.createElement('div')
    box.setAttribute('style', [
        'position:absolute', 'top:0', 'bottom:45px', 'left:0', 'right:0',
        'z-index:2', 'background:#0a0a0a', 'color:#d8d8d8', 'padding:40px',
        'font-family:ui-monospace,Menlo,Consolas,monospace', 'font-size:13px',
        'line-height:1.7'
    ].join(';'))
    box.innerHTML =
        '<div style="color:#D91E36;font-weight:700;letter-spacing:.18em;' +
        'text-transform:uppercase;margin-bottom:14px">Sound Bank Builder did not load</div>' +
        '<div style="color:#6f6f6f">The panel could not read its own files from' +
        ' <code style="color:#F29446">js/app/sfzbuilder/</code>.' +
        ' Look in the network tab of the browser for a 404.</div>' +
        '<div style="margin-top:14px;color:#6f6f6f">Reason:' +
        ' <span style="color:#F29446"></span></div>'
    box.querySelector('span').textContent = text
    root.appendChild(box)
}

JqueryClass('sfzBuilderBox', {
    init: function (options) {
        var self = $(this)

        options = $.extend({
            isMainWindow: true,
            windowName: "Sound Bank Builder"
        }, options)

        var root = self[0]
        var island = import('./app/sfzbuilder/mount.js').then(function (module) {
            return module.mount(root)
        })
        island.catch(function (err) {
            console.error('Cannot load the Sound Bank Builder', err)
            sfzBuilderShowLoadError(root, err)
        })
        self.data('sfzIsland', island)

        options.open = function () {
            island.then(function (it) { it.open() }, function () { /* the message is on the panel */ })
        }
        options.close = function () {
            island.then(function (it) { it.close() }, function () { })
        }

        self.window(options)

        return self
    }
})
