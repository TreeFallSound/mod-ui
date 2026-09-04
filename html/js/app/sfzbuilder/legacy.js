// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * The adapter to the legacy code.
 * This is the only file in the island that reads a global name.
 * @module
 */

/**
 * Gives the jQuery function from the legacy code.
 * jQuery UI adds `draggable` and `droppable` to it.
 * @returns {any}
 */
export function jq() {
    // @ts-ignore - jQuery is a global from a classic script.
    return window.jQuery
}
