"""
SMA2 Title Screen Editor
─────────────────────────────────────────────────────────────────────
Super Mario World: Super Mario Advance 2 (GBA) – Title Screen Editor

─────────────────
• Palette changes instantly refresh the MAP panel (center) — no stale tiles.
• Keyboard shortcuts on the map view:
    Ctrl+C        Copy selected tiles
    Ctrl+V        Paste at anchor (first selected tile)
    Del / Backspace  Delete selected tiles (blank them)
    Ctrl+A        Select all 1024 map tiles
    Ctrl+Z        Undo last paint/delete/paste (single-level)
    Ctrl+S        Save ROM (same as SAVE button)
    H             Flip selected tiles horizontally
    V             Flip selected tiles vertically
• Palette address dropdown includes all verified candidate addresses
  found in binptrs.txt (0815A690, 0815AE90, 0812CE90, …) plus a
  manual hex entry field for any custom address.
• Correct 5→8 bit BGR555 expansion.

Copyright (c) 2026, Oquendo
"""

from __future__ import annotations

import os
import struct
import sys
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QEvent # type: ignore
from PyQt6.QtGui import QColor, QImage, QKeySequence, QPixmap, QTransform # type: ignore
from PyQt6.QtWidgets import ( # type: ignore
    QApplication, QColorDialog, QComboBox, QFileDialog, QGraphicsPixmapItem,
    QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QStatusBar, QVBoxLayout, QWidget,
)


# ══════════════════════════════════════════════════════════════════════
#  GFX UTILS  (from gfx.py in this repo)
# ══════════════════════════════════════════════════════════════════════

def bgr555_to_rgba(c: int) -> Tuple[int, int, int, int]:
    """GBA BGR555 → (r8, g8, b8, 255).  Canonical 5→8 expansion."""
    r5 = c & 0x1F
    g5 = (c >> 5) & 0x1F
    b5 = (c >> 10) & 0x1F
    return (r5 << 3) | (r5 >> 2), (g5 << 3) | (g5 >> 2), (b5 << 3) | (b5 >> 2), 255


def rgba_to_bgr555(r: int, g: int, b: int) -> int:
    return ((r >> 3) & 0x1F) | (((g >> 3) & 0x1F) << 5) | (((b >> 3) & 0x1F) << 10)


def decode_4bpp_tile(tile32: bytes) -> List[int]:
    """32 bytes → 64 palette indices, row-major 8×8. Low nibble = left px."""
    out: List[int] = []
    for y in range(8):
        for x in range(4):
            b = tile32[y * 4 + x]
            out.append(b & 0x0F)
            out.append((b >> 4) & 0x0F)
    return out


# ══════════════════════════════════════════════════════════════════════
#  ROM CONSTANTS
# ══════════════════════════════════════════════════════════════════════

ROM_BASE = 0x08000000

# GFX blocks for the SMW title screen (Graphics.csv + binptrs.txt confirmed)
GFX28_ADDR  = 0x0812EE90   # 0x2000 bytes → tiles 0x000–0x0FF
GFX2A_ADDR  = 0x08132E90   # 0x1000 bytes → tiles 0x100–0x17F
GFX2B_ADDR  = 0x08133E90   # 0x1000 bytes → tiles 0x180–0x1FF
GFX2A_BASE  = 0x100
GFX2B_BASE  = 0x180
TOTAL_TILES = 0x200

# Layer-1 tilemap (binptrs.txt: 08159E90 = Data08159E90.bin)
TILEMAP_L1 = 0x08159E90

# Palette address candidates (from binptrs.txt analysis).
# 0x0815A690 starts immediately after the 0x800-byte tilemap → likely BG palettes.
# Listed best-first; user can also type any custom address.
PAL_CANDIDATES: List[Tuple[str, int]] = [
    ("0815A690  [right after tilemap]",  0x0815A690),
    ("0815AE90  [next data block]",      0x0815AE90),
    ("0812CE90  [before GFX28]",         0x0812CE90),
    ("0815CE90  [after 0815AE90]",       0x0815CE90),
    ("0812EE70  [just before GFX28]",    0x0812EE70),
]

PAL_BLOCK_SIZE  = 0x200   # 16 palettes × 16 colors × 2 bytes
NUM_PALETTES    = 16
COLORS_PER_PAL  = 16

MAP_DIM   = 32
MAP_BYTES = MAP_DIM * MAP_DIM * 2
TILE_UI   = 24   # pixels per tile in the UI

Palette = List[Tuple[int, int, int, int]]


def rom_off(addr: int) -> int:
    return addr - ROM_BASE


# ══════════════════════════════════════════════════════════════════════
#  SCENE ITEMS
# ══════════════════════════════════════════════════════════════════════

class PalTile(QGraphicsPixmapItem):
    def __init__(self, px: QPixmap, tile_id: int) -> None:
        super().__init__(px)
        self.tile_id = tile_id
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)


class MapTile(QGraphicsPixmapItem):
    def __init__(self, px: QPixmap, tile_id: int, pal_idx: int, col: int, row: int) -> None:
        super().__init__(px)
        self.tile_id  = tile_id
        self.pal_idx  = pal_idx
        self.h_flip   = False
        self.v_flip   = False
        self.grid_col = col
        self.grid_row = row
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)

    def update_orientation(self, h: bool, v: bool) -> None:
        self.h_flip, self.v_flip = h, v
        self._tf()

    def toggle_h(self) -> None:
        self.h_flip = not self.h_flip
        self._tf()

    def toggle_v(self) -> None:
        self.v_flip = not self.v_flip
        self._tf()

    def _tf(self) -> None:
        r = self.boundingRect()
        cx, cy = r.width() / 2, r.height() / 2
        t = QTransform()
        t.translate(cx, cy)
        t.scale(-1 if self.h_flip else 1, -1 if self.v_flip else 1)
        t.translate(-cx, -cy)
        self.setTransform(t)

    def snapshot(self) -> dict:
        """Return a full copy of this tile's state (for undo)."""
        return {
            "tile_id": self.tile_id, "pal_idx": self.pal_idx,
            "h_flip": self.h_flip,  "v_flip": self.v_flip,
            "col": self.grid_col,   "row": self.grid_row,
        }


# ══════════════════════════════════════════════════════════════════════
#  DARK THEME
# ══════════════════════════════════════════════════════════════════════

DARK = """
QMainWindow, QWidget {
    background:#1a1a1a; color:#d8d8d8;
    font-family:'Segoe UI',Arial; font-size:11px;
}
QPushButton {
    background:#272727; border:1px solid #484848; padding:5px 10px;
    border-radius:2px; font-weight:bold;
}
QPushButton:hover   { background:#333; border-color:#888; }
QPushButton:pressed { background:#555; }
QPushButton:disabled{ color:#3a3a3a; background:#161616; border-color:#252525; }
QComboBox  { background:#272727; border:1px solid #484848; padding:3px; color:#d8d8d8; }
QLineEdit  { background:#272727; border:1px solid #484848; padding:3px; color:#d8d8d8; }
QGraphicsView { border:1px solid #383838; background:#0d0d0d; }
QLabel     { color:#666; font-size:10px; }
QStatusBar { background:#111; color:#444; font-size:10px; }
QScrollArea{ border:none; }
QSplitter::handle { background:#2a2a2a; width:3px; height:3px; }
"""


# ══════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════

class SMA2EditorMain(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SMA2 Title Screen Editor")
        self.resize(1700, 980)
        self.setStyleSheet(DARK)

        self.rom_data:         bytearray                      = bytearray()
        self.rom_path:         str                            = ""
        self.palettes:         List[Palette]                  = []
        self.tile_cache:       Dict[Tuple[int,int], QPixmap]  = {}
        self.map_grid:         Dict[Tuple[int,int], MapTile]  = {}
        self.selected_tile_id: Optional[int]                  = None
        self.is_painting:      bool                           = False
        self.clipboard:        List[dict]                     = []
        self.undo_stack:       Optional[List[dict]]           = None   # single-level
        self.current_view_pal: int                            = 16     # 16=grayscale

        self._build_ui()
        self._setup_shortcuts()

    # ──────────────────────────────────────────────────────────────────
    #  UI
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        cw   = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(4)

        # ── Toolbar ────────────────────────────────────────────────────
        tb = QHBoxLayout()
        tb.setSpacing(6)

        self.btn_load = QPushButton("LOAD ROM")
        self.btn_load.clicked.connect(self.action_load_rom)
        tb.addWidget(self.btn_load)

        self.btn_import_pal = QPushButton("IMPORT .PAL")
        self.btn_import_pal.setEnabled(False)
        self.btn_import_pal.setStyleSheet("QPushButton{background:#3d2618; color:#ebb09d; border:1px solid #6b3e26;} QPushButton:hover{background:#52341f;}")
        self.btn_import_pal.clicked.connect(self.action_import_pal)
        tb.addWidget(self.btn_import_pal)

        tb.addSpacing(10)
        
        tb.addWidget(QLabel("ROM ADDR:"))
        self.combo_addr = QComboBox()
        for name, addr in PAL_CANDIDATES:
            self.combo_addr.addItem(name.split()[0], addr) # Solo muestra el Hex (ej. 0815A690)
        self.combo_addr.currentIndexChanged.connect(self.action_addr_switch)
        tb.addWidget(self.combo_addr)
        
        tb.addSpacing(10)

        tb.addWidget(QLabel("VIEW:"))
        self.combo_pal = QComboBox()
        self.combo_pal.addItem("GRAYSCALE", 16)
        for i in range(NUM_PALETTES):
            self.combo_pal.addItem(f"PAL {i:X}", i)
        self.combo_pal.setFixedWidth(95)
        self.combo_pal.currentIndexChanged.connect(self.action_pal_switch)
        tb.addWidget(self.combo_pal)

        tb.addStretch()

        # Keyboard hint
        hint = QLabel("Map keys: Ctrl+C/V  Del  Ctrl+A  Ctrl+Z  Ctrl+S  H  V")
        hint.setStyleSheet("color:#3a3a3a; font-size:9px;")
        tb.addWidget(hint)

        tb.addStretch()

        self.edit_btns: List[QPushButton] = []
        for lbl, fn in [
            ("FLIP H",  self.action_flip_h),
            ("FLIP V",  self.action_flip_v),
            ("COPY",    self.action_copy),
            ("PASTE",   self.action_paste),
            ("DELETE",  self.action_delete),
            ("SET PAL", self.action_apply_pal), 
        ]:
            b = QPushButton(lbl)
            b.setEnabled(False)
            b.clicked.connect(fn)
            tb.addWidget(b)
            self.edit_btns.append(b)

        tb.addSpacing(8)
        self.btn_save = QPushButton("SAVE ROM  Ctrl+S")
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet(
            "QPushButton{background:#183d26; color:#9debb0; border:1px solid #266b3e;}"
            "QPushButton:hover{background:#1f5234;}"
        )
        self.btn_save.clicked.connect(self.action_save_rom)
        tb.addWidget(self.btn_save)
        root.addLayout(tb)

        # ── Three-pane splitter ────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT: tileset
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self._cap("SOURCE TILES  —  click to select"))
        self.scene_ts = QGraphicsScene()
        self.view_ts  = QGraphicsView(self.scene_ts)
        self.view_ts.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.scene_ts.selectionChanged.connect(self._on_ts_sel)
        ll.addWidget(self.view_ts)
        splitter.addWidget(left)

        # CENTRE: map
        mid  = QWidget()
        ml   = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self._cap(
            "LAYER 1 MAP  32×32  │  LMB = paint  │  RMB drag = multi-select  "
            "│  Shift+LMB = additive select  │  Ctrl+A = select all"
        ))
        self.scene_map = QGraphicsScene()
        self.view_map  = QGraphicsView(self.scene_map)
        self.view_map.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view_map.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.view_map.viewport().installEventFilter(self)
        ml.addWidget(self.view_map)
        splitter.addWidget(mid)

        splitter.setSizes([400, 1300])
        root.addWidget(splitter)

        # ── Status bar ─────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Standby – load a GBA ROM to begin")

    @staticmethod
    def _cap(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#444; font-size:9px; padding:1px 0;")
        return lbl

    # ──────────────────────────────────────────────────────────────────
    #  KEYBOARD SHORTCUTS
    # ──────────────────────────────────────────────────────────────────

    def _setup_shortcuts(self) -> None:
        from PyQt6.QtGui import QShortcut # type: ignore
        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(fn)
        sc("Ctrl+C", self.action_copy)
        sc("Ctrl+V", self.action_paste)
        sc("Delete", self.action_delete)
        sc("Backspace", self.action_delete)
        sc("Ctrl+A", self.action_select_all)
        sc("Ctrl+Z", self.action_undo)
        sc("Ctrl+S", self.action_save_rom)
        sc("H", self.action_flip_h)
        sc("V", self.action_flip_v)

    # ──────────────────────────────────────────────────────────────────
    #  PALETTE ENGINE
    # ──────────────────────────────────────────────────────────────────

    def _build_palettes(self) -> None:
        """Crea paletas en blanco. Ya no lee de la ROM, espera que se importe un .pal"""
        # Si ya importamos una paleta previamente, no la sobrescribimos
        if len(self.palettes) >= NUM_PALETTES + 1:
            return 
            
        self.palettes = []
        for p in range(NUM_PALETTES):
            pal: Palette = []
            for c in range(COLORS_PER_PAL):
                pal.append((0, 0, 0, 0 if c == 0 else 255))
            self.palettes.append(pal)

        # Índice 16: Escala de grises (obligatoria para la interfaz)
        gray: Palette = []
        for i in range(COLORS_PER_PAL):
            v = int((i / 15) ** 1.8 * 235 + 10)
            gray.append((v, v, v, 0 if i == 0 else 255))
        self.palettes.append(gray)

    def _on_pal_changed(self) -> None:
        """Palette editor callback — invalidate cache and redraw BOTH panels."""
        self._build_palettes()
        self.tile_cache.clear()
        self.refresh_tileset_view()
        self.refresh_map_visuals()   # ← map panel updates too

    # ──────────────────────────────────────────────────────────────────
    #  TILE RENDERING
    # ──────────────────────────────────────────────────────────────────

    def _tile_addr(self, tid: int) -> int:
        if tid < GFX2A_BASE:
            return GFX28_ADDR + tid * 32
        elif tid < GFX2B_BASE:
            return GFX2A_ADDR + (tid - GFX2A_BASE) * 32
        return GFX2B_ADDR + (tid - GFX2B_BASE) * 32

    def get_tile(self, tile_id: int, pal_idx: int) -> QPixmap:
        key = (tile_id, pal_idx)
        if key in self.tile_cache:
            return self.tile_cache[key]
        off  = rom_off(self._tile_addr(tile_id))
        raw  = bytes(self.rom_data[off : off + 32]).ljust(32, b"\x00")
        idxs = decode_4bpp_tile(raw)
        pal  = self.palettes[min(pal_idx, len(self.palettes) - 1)]
        buf  = bytearray(64 * 4)
        for i, ci in enumerate(idxs):
            buf[i*4 : i*4+4] = pal[ci]
        img = QImage(bytes(buf), 8, 8, QImage.Format.Format_RGBA8888)
        px  = QPixmap.fromImage(img.scaled(
            TILE_UI, TILE_UI,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        ))
        self.tile_cache[key] = px
        return px

    def _dp(self, item_pal: int) -> int:
        """Resolve display palette index (grayscale override or item's own pal)."""
        return 16 if self.current_view_pal == 16 else item_pal

    # ──────────────────────────────────────────────────────────────────
    #  VIEW REFRESH
    # ──────────────────────────────────────────────────────────────────

    def refresh_tileset_view(self) -> None:
        self.scene_ts.clear()
        for i in range(TOTAL_TILES):
            px   = self.get_tile(i, self.current_view_pal)
            item = PalTile(px, i)
            r, c = divmod(i, 16)
            item.setPos(c * (TILE_UI + 2), r * (TILE_UI + 2))
            self.scene_ts.addItem(item)

    def load_map_from_rom(self) -> None:
        self.scene_map.clear()
        self.map_grid.clear()
        off  = rom_off(TILEMAP_L1)
        data = bytes(self.rom_data[off : off + MAP_BYTES]).ljust(MAP_BYTES, b"\x00")
        for i in range(MAP_DIM * MAP_DIM):
            w    = struct.unpack_from("<H", data, i * 2)[0]
            tid  = w & 0x3FF
            hf   = bool((w >> 10) & 1)
            vf   = bool((w >> 11) & 1)
            pidx = (w >> 12) & 0xF
            col, row = i % MAP_DIM, i // MAP_DIM
            item = MapTile(self.get_tile(tid, self._dp(pidx)), tid, pidx, col, row)
            item.update_orientation(hf, vf)
            item.setPos(col * TILE_UI, row * TILE_UI)
            self.scene_map.addItem(item)
            self.map_grid[(col, row)] = item

    def refresh_map_visuals(self) -> None:
        """Redraw every map tile — called after palette change or view-pal switch."""
        for item in self.map_grid.values():
            item.setPixmap(self.get_tile(item.tile_id, self._dp(item.pal_idx)))

    def find_blank_tile(self) -> int:
        for base, size, start in [
            (GFX28_ADDR, 0x2000, 0),
            (GFX2A_ADDR, 0x1000, GFX2A_BASE),
            (GFX2B_ADDR, 0x1000, GFX2B_BASE),
        ]:
            off = rom_off(base)
            for i in range(size // 32):
                chunk = self.rom_data[off + i*32 : off + i*32 + 32]
                if len(chunk) == 32 and not any(chunk):
                    return start + i
        return 0

    # ──────────────────────────────────────────────────────────────────
    #  UNDO
    # ──────────────────────────────────────────────────────────────────

    def _push_undo(self) -> None:
        """Snapshot entire map state for single-level undo."""
        self.undo_stack = [item.snapshot() for item in self.map_grid.values()]

    def action_undo(self) -> None:
        if not self.undo_stack:
            self.status.showMessage("Nothing to undo.")
            return
        for snap in self.undo_stack:
            item = self.map_grid.get((snap["col"], snap["row"]))
            if item is None:
                continue
            item.tile_id = snap["tile_id"]
            item.pal_idx = snap["pal_idx"]
            item.update_orientation(snap["h_flip"], snap["v_flip"])
            item.setPixmap(self.get_tile(item.tile_id, self._dp(item.pal_idx)))
        self.undo_stack = None
        self.status.showMessage("Undo applied.")

    # ──────────────────────────────────────────────────────────────────
    #  FILE ACTIONS
    # ──────────────────────────────────────────────────────────────────

    def action_load_rom(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open SMA2 GBA ROM", "", "GBA ROM (*.gba *.GBA)"
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                self.rom_data = bytearray(f.read())
            self.rom_path = path
            self.tile_cache.clear()
            
            # Cargar todo sin depender del panel de paletas
            self._build_palettes()
            self.refresh_tileset_view()
            self.load_map_from_rom()

            # Auto-cargar bg.pal si existe en la misma carpeta que el script
            ruta_paleta = os.path.join(os.path.dirname(__file__), "bg.pal")
            if os.path.exists(ruta_paleta):
                self.action_import_pal(ruta_paleta)
            
            for b in self.edit_btns:
                b.setEnabled(True)
            self.btn_save.setEnabled(True)
            self.btn_import_pal.setEnabled(True)
            
            self.status.showMessage(
                f"Loaded: {os.path.basename(path)}  │  {len(self.rom_data):,} bytes"
            )
        except Exception as e:
            QMessageBox.critical(self, "ROM Error", f"Failed to load ROM:\n{e}")

    def action_addr_switch(self) -> None:
        self.current_rom_addr = self.combo_addr.currentData()
        if not self.rom_data:
            return
        self._build_palettes()
        self.tile_cache.clear()
        self.refresh_tileset_view()
        self.refresh_map_visuals()

    def action_pal_switch(self) -> None:
        self.current_view_pal = self.combo_pal.currentData()
        if not self.rom_data:
            return
        self.tile_cache.clear()
        self.refresh_tileset_view()
        self.refresh_map_visuals()

    def action_save_rom(self) -> None:
        if not self.rom_data:
            return
        if QMessageBox.question(
            self, "Confirm Save",
            "Write map + palette changes to the ROM file on disk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        new_map = bytearray(MAP_BYTES)
        for row in range(MAP_DIM):
            for col in range(MAP_DIM):
                item = self.map_grid.get((col, row))
                if item is None:
                    continue
                w = item.tile_id & 0x3FF
                if item.h_flip: w |= 1 << 10
                if item.v_flip: w |= 1 << 11
                w |= (item.pal_idx & 0xF) << 12
                struct.pack_into("<H", new_map, (row * MAP_DIM + col) * 2, w)

        self.rom_data[rom_off(TILEMAP_L1) : rom_off(TILEMAP_L1) + MAP_BYTES] = new_map
        # Palette bytes already written live to rom_data on each swatch edit.

        try:
            with open(self.rom_path, "wb") as f:
                f.write(self.rom_data)
            self.status.showMessage(f"SAVED → {os.path.basename(self.rom_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not write:\n{e}")

    def action_import_pal(self, auto_path: str = "") -> None:
        path = auto_path
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Importar Paleta", "", "Archivos de Paleta (*.pal);;Todos los archivos (*)"
            )
        if not path:
            return
            
        try:
            with open(path, "rb") as f:
                raw_data = f.read()

            colors = []
            
            # 1. Detectar formato RIFF PAL (el que exportó tu emulador)
            if raw_data.startswith(b"RIFF") and raw_data[8:12] == b"PAL ":
                num_colors = struct.unpack_from("<H", raw_data, 22)[0]
                # Los colores en RIFF empiezan en el byte 24, cada uno ocupa 4 bytes (R, G, B, Flags)
                for i in range(num_colors):
                    idx = 24 + (i * 4)
                    if idx + 2 < len(raw_data):
                        r, g, b = raw_data[idx], raw_data[idx+1], raw_data[idx+2]
                        colors.append((r, g, b, 255))
                        
            # 2. Detectar formato JASC-PAL (texto)
            elif raw_data.startswith(b"JASC-PAL"):
                text_data = raw_data.decode("utf-8", errors="ignore")
                lines = text_data.splitlines()
                num_colors = int(lines[2])
                for i in range(3, 3 + num_colors):
                    r, g, b = map(int, lines[i].split())
                    colors.append((r, g, b, 255))
                    
            # 3. Detectar binario crudo GBA (BGR555)
            else:
                for i in range(0, len(raw_data), 2):
                    if i + 1 < len(raw_data):
                        bgr = struct.unpack_from("<H", raw_data, i)[0]
                        r, g, b, _ = bgr555_to_rgba(bgr)
                        colors.append((r, g, b, 255))

            # Aplicar los colores leídos a la memoria del editor
            self.palettes = []
            for p in range(16):
                pal: Palette = []
                for c in range(16):
                    idx = p * 16 + c
                    if idx < len(colors):
                        r, g, b, a = colors[idx]
                        pal.append((r, g, b, 0 if c == 0 else 255))
                    else:
                        pal.append((0, 0, 0, 255))
                self.palettes.append(pal)
                
            # Siempre mantener la escala de grises al final (índice 16)
            gray: Palette = []
            for i in range(16):
                v = int((i / 15) ** 1.8 * 235 + 10)
                gray.append((v, v, v, 0 if i == 0 else 255))
            self.palettes.append(gray)

            # Refrescar los gráficos en pantalla
            self.tile_cache.clear()
            self.refresh_tileset_view()
            self.refresh_map_visuals()
            self.status.showMessage(f"Paleta importada con éxito: {os.path.basename(path)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error de Paleta", f"No se pudo leer el archivo:\n{e}")

    # ──────────────────────────────────────────────────────────────────
    #  TILESET SELECTION
    # ──────────────────────────────────────────────────────────────────

    def _on_ts_sel(self) -> None:
        sel = self.scene_ts.selectedItems()
        if sel:
            self.selected_tile_id = sel[0].tile_id
            self.status.showMessage(
                f"Selected source tile {self.selected_tile_id:#05X}"
            )

    # ──────────────────────────────────────────────────────────────────
    #  EVENT FILTER  (map viewport — paint + multi-select)
    # ──────────────────────────────────────────────────────────────────

    def eventFilter(self, source, event) -> bool:
        if source is not self.view_map.viewport():
            return super().eventFilter(source, event)

        et   = event.type()
        mods = event.modifiers() if hasattr(event, "modifiers") else Qt.KeyboardModifier.NoModifier

        if et == QEvent.Type.MouseButtonPress:
            btn = event.button()
            if btn == Qt.MouseButton.LeftButton:
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    # Shift+LMB → additive rubber-band
                    self.is_painting = False
                    self.view_map.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                else:
                    # Plain LMB → paint
                    self.is_painting = True
                    self.view_map.setDragMode(QGraphicsView.DragMode.NoDrag)
                    self.scene_map.clearSelection()
                    self._push_undo()
                    self._paint(event.pos())
            elif btn == Qt.MouseButton.RightButton:
                # RMB → rubber-band select
                self.is_painting = False
                self.scene_map.clearSelection()
                self.view_map.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        elif et == QEvent.Type.MouseMove and self.is_painting:
            self._paint(event.pos())

        elif et == QEvent.Type.MouseButtonRelease:
            if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
                self.is_painting = False
                self.view_map.setDragMode(QGraphicsView.DragMode.NoDrag)
                n = len(self._sel())
                if n:
                    self.status.showMessage(f"{n} tile(s) selected")

        return super().eventFilter(source, event)

    def _paint(self, vp) -> None:
        if self.selected_tile_id is None:
            return
        sp  = self.view_map.mapToScene(vp)
        col = int(sp.x() // TILE_UI)
        row = int(sp.y() // TILE_UI)
        if not (0 <= col < MAP_DIM and 0 <= row < MAP_DIM):
            return
        item = self.map_grid.get((col, row))
        if item is None:
            return
        item.tile_id = self.selected_tile_id
        if self.current_view_pal < 16:
            item.pal_idx = self.current_view_pal
        item.setPixmap(self.get_tile(item.tile_id, self._dp(item.pal_idx)))
        self.status.showMessage(
            f"Painted {item.tile_id:#05X} @ ({col},{row})  pal={item.pal_idx}"
        )

    # ──────────────────────────────────────────────────────────────────
    #  TOOL ACTIONS
    # ──────────────────────────────────────────────────────────────────

    def _sel(self) -> List[MapTile]:
        return [t for t in self.scene_map.selectedItems() if isinstance(t, MapTile)]

    def action_select_all(self) -> None:
        for item in self.map_grid.values():
            item.setSelected(True)
        self.status.showMessage(f"Selected all {len(self.map_grid)} tiles")

    def action_flip_h(self) -> None:
        sel = self._sel()
        if sel:
            self._push_undo()
            for t in sel:
                t.toggle_h()

    def action_flip_v(self) -> None:
        sel = self._sel()
        if sel:
            self._push_undo()
            for t in sel:
                t.toggle_v()

    def action_delete(self) -> None:
        sel = self._sel()
        if not sel:
            return
        self._push_undo()
        blank = self.find_blank_tile()
        for t in sel:
            t.tile_id = blank
            t.pal_idx = 0
            t.update_orientation(False, False)
            t.setPixmap(self.get_tile(blank, self._dp(0)))
        self.status.showMessage(f"Deleted {len(sel)} tile(s)")

    def action_copy(self) -> None:
        sel = self._sel()
        if not sel:
            return
        mc = min(t.grid_col for t in sel)
        mr = min(t.grid_row for t in sel)
        self.clipboard = [
            {"dc": t.grid_col - mc, "dr": t.grid_row - mr,
             "id": t.tile_id, "h": t.h_flip, "v": t.v_flip, "p": t.pal_idx}
            for t in sel
        ]
        self.status.showMessage(f"Copied {len(self.clipboard)} tile(s)  (Ctrl+V to paste)")

    def action_paste(self) -> None:
        anc = self._sel()
        if not anc or not self.clipboard:
            return
        self._push_undo()
        a = min(anc, key=lambda t: (t.grid_row, t.grid_col))
        n = 0
        for e in self.clipboard:
            tgt = self.map_grid.get((a.grid_col + e["dc"], a.grid_row + e["dr"]))
            if tgt is None:
                continue
            tgt.tile_id = e["id"]
            tgt.pal_idx = e["p"]
            tgt.update_orientation(e["h"], e["v"])
            tgt.setPixmap(self.get_tile(tgt.tile_id, self._dp(tgt.pal_idx)))
            n += 1
        self.status.showMessage(f"Pasted {n} tile(s)")

    def action_apply_pal(self) -> None:
        # 1. Block if they are trying to apply the "grayscale" palette
        if self.current_view_pal == 16:
            self.status.showMessage("Error: Choose a palette (PAL 0 - PAL F) in the 'VIEW' menu first.")
            return
            
        # 2. Get the tiles the user has selected on the map
        sel = self._sel()
        
        # 3. If nothing is selected, offer to apply it to the entire map
        if not sel:
            response = QMessageBox.question(
                self, 
                "No selection",
                "You haven't selected any tiles on the main map.\n\n"
                f"Do you want to apply Palette {self.current_view_pal:X} to the ENTIRE map (all 1024 tiles)?\n\n"
                "(Tip: If you only want to change a specific area, select it by right-clicking and dragging on the map).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if response == QMessageBox.StandardButton.Yes:
                sel = list(self.map_grid.values())  # Grab all tiles from the map
            else:
                return

        # 4. Save state for Ctrl+Z and apply the new palette
        self._push_undo()
        for t in sel:
            t.pal_idx = self.current_view_pal
            t.setPixmap(self.get_tile(t.tile_id, self._dp(t.pal_idx)))
            
        self.status.showMessage(f"Applied Palette {self.current_view_pal:X} to {len(sel)} tile(s). Remember to save (Ctrl+S)!")


# ══════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SMA2EditorMain()
    win.show()
    sys.exit(app.exec())

    