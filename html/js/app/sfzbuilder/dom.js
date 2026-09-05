// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * A small set of tools that make elements.
 *
 * The island makes its own markup (architecture rule 4.3). These functions use
 * the browser API, and `clear` also uses jQuery to take an element down. They
 * exist so that the view code stays short, not to replace a library.
 * @module
 */

import { jq } from './legacy.js'

/**
 * Makes an element.
 *
 * The tag can hold classes after a dot. Example: `h('div.sfz-pad.sfz-pad--on')`.
 * A property that starts with "on" becomes an event listener.
 * A child that is a string becomes a text node, thus the text is always safe.
 *
 * @param {string} tag
 * @param {object} [props]
 * @param {(Node|string|null|false|undefined)[]} [children]
 * @returns {HTMLElement}
 */
export function h(tag, props, children) {
    const parts = tag.split('.')
    const node = document.createElement(parts[0] || 'div')
    for (let i = 1; i < parts.length; i++) {
        node.classList.add(parts[i])
    }
    for (const key in props || {}) {
        const value = (props || {})[key]
        if (value === null || value === undefined || value === false) {
            continue
        }
        if (key.indexOf('on') === 0) {
            node.addEventListener(key.slice(2), value)
        } else if (key === 'text') {
            node.textContent = String(value)
        } else if (key === 'html') {
            node.innerHTML = String(value)
        } else if (key in node && key !== 'list' && key !== 'form') {
            // @ts-ignore - a direct property keeps the type, for example checked.
            node[key] = value
        } else {
            node.setAttribute(key, String(value))
        }
    }
    for (const child of children || []) {
        if (child === null || child === undefined || child === false) {
            continue
        }
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child)
    }
    return node
}

/**
 * Removes every child of an element.
 *
 * This uses the jQuery `empty`, not `removeChild`, whenever jQuery is there
 * (architecture rule 4.11). jQuery UI keeps a `draggable` and a `droppable` in
 * `$.ui.ddmanager` and in the jQuery data cache, and it takes either one out
 * only through the `cleanData` hook of jQuery. A native `removeChild` never
 * runs that hook, so the entries stayed after the element was gone: they held
 * the element, which was thus never collected, and jQuery UI walks the whole
 * list of droppables on every move of a drag. The panel draws the pads again on
 * every click of a pad and the sample rows on every keystroke of the filter, so
 * the two lists grew for as long as the panel was open.
 *
 * `empty` cleans the descendants of the element and not the element itself,
 * which is what this function wants: the element stays and its children go.
 *
 * The plain path below is the one to take when jQuery is absent, so that this
 * file can be read outside the browser.
 *
 * @param {HTMLElement} node
 */
export function clear(node) {
    const $ = jq()
    if ($) {
        $(node).empty()
        return
    }
    while (node.firstChild) {
        node.removeChild(node.firstChild)
    }
}

/**
 * Adds or removes a class.
 * @param {Element|null} node
 * @param {string} name
 * @param {boolean} on
 */
export function toggleClass(node, name, on) {
    if (node) {
        node.classList.toggle(name, !!on)
    }
}

/**
 * Shows or hides an element.
 * @param {HTMLElement|null} node
 * @param {boolean} on
 */
export function show(node, on) {
    if (node) {
        node.style.display = on ? '' : 'none'
    }
}

/**
 * Makes an element that is not a button act as one.
 *
 * The bank rows, the sample rows and the pads are a div or a li, because each
 * one holds its own buttons and a button cannot hold a button. An element like
 * that takes a click but the keyboard cannot reach it, so it can carry no focus
 * ring either. This function gives it a place in the tab order, a name that a
 * screen reader reads, and the two keys that activate a button.
 *
 * The keys act only when the element itself has the focus. A press on a button
 * inside it, for example the play control of a sample row, sends a click of its
 * own and the keydown goes up to this element as well; without the test the row
 * would act two times.
 *
 * The role is given by the caller, because it is not always "button". The
 * children of a button are presentational: a screen reader is free to flatten
 * them away and read the button as one piece of text. That is right for an
 * element that holds text only, and wrong for one that holds a control of its
 * own, whose control would then be lost. Pass a role that keeps its children,
 * such as "group", or pass null to keep the role the element already has, which
 * for a li inside a ul is "listitem".
 *
 * @param {HTMLElement} node
 * @param {(event: Event) => void} onActivate
 * @param {string|null} [role] The ARIA role, "button" when not given.
 * @returns {HTMLElement} The same element.
 */
export function clickable(node, onActivate, role) {
    const name = role === undefined ? 'button' : role
    node.setAttribute('tabindex', '0')
    if (name) {
        node.setAttribute('role', name)
    }
    node.addEventListener('click', onActivate)
    node.addEventListener('keydown', (event) => {
        if (event.target !== node) {
            return
        }
        if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
            // A space would else scroll the list that holds the element.
            event.preventDefault()
            onActivate(event)
        }
    })
    return node
}
