import sys
from typing import Dict

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import (
    QFont, QColor, QSyntaxHighlighter, QTextCharFormat,
    QAction, QIcon, QPainter, QPen
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTabWidget, QTextEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QFileDialog,
    QMessageBox, QToolBar, QLabel, QHeaderView, QAbstractItemView, QTabBar, QToolButton, QSizePolicy
)

from SQL_compiler.execution.executor import QueryExecutor
from SQL_compiler.execution.table import Table, ExcelLoader
from SQL_compiler.parsing.parser import parse


class CustomTabBar(QTabBar):
    """Кастомный TabBar с правильной обработкой закрытия"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QTabBar::tab {
                background-color: #1E1E1E;
                color: #808080;
                padding: 5px 20px 5px 15px;
                margin-right: 0px;
                border: none;
                min-width: 80px;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            QTabBar::tab:selected {
                background-color: #2D2D2D;
                color: #E0E0E0;
            }
            QTabBar::tab:hover {
                background-color: #2A2A2A;
            }
            QTabBar::tab:!selected {
                background-color: #1E1E1E;
            }
            QTabBar::close-button {
                image: none;
                subcontrol-position: right;
                subcontrol-origin: padding;
                margin-right: 10px;
                right: -3px;
            }
        """)

        # Создаем кнопки закрытия для существующих вкладок
        for i in range(self.count()):
            self.setup_close_button(i)

    def setup_close_button(self, index):
        close_button = QToolButton(self)
        close_button.setText("×")
        close_button.setFixedSize(18, 18)

        close_button.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #888;
                font-size: 14px;
            }
            QToolButton:hover {
                color: #fff;
            }
        """)

        def on_close_clicked():
            for i in range(self.count()):
                if self.tabButton(i, QTabBar.RightSide) is close_button:
                    self.tabCloseRequested.emit(i)
                    break

        close_button.clicked.connect(on_close_clicked)
        self.setTabButton(index, QTabBar.RightSide, close_button)

    def tabInserted(self, index):
        """Вызывается при добавлении новой вкладки"""
        super().tabInserted(index)
        self.setup_close_button(index)


class CustomTabWidget(QTabWidget):
    """
    Кастомный TabWidget:
    - кастомный TabBar
    - кнопка "+"
    - удобные методы для поиска / активации вкладок
    """

    def __init__(self, parent=None, show_add_button=True):
        super().__init__(parent)

        self.setTabBar(CustomTabBar(self))
        self.setTabsClosable(True)

        self.show_add_button = show_add_button
        self.add_button = None

        if self.show_add_button:
            self.add_button = QToolButton(self)
            self.add_button.setText("+")
            self.add_button.setToolTip("New tab")
            self.add_button.setCursor(Qt.PointingHandCursor)
            self.add_button.setFixedHeight(24)

            self.add_button.setStyleSheet("""
                QToolButton {
                    background-color: transparent;
                    color: #808080;
                    border: none;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 4px 8px;
                    border-radius: 4px;
                }
                QToolButton:hover {
                    color: #CCCCCC;
                }
            """)

            self.add_button.clicked.connect(self.on_add_clicked)

        self.setStyleSheet("""
                    QTabBar::tab {
                        background-color: #1E1E1E;
                        color: #808080;
                        padding: 4px 8px 4px ; 
                        margin-right: 0px;
                        border: none;
                        min-width: 80px; 
                    }
                    QTabBar::tab:selected {
                        background-color: #2D2D2D;
                        color: #E0E0E0;
                    }
                    QTabBar::tab:hover {
                        background-color: #2A2A2A;
                    }
                    QTabBar::tab:!selected {
                        background-color: #1E1E1E;
                    }
                    QTabBar::close-button {
                        image: none;
                        subcontrol-position: right;
                        subcontrol-origin: padding;
                        margin-right: 10px;
                        right: -3px;
                    }
                """)

    def find_tab_by_text(self, text: str) -> int:
        """Вернуть индекс вкладки по имени или -1"""
        for i in range(self.count()):
            if self.tabText(i) == text:
                return i
        return -1

    def activate_tab(self, text: str) -> bool:
        """Активировать вкладку, если существует"""
        index = self.find_tab_by_text(text)
        if index != -1:
            self.setCurrentIndex(index)
            return True
        return False

    def add_tab_unique(self, widget: QWidget, title: str):
        """
        Добавить вкладку только если её нет.
        Если есть — просто активировать.
        """
        index = self.find_tab_by_text(title)
        if index != -1:
            self.setCurrentIndex(index)
            return index

        index = self.addTab(widget, title)
        self.setCurrentIndex(index)
        self.update_add_button_position()
        return index

    def on_add_clicked(self):
        """Переопределяется снаружи"""
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_add_button_position()

    def update_add_button_position(self):
        if not self.show_add_button or not self.add_button:
            return

        tab_bar = self.tabBar()

        if self.count() > 0:
            last_tab_rect = tab_bar.tabRect(self.count() - 1)
            x = last_tab_rect.right() + 6
        else:
            x = 6

        y = (tab_bar.height() - self.add_button.height()) // 2
        self.add_button.move(x, y)


class SQLSyntaxHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса SQL"""

    def __init__(self, document):
        super().__init__(document)

        self.keywords = [
            'SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE', 'DELETE',
            'CREATE', 'DROP', 'ALTER', 'TABLE', 'INDEX', 'VIEW',
            'JOIN', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'ON',
            'GROUP BY', 'ORDER BY', 'HAVING', 'UNION', 'ALL',
            'AND', 'OR', 'NOT', 'IN', 'EXISTS', 'BETWEEN', 'LIKE',
            'NULL', 'TRUE', 'FALSE', 'DISTINCT', 'AS', 'INTO',
            'VALUES', 'SET', 'LIMIT', 'OFFSET'
        ]

        self.functions = [
            'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COALESCE',
            'CAST', 'CONVERT', 'SUBSTRING', 'UPPER', 'LOWER',
            'LENGTH', 'TRIM', 'ROUND', 'DATE', 'DATETIME'
        ]

        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#569CD6"))
        self.keyword_format.setFontWeight(QFont.Bold)

        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor("#DCDCAA"))

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#CE9178"))

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#B5CEA8"))

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#6A9955"))

    def highlightBlock(self, text):
        # Подсветка комментариев
        if '--' in text:
            index = text.index('--')
            self.setFormat(index, len(text) - index, self.comment_format)

        # Подсветка строк
        in_string = False
        string_start = 0
        for i, char in enumerate(text):
            if char == "'" and not in_string:
                in_string = True
                string_start = i
            elif char == "'" and in_string:
                in_string = False
                self.setFormat(string_start, i - string_start + 1, self.string_format)

        # Подсветка ключевых слов
        for keyword in self.keywords:
            index = text.upper().find(keyword)
            while index >= 0:
                if (index == 0 or not text[index - 1].isalnum()) and \
                        (index + len(keyword) == len(text) or not text[index + len(keyword)].isalnum()):
                    self.setFormat(index, len(keyword), self.keyword_format)
                index = text.upper().find(keyword, index + 1)

        # Подсветка функций
        for func in self.functions:
            index = text.upper().find(func + '(')
            while index >= 0:
                if index == 0 or not text[index - 1].isalnum():
                    self.setFormat(index, len(func), self.function_format)
                index = text.upper().find(func + '(', index + 1)


class ModernTreeWidget(QTreeWidget):
    """Современное дерево для отображения структуры БД"""

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setIndentation(10)  # Уменьшаем отступы для веток
        self.setStyleSheet("""
                    QTreeWidget {
                        background-color: #1E1E1E;
                        color: #CCCCCC;
                        border: none;
                        border-radius: 8px;
                        padding: 5px;
                        font-size: 16px;
                    }
                    QTreeWidget::item {
                        padding: 6px;
                        border-radius: 4px;
                        color: #CCCCCC;
                        background-color: transparent;
                    }
                    QTreeWidget::item:hover {
                        background-color: transparent;
                    }
                    QTreeWidget::item:selected {
                        background-color: transparent;
                        color: #CCCCCC;
                    }
                    QTreeWidget::branch {
                        background: transparent;
                    }
                    QTreeWidget::branch:closed:has-children {
                        image: url(icons/tick_right.svg);
                        width: 5px;
                        height: 5px;
                    }
                    QTreeWidget::branch:open:has-children {
                        image: url(icons/tick_down.svg);
                        width: 5px;
                        height: 5px;
                    }
                """)

    def mousePressEvent(self, event):
        """Обработка нажатия мыши для расширения области клика по ветви"""
        pos = event.position().toPoint()
        item = self.itemAt(pos)

        if item and item.childCount() > 0:
            # Получаем прямоугольник элемента
            index = self.indexFromItem(item)
            rect = self.visualRect(index)

            # Область для ветки (первые 20 пикселей, учитывая отступ)
            branch_rect = QRect(rect.x() + 5, rect.y(), 20, rect.height())

            if branch_rect.contains(pos):
                # Переключаем состояние развернуто/свернуто
                item.setExpanded(not item.isExpanded())
                return

        super().mousePressEvent(event)

    # def drawBranches(self, painter, rect, index):
    #     """Кастомная отрисовка ветвей дерева"""
    #     painter.setRenderHint(QPainter.Antialiasing)
    #
    #     if self.model().hasChildren(index):
    #         painter.setPen(QPen(QColor("#808080"), 1))
    #
    #         center_x = rect.x() + 15  # Фиксированная позиция для плюсика
    #         center_y = rect.y() + rect.height() // 2
    #
    #         if self.isExpanded(index):
    #             # Рисуем минус
    #             painter.drawLine(center_x - 4, center_y, center_x + 4, center_y)
    #         else:
    #             # Рисуем плюс
    #             painter.drawLine(center_x - 4, center_y, center_x + 4, center_y)
    #             painter.drawLine(center_x, center_y - 4, center_x, center_y + 4)


class ModernTableWidget(QTableWidget):
    """Таблица для отображения результатов"""

    def __init__(self, stretch_columns=False):
        super().__init__()
        self.stretch_columns = stretch_columns
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(True)
        self.verticalHeader().setDefaultAlignment(Qt.AlignCenter)

        self.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                gridline-color: #2D2D2D;
                border: none;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
                border-bottom: 1px solid #2D2D2D;
                border-right: 1px solid #2D2D2D;
            }
            QTableWidget::item:selected {
                background-color: #3E3E3E;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #E0E0E0;
                padding: 8px;
                border: none;
                border-right: 1px solid #3E3E3E;
                border-bottom: 2px solid #3E3E3E;
                font-weight: bold;
            }
            QTableWidget QTableCornerButton::section {
                background-color: #252526;
                border: 1px solid #3E3E3E;
            }
            QHeaderView::section:vertical {
                background-color: #252526;
                color: #808080;
                border-right: 2px solid #3E3E3E;
                border-bottom: 1px solid #2D2D2D;
                padding: 4px 8px;
            }
        """)

    def setDataFrame(self, df, stretch=True):
        """Заполнение таблицы из DataFrame"""
        self.setRowCount(len(df))
        self.setColumnCount(len(df.columns))
        self.setHorizontalHeaderLabels(df.columns)

        # Устанавливаем номера строк
        row_headers = [str(i + 1) for i in range(len(df))]
        self.setVerticalHeaderLabels(row_headers)

        for i, row in df.iterrows():
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.setItem(i, j, item)

        if stretch:
            header = self.horizontalHeader()
            for j in range(len(df.columns)):
                header.setSectionResizeMode(j, QHeaderView.Stretch)
        else:
            self.resizeColumnsToContents()


class ModernSQLTextEdit(QTextEdit):
    """Редактор SQL с подсветкой синтаксиса"""

    def __init__(self):
        super().__init__()
        self.default_font = QFont("Consolas", 11)
        self.setFont(self.default_font)
        self.setStyleSheet("""
                    QTextEdit {
                        background-color: #1E1E1E;
                        color: #D4D4D4;
                        border: none;
                        border-radius: 8px;
                        padding: 10px;
                        selection-background-color: #264F78;
                        font-family: Consolas, Monaco, monospace;
                        font-size: 11pt;
                    }
                """)
        self.highlighter = SQLSyntaxHighlighter(self.document())
        self.setTabStopDistance(40)
        self.setAcceptRichText(False)

    def insertFromMimeData(self, source):
        """Переопределяем вставку для очистки форматирования"""
        if source.hasText():
            # Вставляем только обычный текст без форматирования
            self.insertPlainText(source.text())

    def canInsertFromMimeData(self, source):
        """Разрешаем вставку текста"""
        return source.hasText()


class DatabaseViewer(QMainWindow):
    """Главное окно приложения"""

    def __init__(self):
        super().__init__()
        self.current_db = None
        self.db_tables = {}
        self.query_counter = 1
        self.table_view_counter = 1
        self.open_table_tabs = {}  # table_name -> tab index
        self.left_panel_visible = True
        self.sql_executor = None
        self.init_ui()
        self.apply_dark_theme()

    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle("SQL Query Tool")
        self.setGeometry(100, 100, 1400, 900)

        # Создание центрального виджета
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(5)

        # Создание меню
        self.create_menu_bar()

        # Создание тулбара
        # self.create_toolbar()

        # Основной сплиттер
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Левая панель - дерево БД
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.db_tree = ModernTreeWidget()
        self.db_tree.itemClicked.connect(self.on_tree_item_clicked)
        left_layout.addWidget(self.db_tree)

        self.left_panel = left_widget
        self.main_splitter.addWidget(left_widget)

        # Правая панель
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        # Верхняя часть правой панели - редактор запросов
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(3, 0, 0, 0)  # Добавляем отступ слева
        editor_layout.setSpacing(5)

        # Кнопки управления запросами
        buttons_container = QWidget()
        buttons_container.setSizePolicy(
            QSizePolicy.Maximum,
            QSizePolicy.Fixed
        )
        buttons_container.setStyleSheet("""
            QWidget {
                background-color: #252526;
                border-radius: 8px;
                padding: 6px;
            }
        """)

        query_buttons_layout = QHBoxLayout(buttons_container)
        query_buttons_layout.setSpacing(6)
        query_buttons_layout.setContentsMargins(6, 4, 6, 4)

        self.execute_btn = self.make_icon_button("icons/execute.svg", "Execute")
        self.execute_btn.clicked.connect(self.execute_query)

        self.save_query_btn = self.make_icon_button("icons/save.svg", "Save Query")
        self.save_query_btn.clicked.connect(self.save_query_to_file)

        self.load_script_btn = self.make_icon_button("icons/load.svg", "Load Script")
        self.load_script_btn.clicked.connect(self.load_script)

        query_buttons_layout.addWidget(self.execute_btn)
        query_buttons_layout.addWidget(self.save_query_btn)
        query_buttons_layout.addWidget(self.load_script_btn)
        query_buttons_layout.addStretch()
        editor_layout.addWidget(buttons_container)
        editor_layout.addLayout(query_buttons_layout)

        # Вкладки для запросов
        self.query_tabs = CustomTabWidget(show_add_button=True)
        self.query_tabs.tabCloseRequested.connect(self.close_query_tab)
        self.query_tabs.add_button.clicked.connect(self.create_new_query_tab)

        # Создаем первую вкладку для запросов
        self.create_new_query_tab()

        editor_layout.addWidget(self.query_tabs)

        # Нижняя часть правой панели - результаты
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(3, 0, 0, 0)  # Добавляем отступ слева

        results_header_layout = QHBoxLayout()

        results_label = QLabel("Query Results")
        results_label.setStyleSheet("color: #CCCCCC; font-weight: bold; padding: 5px;")

        self.rows_info_label = QLabel("")
        self.rows_info_label.setStyleSheet("color: #808080; padding: 5px;")

        results_header_layout.addWidget(results_label)
        results_header_layout.addStretch()
        results_header_layout.addWidget(self.rows_info_label)

        results_layout.addLayout(results_header_layout)

        self.results_table = ModernTableWidget()
        results_layout.addWidget(self.results_table)

        # Создаем сплиттер для редактора и результатов
        vertical_splitter = QSplitter(Qt.Vertical)
        vertical_splitter.addWidget(editor_widget)
        vertical_splitter.addWidget(results_widget)
        vertical_splitter.setSizes([400, 400])

        right_layout.addWidget(vertical_splitter)

        # Вкладки для просмотра таблиц
        self.table_tabs = CustomTabWidget(show_add_button=False)
        self.table_tabs.tabCloseRequested.connect(self.close_table_tab)
        self.table_tabs.setVisible(False)
        right_layout.addWidget(self.table_tabs)

        self.main_splitter.addWidget(right_widget)
        self.main_splitter.setSizes([300, 1100])

        main_layout.addWidget(self.main_splitter)

    def make_icon_button(self, icon_path, tooltip):
        btn = QPushButton()
        btn.setIcon(QIcon(icon_path))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(32, 32)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:hover {
                background: transparent;
            }
            QPushButton:pressed {
                background: transparent;
            }
        """)
        return btn

    def create_menu_bar(self):
        """Создание меню"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border-bottom: 1px solid #3E3E3E;
                padding: 4px;
            }
            QMenuBar::item {
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #3E3E3E;
                border-radius: 4px;
            }
            QMenu {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #3E3E3E;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 8px 6px 8px;  
                margin: 2px 4px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #404040;  
                color: #FFFFFF;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3E3E3E;
                margin: 4px 8px;
            }
        """)

        # Меню File
        file_menu = menubar.addMenu("File")

        load_db_action = QAction("Load Database (Excel)", self)
        load_db_action.triggered.connect(self.load_database)
        file_menu.addAction(load_db_action)

        load_script_action = QAction("Load SQL Script", self)
        load_script_action.triggered.connect(self.load_script)
        file_menu.addAction(load_script_action)

        save_script_action = QAction("Save Current Script", self)
        save_script_action.triggered.connect(self.save_query_to_file)
        file_menu.addAction(save_script_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню View
        view_menu = menubar.addMenu("View")

        toggle_panel_action = QAction("Toggle Left Panel", self)
        toggle_panel_action.triggered.connect(self.toggle_left_panel)
        view_menu.addAction(toggle_panel_action)

    def create_toolbar(self):
        """Создание тулбара"""
        toolbar = QToolBar()
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #2D2D2D;
                border: none;
                border-radius: 6px;
                padding: 4px;
                spacing: 0px;
            }
            QToolBar::separator {
                width: 0px;
                height: 0px;
            }
            QToolButton {
                background-color: transparent;
                color: #CCCCCC;
                border-radius: 4px;
                padding: 6px 12px;
                margin: 0px 2px;
            }
            QToolButton:hover {
                background-color: #3E3E3E;
            }
            QToolButton:pressed {
                background-color: #094771;
            }
        """)
        self.addToolBar(toolbar)

        # Кнопка переключения левой панели
        toggle_panel_btn = QToolButton()
        toggle_panel_btn.setIcon(QIcon("icons/left_bar.svg"))
        # toggle_panel_btn.setIconSize(QSize(14, 14))
        toggle_panel_btn.setFixedSize(QSize(40, 40))

        toggle_panel_btn.setToolTip("Toggle Left Panel")
        toggle_panel_btn.clicked.connect(self.toggle_left_panel)
        # toggle_panel_btn.setStyleSheet("""
        #     QToolButton {
        #         font-size: 16px;
        #         font-weight: bold;
        #     }
        # """)
        toolbar.addWidget(toggle_panel_btn)

        # Добавляем действия
        load_db_btn = QPushButton("Load DB")
        load_db_btn.clicked.connect(self.load_database)
        load_db_btn.setStyleSheet(self.get_button_style("#3E3E3E", "#4E4E4E"))
        toolbar.addWidget(load_db_btn)

    def toggle_left_panel(self):
        """Переключение видимости левой панели"""
        if self.left_panel_visible:
            self.left_panel.hide()
            self.left_panel_visible = False
        else:
            self.left_panel.show()
            self.left_panel_visible = True

    def get_button_style(self, bg_color, hover_color):
        """Стиль для кнопок"""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {bg_color};
            }}
        """

    def apply_dark_theme(self):
        """Применение темной темы"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1E1E1E;
            }
            QWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
            }
            QSplitter::handle {
                background-color: #3E3E3E;
                width: 2px;
                height: 2px;
            }
            QScrollBar:vertical {
                background-color: #2D2D2D;
                width: 5px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #5E5E5E;
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #7E7E7E;
            }
            QScrollBar:horizontal {
                background-color: #2D2D2D;
                height: 5px;
                border-radius: 2px;
            }
            QScrollBar::handle:horizontal {
                background-color: #5E5E5E;
                border-radius: 2px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #7E7E7E;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                border: none;
                background: none;
                width: 0px;
                height: 0px;
            }
            QScrollBar::add-page, QScrollBar::sub-page {
                background: none;
            }
        """)

    def load_database(self):
        """Загрузка базы данных из Excel с правильными типами"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Database", "", "Excel Files (*.xlsx *.xls)"
        )

        if file_path:
            try:
                # Используем наш ExcelLoader вместо прямого чтения pandas
                loader = ExcelLoader()
                executor_tables = loader.load(file_path)

                # Сохраняем таблицы для отображения в дереве
                self.db_tables = {}
                for name, table in executor_tables.items():
                    # Конвертируем обратно в DataFrame для отображения
                    data = []
                    for row in table.rows:
                        data.append(row.copy())
                    self.db_tables[name] = pd.DataFrame(data)

                # Инициализируем executor с таблицами
                self.query_executor = QueryExecutor(executor_tables)

                self.update_db_tree()

                # QMessageBox.information(self, "Success", f"Loaded {len(executor_tables)} tables")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load database: {str(e)}")
                import traceback
                traceback.print_exc()

    def _convert_df_to_tables(self, db_tables: Dict[str, pd.DataFrame]) -> Dict[str, Table]:
        """Конвертация DataFrame в объекты Table для QueryExecutor"""
        executor_tables = {}

        for table_name, df in db_tables.items():
            table = Table(table_name)

            # Добавляем колонки
            for col in df.columns:
                # Определяем тип колонки
                dtype = df[col].dtype
                if dtype == 'int64':
                    col_type = int
                elif dtype == 'float64':
                    col_type = float
                elif dtype == 'bool':
                    col_type = bool
                else:
                    col_type = str

                table.add_column(col, col_type)

            # Добавляем строки
            for _, row in df.iterrows():
                row_dict = row.to_dict()
                # Конвертируем значения в соответствующие типы
                for col, value in row_dict.items():
                    if pd.isna(value):
                        row_dict[col] = None
                    elif isinstance(value, (np.integer,)):
                        row_dict[col] = int(value)
                    elif isinstance(value, (np.floating,)):
                        row_dict[col] = float(value)
                    elif isinstance(value, (np.bool_,)):
                        row_dict[col] = bool(value)
                    else:
                        row_dict[col] = str(value) if value is not None else None

                table.add_row(row_dict)

            executor_tables[table_name] = table

        return executor_tables

    def execute_query(self):
        """Выполнение SQL запроса"""
        self.execute_current_query()

    def _normalize_query(self, query: str) -> str:
        """Приведение всех идентификаторов в SQL запросе к нижнему регистру"""

        # Приводим к нижнему регистру все идентификаторы, кроме строк в кавычках
        result = []
        in_string = False
        string_char = None
        i = 0

        while i < len(query):
            char = query[i]

            # Обработка строк в кавычках
            if char in ("'", '"') and not in_string:
                in_string = True
                string_char = char
                result.append(char)
            elif char == string_char and in_string:
                in_string = False
                string_char = None
                result.append(char)
            elif in_string:
                result.append(char)
            else:
                # Приводим к нижнему регистру только идентификаторы и ключевые слова
                result.append(char.lower())

            i += 1

        return ''.join(result)

    def update_db_tree(self):
        """Обновление дерева базы данных"""
        self.db_tree.clear()

        if not self.db_tables:
            return

        root = QTreeWidgetItem(self.db_tree, ["Database"])
        root.setExpanded(True)

        for table_name, df in self.db_tables.items():
            table_item = QTreeWidgetItem(root, [table_name])

            # Добавляем колонки напрямую
            for col in df.columns:
                col_type = str(df[col].dtype)
                QTreeWidgetItem(table_item, [f"{col} : {col_type}"])

    def on_tree_item_clicked(self, item, column):
        """Обработка клика по элементу дерева"""
        if item.parent() and item.parent().text(0) != "Database":
            # Это колонка, игнорируем
            return
        elif item.parent() and item.parent().text(0) == "Database":
            # Это таблица
            table_name = item.text(0)
            # Создаем новую вкладку с запросом SELECT * FROM table
            self.create_and_execute_select_all(table_name)

    def create_and_execute_select_all(self, table_name):
        """Создать новую вкладку с SELECT * FROM table и выполнить его"""
        # Создаем новую вкладку
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        query_editor = ModernSQLTextEdit()
        query = f"SELECT * FROM {table_name};"
        query_editor.setText(query)
        query_editor.setPlaceholderText("Enter your SQL query here...")

        tab_layout.addWidget(query_editor)

        # Создаем вкладку с именем таблицы
        tab_name = table_name
        self.query_tabs.addTab(tab_widget, tab_name)
        self.query_tabs.setCurrentWidget(tab_widget)
        self.query_tabs.update_add_button_position()

        # Выполняем запрос автоматически
        self.execute_query_from_editor(query_editor, tab_name)

    def execute_query_from_editor(self, query_editor, tab_name):
        """Выполнить запрос из указанного редактора"""
        if not self.db_tables:
            QMessageBox.warning(self, "Warning", "No database loaded")
            return

        if not self.query_executor:
            QMessageBox.warning(self, "Warning", "Query executor not initialized")
            return

        query = query_editor.toPlainText().strip()

        try:
            normalized_query = self._normalize_query(query)
            ast = parse(normalized_query)
            result_rows = self.query_executor.execute(ast)

            if result_rows:
                result_df = pd.DataFrame(result_rows)
                self.results_table.setDataFrame(result_df, stretch=True)
                self.rows_info_label.setText(f"Rows: {len(result_df)} | Query: {tab_name}")
            else:
                self.results_table.setRowCount(0)
                self.results_table.setColumnCount(0)
                self.rows_info_label.setText(f"Rows: 0 | Query: {tab_name}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Query execution failed: {str(e)}")

    def show_table_contents(self, table_name):
        """Показать содержимое таблицы (без дубликатов вкладок)"""
        if table_name not in self.db_tables:
            return

        self.table_tabs.setVisible(True)

        # Если вкладка уже существует — просто активируем
        if table_name in self.open_table_tabs:
            index = self.open_table_tabs[table_name]
            self.table_tabs.setCurrentIndex(index)
            return

        # Создаём новую вкладку
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        table = ModernTableWidget()
        df = self.db_tables[table_name]

        table.setDataFrame(df, stretch=True)  # Явно указываем stretch=True

        tab_layout.addWidget(table)

        index = self.table_tabs.addTab(tab_widget, table_name)
        self.open_table_tabs[table_name] = index
        self.table_tabs.setCurrentIndex(index)

    def create_new_query_tab(self):
        """Создание новой вкладки для запроса"""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        query_editor = ModernSQLTextEdit()
        query_editor.setPlaceholderText("Enter your SQL query here...")

        tab_layout.addWidget(query_editor)

        tab_name = f"Query {self.query_counter}"
        self.query_counter += 1

        self.query_tabs.addTab(tab_widget, tab_name)
        self.query_tabs.setCurrentWidget(tab_widget)
        self.query_tabs.update_add_button_position()

    def close_query_tab(self, index):
        """Закрытие вкладки запроса"""
        if self.query_tabs.count() == 1:
            editor = self.query_tabs.widget(0).findChild(QTextEdit)
            if editor:
                editor.clear()
            return

        self.query_tabs.removeTab(index)
        self.query_tabs.update_add_button_position()

    def close_table_tab(self, index):
        """Закрытие вкладки таблицы"""
        widget = self.table_tabs.widget(index)
        table_name = self.table_tabs.tabText(index)

        self.table_tabs.removeTab(index)
        widget.deleteLater()

        # Удаляем из словаря
        if table_name in self.open_table_tabs:
            del self.open_table_tabs[table_name]

        # Обновляем индексы оставшихся вкладок
        for name, i in list(self.open_table_tabs.items()):
            if i > index:
                self.open_table_tabs[name] = i - 1

        if self.table_tabs.count() == 0:
            self.table_tabs.setVisible(False)

    def load_script(self):
        """Загрузка SQL скрипта из файла и автоматическое выполнение"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load SQL Script", "", "SQL Files (*.sql);;Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                current_tab = self.query_tabs.currentWidget()
                if current_tab:
                    query_editor = current_tab.findChild(QTextEdit)
                    if query_editor:
                        query_editor.setText(content)
                        # Автоматически выполняем загруженный скрипт
                        self.execute_current_query()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load script: {str(e)}")

    def execute_current_query(self):
        """Выполнить запрос из текущей вкладки с диагностикой"""
        current_tab = self.query_tabs.currentWidget()
        if not current_tab:
            return

        query_editor = current_tab.findChild(QTextEdit)
        if not query_editor:
            return

        query = query_editor.toPlainText().strip()

        if not query:
            QMessageBox.warning(self, "Warning", "Query is empty")
            return

        if not self.db_tables:
            QMessageBox.warning(self, "Warning", "No database loaded")
            return

        if not self.query_executor:
            QMessageBox.warning(self, "Warning", "Query executor not initialized")
            return

        try:
            import time
            start_time = time.time()

            normalized_query = self._normalize_query(query)
            ast = parse(normalized_query)
            result_rows = self.query_executor.execute(ast)

            elapsed = time.time() - start_time

            if result_rows:
                result_df = pd.DataFrame(result_rows)
                self.results_table.setDataFrame(result_df, stretch=True)
                tab_name = self.query_tabs.tabText(self.query_tabs.currentIndex())
                self.rows_info_label.setText(f"Rows: {len(result_df)} | Time: {elapsed:.2f}s | Query: {tab_name}")

                # Выводим типы колонок для диагностики
                print(f"\n=== Результат запроса ===")
                print(f"Строк: {len(result_df)}")
                print(f"Колонки и типы:")
                for col in result_df.columns:
                    print(f"  {col}: {result_df[col].dtype}")
            else:
                self.results_table.setRowCount(0)
                self.results_table.setColumnCount(0)
                self.rows_info_label.setText(f"Rows: 0 | Time: {elapsed:.2f}s")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Query execution failed: {str(e)}")
            import traceback
            traceback.print_exc()

    def save_query_to_file(self):
        """Сохранение запроса в файл"""
        current_tab = self.query_tabs.currentWidget()
        if not current_tab:
            return

        query_editor = current_tab.findChild(QTextEdit)
        if not query_editor:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save SQL Script", "test queries/query.sql", "SQL Files (*.sql);;Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(query_editor.toPlainText())

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save script: {str(e)}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = DatabaseViewer()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
