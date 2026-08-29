"""A one-off job: measure real sailing distances off the map.

Run when the map changes - a new port, or a strait the lattice routes badly -
and not otherwise. Reads the cached tiles in web/tiles, writes
derived/port_distances.json, and that JSON is committed so nothing else ever
has to run this. Nothing imports this package.

Needs scipy and Pillow. Paths are imported absolutely rather than through four
dots, because this sits four levels down.
"""
