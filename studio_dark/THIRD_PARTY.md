# Theme sources

Studio Dark Compact 2.3 uses the GTK 3 CSS and assets from the user's
installed **MacTahoe-Dark-solid**. Its GTK3 copy is under
`theme/gtk-3.0/vendor/mactahoe/`, with the upstream MIT license in `COPYING`.
Four cosmetic rule groups for Nautilus and GNOME Photos were omitted because
they reference seven images absent from the supplied theme. GTK widget states and all supplied assets were retained.
Two neutral dark surface values were adjusted in the vendored CSS:
#242424 to #202020, and #333333 to #2d2d2d.
The original supplied theme directories were not modified. The changes are recorded in the audit.

Upstream: https://github.com/vinceliuice/MacTahoe-gtk-theme
Copyright (c) 2021 WhiteSur Developers.

The supplied **Mojave-Dark-solid-alt** was unpacked for comparison of widget
dimensions and spacing. The Inkscape layer uses its smaller horizontal requests as a design reference;
no Mojave CSS, compiled resources, or image assets are distributed here.

Upstream: https://github.com/vinceliuice/Mojave-gtk-theme

The complete provenance and source hashes are recorded in `qa/source-audit.json`.
Studio's installer, palette, compact rules, and Inkscape-specific rules remain
under the MIT license in `LICENSE`.
