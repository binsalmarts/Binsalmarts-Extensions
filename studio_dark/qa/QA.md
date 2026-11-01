# Studio Dark Compact 2.3 verification

Verified in the installed Inkscape 1.4.4 / bundled GTK 3.24 on macOS.
The installed theme files match the packaged source.

## Requested correction

The vertical `#commands-toolbar` now uses 16 px content minimums with equal
6 px padding: 28 px square icon buttons. Horizontal margins are 2 px rather
than 3 px. This replaces the 34 px horizontal request inherited from the
ordinary flat-button rule. Horizontal commands bars and popover contents are
excluded from this correction.

Inkscape's snap image has `halign=start`. Its statusbar eye/lock images are
packed at the start of `#AlternateIcons`. MacTahoe's 24 px content minimum
therefore left unused space on the right of a 16 px icon. These three controls
now use 16 px content minimums plus symmetric 6 px padding. The snap button
keeps its previous 28 px outside square; eye/lock use the same square. Icon
margins/padding are cleared only inside these controls, not across the UI.

## Native inspection

`preview-controls-v23.png` is a native 2940 × 1848 Retina screenshot of
Studio Dark 2.3 on the local `soft-rectangle-check.svg` QA document. It shows
centered snapping and checked visibility/lock buttons, and the narrower right
commands column. `preview-controls-normal-v23.png` shows the same document
with the layer visible and unlocked. Both alternate icons remain centered.
The QA layer's prior hidden/locked states were restored after inspection.
No actual working drawing was edited.

The earlier before capture used the user's active Mojave theme, confirmed
when preferences were saved on quit. It is not a Studio 2.2 measurement and
is excluded from the release archive. The 2.3 installed theme was activated
by the reversible installer and inspected after restarting Inkscape.

GTK accepted gtk.css, gtk-dark.css and inkscape.css. Nine installer
recovery/import tests passed. The specific normal-text palette pairs in
check_contrast.py pass 4.5:1; this is not a test of every GTK state.

## Preserved behavior

2.2's 4 px soft rectangular tab/scale corners, native field/scale heights,
8 px scroll thumbs, and two darker neutral base colours remain. Ruler
page/shadow/selection rules and paint-panel geometry were not changed.
No fixed-width dock rule was introduced. The earlier 2.1 expanded-wheel
inspection at 320 logical pixels remains a historical result, not a 2.3
wheel measurement.

## Provenance and loading

The supplied MacTahoe GTK3 CSS/assets remain the base, with its MIT license.
Four unrelated Nautilus/GNOME Photos cosmetic groups were omitted because
seven referenced images were missing in the supplied files. All generic GTK
widget rules and assets remain. The two neutral colour substitutions are
recorded in source-audit.json and THIRD_PARTY.md. The supplied source theme
folders were not edited. Mojave was inspected only for horizontal sizing.

The GTK base loads at theme priority. ui/Studio-Dark.css imports only
inkscape.css at application priority; this override does not set ruler
colours or import the complete GTK base above Inkscape's custom widgets.
