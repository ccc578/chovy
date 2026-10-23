# -*- coding: utf-8 -*-
"""全局深色主题，使侧边栏/面板与深色画布保持一致。"""
from __future__ import annotations

DARK_QSS = """
QWidget {
    background-color: #23262a;
    color: #d4d4d4;
    font-size: 12px;
}
QMainWindow, QDialog {
    background-color: #23262a;
}
QLabel {
    background: transparent;
    color: #d4d4d4;
}
QGroupBox {
    border: 1px solid #3a3d42;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #aebccb;
}
QPushButton {
    background-color: #33373d;
    border: 1px solid #44484f;
    border-radius: 4px;
    padding: 4px 8px;
    color: #d4d4d4;
}
QPushButton:hover { background-color: #3c4148; }
QPushButton:pressed { background-color: #2a2d32; }
QPushButton:checked {
    background-color: #2f6fb8;
    border-color: #2f6fb8;
    color: #ffffff;
}
QPushButton:disabled { color: #666666; }
QLineEdit, QSpinBox, QComboBox {
    background-color: #1b1d20;
    border: 1px solid #3a3d42;
    border-radius: 3px;
    padding: 3px 5px;
    color: #d4d4d4;
    selection-background-color: #2f6fb8;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background-color: #26282c;
    border: 1px solid #3a3d42;
    selection-background-color: #2f6fb8;
    color: #d4d4d4;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #1b1d20;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -4px 0;
    background: #2f6fb8;
    border-radius: 7px;
}
QCheckBox { color: #d4d4d4; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #3a3d42;
    border-radius: 3px;
    background: #1b1d20;
}
QCheckBox::indicator:checked {
    background: #2f6fb8;
    border-color: #2f6fb8;
}
QTabWidget::pane {
    border: 1px solid #3a3d42;
    border-radius: 4px;
    top: -1px;
}
QTabBar::tab {
    background: #2a2d32;
    border: 1px solid #3a3d42;
    padding: 5px 12px;
    color: #9a9a9a;
}
QTabBar::tab:selected {
    background: #1b1d20;
    color: #d4d4d4;
}
QTabBar::tab:hover { color: #d4d4d4; }
QListWidget {
    background-color: #1b1d20;
    border: none;
    outline: none;
}
QListWidget::item {
    color: #d4d4d4;
    border-radius: 4px;
    padding: 2px;
}
QListWidget::item:selected {
    background-color: #2f6fb8;
    color: #ffffff;
}
QListWidget::item:hover { background-color: #33373d; }
QMenuBar { background-color: #23262a; }
QMenuBar::item { padding: 4px 8px; color: #d4d4d4; }
QMenuBar::item:selected { background: #33373d; }
QMenu {
    background-color: #26282c;
    border: 1px solid #3a3d42;
    color: #d4d4d4;
}
QMenu::item { padding: 4px 20px; }
QMenu::item:selected { background: #2f6fb8; }
QMenu::separator { height: 1px; background: #3a3d42; }
QToolBar { background: #23262a; border: none; spacing: 4px; }
QStatusBar { background: #23262a; color: #9a9a9a; }
QScrollBar:vertical { background: #1b1d20; width: 10px; margin: 0; }
QScrollBar::handle:vertical {
    background: #3a3d42;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #4a4e55; }
QScrollBar:horizontal { background: #1b1d20; height: 10px; margin: 0; }
QScrollBar::handle:horizontal {
    background: #3a3d42;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QProgressBar {
    border: 1px solid #3a3d42;
    border-radius: 3px;
    text-align: center;
    color: #d4d4d4;
    background: #1b1d20;
}
QProgressBar::chunk { background-color: #2f6fb8; border-radius: 3px; }
QToolTip {
    background-color: #26282c;
    color: #d4d4d4;
    border: 1px solid #3a3d42;
    padding: 2px;
}
QSplitter::handle { background: #1b1d20; }
"""
