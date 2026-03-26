# SMA2 Title Screen Editor

A Graphical User Interface (GUI) tool developed in Python and PyQt6 to edit the title screen (Layer 1 map and palettes) of **Super Mario World: Super Mario Advance 2** for the Game Boy Advance (GBA).

This editor allows you to visually and intuitively modify the tile layout, apply different color palettes, and save the changes directly to your ROM file.

![Screenshot](screenshot.png)

---

## Key Features

- **Visual Map Editing (32x32):** A split-interface featuring a source tile selection panel and an interactive map canvas.  
- **Real-Time Refresh:** Palette changes instantly update the entire map to prevent stale tile visuals.  
- **Flexible Palette Import:** Supports multiple `.pal` file formats so you can work with your favorite graphics editor:
  - RIFF PAL (standard format exported by many emulators)
  - JASC-PAL (text format)
  - Raw GBA Binary (BGR555)
- **Auto-Load Palette:** If a file named `bg.pal` exists in the same directory as the script, it will load automatically when you open a ROM.  
- **View Modes:** Option to view the map in grayscale for a structure-focused design, or preview any of the 16 hardware palettes.  
- **Hex Address Modification:** Includes a dropdown menu with candidate palette addresses (e.g., `0815A690`, `0815AE90`) discovered via reverse engineering, ready to be tested.  

---

## Requirements

- **Python 3.7** or higher  
- **PyQt6** (GUI library)  

Install dependencies with:

```bash
pip install PyQt6
```

---

## How to Use

1. Ensure you have Python and PyQt6 installed.  
2. Download the `SMA2 Title Screen Editor.py` file.  
3. Run the script:

```bash
python "SMA2 Title Screen Editor.py"
```

4. Click **LOAD ROM** and select your Super Mario Advance 2 `.gba` file.  
5. Click **IMPORT .PAL** to load the correct colors if the graphics appear in grayscale.  
6. Start editing! When finished, press **SAVE ROM** (or `Ctrl+S`).  

---

## Controls and Keyboard Shortcuts

### Mouse Controls on the Map

| Action | Result |
| :--- | :--- |
| **Left Click (LMB)** | Paints the selected source tile onto the canvas |
| **Right Click (RMB) + Drag** | Creates a multi-selection box |
| **Shift + Left Click** | Adds tiles to the current selection |

---

### Keyboard Shortcuts

| Key | Function |
| :--- | :--- |
| `Ctrl + C` | Copy selected tiles |
| `Ctrl + V` | Paste copied tiles |
| `Del` / `Backspace` | Delete selected tiles |
| `Ctrl + A` | Select all tiles |
| `Ctrl + Z` | Undo last action (single-level) |
| `Ctrl + S` | Save ROM |
| `H` | Flip tiles horizontally |
| `V` | Flip tiles vertically |

---
update test
