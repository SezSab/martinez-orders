#!/usr/bin/env python3
"""
Martinez Orders - Professional WooCommerce Order Management
"""

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any, List

import requests

# App version - bump this for each release
APP_VERSION = "1.0.0"
GITHUB_REPO = "SezSab/martinez-orders"

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QGridLayout, QComboBox, QTabWidget, QTabBar,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QDialog, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QModelIndex, QTimer, QRectF, QThread
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QBrush, QPen, QIcon, QPixmap


class UpdateChecker(QThread):
    """Background thread to check for updates"""
    update_available = pyqtSignal(str, str)  # version, download_url
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                release = response.json()
                latest_version = release['tag_name'].lstrip('v')

                # Compare versions
                if self._is_newer(latest_version, APP_VERSION):
                    # Find the exe download URL
                    download_url = None
                    for asset in release.get('assets', []):
                        if asset['name'].endswith('.exe'):
                            download_url = asset['browser_download_url']
                            break

                    if download_url:
                        self.update_available.emit(latest_version, download_url)
                    else:
                        self.no_update.emit()
                else:
                    self.no_update.emit()
            elif response.status_code == 404:
                self.no_update.emit()  # No releases yet
            else:
                self.error.emit(f"GitHub API error: {response.status_code}")
        except Exception as e:
            self.error.emit(str(e))

    def _is_newer(self, latest: str, current: str) -> bool:
        """Compare version strings (e.g., '1.0.1' > '1.0.0')"""
        try:
            latest_parts = [int(x) for x in latest.split('.')]
            current_parts = [int(x) for x in current.split('.')]
            return latest_parts > current_parts
        except:
            return False


class UpdateDownloader(QThread):
    """Background thread to download update"""
    progress = pyqtSignal(int)  # percentage
    finished = pyqtSignal(str)  # path to downloaded file
    error = pyqtSignal(str)

    def __init__(self, download_url: str):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            # Download to temp file
            response = requests.get(self.download_url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            # Create temp file
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, "MartinezOrders_update.exe")

            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int(downloaded * 100 / total_size)
                            self.progress.emit(progress)

            self.finished.emit(temp_file)
        except Exception as e:
            self.error.emit(str(e))


class UpdateDialog(QDialog):
    """Dialog for showing update progress and installing"""

    def __init__(self, new_version: str, download_url: str, parent=None):
        super().__init__(parent)
        self.new_version = new_version
        self.download_url = download_url
        self.downloader = None
        self.downloaded_file = None

        self.setWindowTitle("Update Available")
        self.setFixedSize(400, 200)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Info label
        self.info_label = QLabel(f"New version {new_version} is available!\nCurrent version: {APP_VERSION}")
        self.info_label.setFont(QFont("Segoe UI", 12))
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #7c3aed;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()

        self.download_btn = QPushButton("Download && Install")
        self.download_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.download_btn.clicked.connect(self._start_download)
        btn_layout.addWidget(self.download_btn)

        self.cancel_btn = QPushButton("Later")
        self.cancel_btn.setFont(QFont("Segoe UI", 11))
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #333;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _start_download(self):
        self.download_btn.setEnabled(False)
        self.download_btn.setText("Downloading...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.downloader = UpdateDownloader(self.download_url)
        self.downloader.progress.connect(self._on_progress)
        self.downloader.finished.connect(self._on_download_finished)
        self.downloader.error.connect(self._on_download_error)
        self.downloader.start()

    def _on_progress(self, value: int):
        self.progress_bar.setValue(value)

    def _on_download_finished(self, file_path: str):
        self.downloaded_file = file_path
        self.info_label.setText("Download complete!\nThe app will restart to install the update.")
        self.download_btn.setText("Install Now")
        self.download_btn.setEnabled(True)
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self._install_update)

    def _on_download_error(self, error: str):
        self.info_label.setText(f"Download failed:\n{error}")
        self.download_btn.setText("Retry")
        self.download_btn.setEnabled(True)

    def _install_update(self):
        if not self.downloaded_file or not os.path.exists(self.downloaded_file):
            QMessageBox.warning(self, "Error", "Downloaded file not found")
            return

        # Get current executable path
        if getattr(sys, 'frozen', False):
            # Running as compiled exe
            current_exe = sys.executable
            current_dir = os.path.dirname(current_exe)

            # Create a batch script to:
            # 1. Wait for current process to exit
            # 2. Replace the exe
            # 3. Start the new exe
            # 4. Delete the batch script

            batch_script = os.path.join(tempfile.gettempdir(), "update_martinez.bat")
            new_exe_name = os.path.basename(current_exe)

            batch_content = f'''@echo off
echo Updating Martinez Orders...
timeout /t 2 /nobreak > nul
copy /Y "{self.downloaded_file}" "{current_exe}"
start "" "{current_exe}"
del "{self.downloaded_file}"
del "%~f0"
'''
            with open(batch_script, 'w') as f:
                f.write(batch_content)

            # Run the batch script and exit
            subprocess.Popen(['cmd', '/c', batch_script],
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            QApplication.quit()
        else:
            # Running as Python script - just show message
            QMessageBox.information(
                self,
                "Update Downloaded",
                f"Update downloaded to:\n{self.downloaded_file}\n\nPlease replace the executable manually."
            )
            self.accept()

# ElevenLabs Call Status definitions (from WooCommerce plugin)
CALL_STATUSES = {
    'Без_обаждане': {'color': '#6c757d', 'icon': '—', 'text': 'Без обаждане'},
    'Потвърдена_по_телефон': {'color': '#28a745', 'icon': '✓', 'text': 'Потвърдена'},
    'Потвърдена_с_промени': {'color': '#17a2b8', 'icon': '✓', 'text': 'С промени'},
    'Отказана_по_телефон': {'color': '#dc3545', 'icon': '✗', 'text': 'Отказана'},
    'Изчакване_потвърждение': {'color': '#ffc107', 'icon': '⏳', 'text': 'Изчакване'},
    'Неотговорен_опит_1': {'color': '#ff6b6b', 'icon': '📞', 'text': 'Опит 1/3'},
    'Неотговорен_опит_2': {'color': '#ff6b6b', 'icon': '📞', 'text': 'Опит 2/3'},
    'Неотговорен_опит_3': {'color': '#ff6b6b', 'icon': '📞', 'text': 'Опит 3/3'},
    'Неотговорен_максимум': {'color': '#868e96', 'icon': '❌', 'text': 'Макс. опити'},
}

# WooCommerce Order Status colors
ORDER_STATUS_COLORS = {
    'pending': '#ffc107',      # Yellow - Pending payment
    'processing': '#007bff',   # Blue - Processing
    'on-hold': '#fd7e14',      # Orange - On hold
    'completed': '#28a745',    # Green - Completed
    'cancelled': '#dc3545',    # Red - Cancelled
    'refunded': '#6c757d',     # Gray - Refunded
    'failed': '#dc3545',       # Red - Failed
    'trash': '#868e96',        # Gray - Trash
    'checkout-draft': '#6c757d', # Gray - Draft
}

def lighten_color(hex_color, factor=0.85):
    """Create a lighter version of a hex color for hover backgrounds"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f'#{r:02x}{g:02x}{b:02x}'


class ColoredComboDelegate(QStyledItemDelegate):
    """Custom delegate for painting QComboBox items with individual colors"""

    def __init__(self, color_map: dict, parent=None):
        super().__init__(parent)
        self.color_map = color_map  # slug -> color hex string

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # Get the slug (stored as UserRole data)
        slug = index.data(Qt.ItemDataRole.UserRole)
        color_hex = self.color_map.get(slug, '#333333')

        painter.save()

        # Check states using proper PyQt6 enum
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Draw hover/selection background
        if is_hovered and not is_selected:
            hover_color = QColor(lighten_color(color_hex, 0.7))
            painter.fillRect(option.rect, QBrush(hover_color))
        elif is_selected:
            painter.fillRect(option.rect, QBrush(QColor(color_hex)))

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        text_rect = option.rect.adjusted(10, 0, -10, 0)

        # Set text color based on selection state
        if is_selected:
            painter.setPen(QColor('white'))
        else:
            painter.setPen(QColor(color_hex))

        font = painter.font()
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        size = super().sizeHint(option, index)
        size.setHeight(32)  # Ensure consistent row height
        return size


class CallStatusComboDelegate(QStyledItemDelegate):
    """Custom delegate for painting Call Status QComboBox items with individual colors"""

    def __init__(self, statuses: dict, parent=None):
        super().__init__(parent)
        self.statuses = statuses  # key -> {'color': hex, 'icon': str, 'text': str}

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # Get the status key (stored as UserRole data)
        status_key = index.data(Qt.ItemDataRole.UserRole)
        status_info = self.statuses.get(status_key, {})
        color_hex = status_info.get('color', '#333333')

        painter.save()

        # Check states using proper PyQt6 enum
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Draw hover/selection background
        if is_hovered and not is_selected:
            hover_color = QColor(lighten_color(color_hex, 0.7))
            painter.fillRect(option.rect, QBrush(hover_color))
        elif is_selected:
            painter.fillRect(option.rect, QBrush(QColor(color_hex)))

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        text_rect = option.rect.adjusted(10, 0, -10, 0)

        # Set text color based on selection state
        if is_selected:
            painter.setPen(QColor('white'))
        else:
            painter.setPen(QColor(color_hex))

        font = painter.font()
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        size = super().sizeHint(option, index)
        size.setHeight(32)  # Ensure consistent row height
        return size


try:
    from woocommerce import API as WooCommerceAPI
except ImportError:
    print("Missing woocommerce. Run: pip install woocommerce")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Config:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.data = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {}
        with open(self.config_path, 'r') as f:
            return json.load(f)

    @property
    def asterisk(self) -> Dict[str, Any]:
        return self.data.get('asterisk', {})

    @property
    def shops(self) -> List[Dict[str, Any]]:
        """Get list of shop configurations"""
        return self.data.get('shops', [])

    @property
    def woocommerce(self) -> Dict[str, Any]:
        """Legacy support - returns first shop config"""
        shops = self.shops
        if shops:
            return shops[0]
        return self.data.get('woocommerce', {})

    @property
    def settings(self) -> Dict[str, Any]:
        return self.data.get('settings', {})


class WooCommerceClient:
    def __init__(self, shop_config: Dict[str, Any]):
        """Initialize with a shop config dict containing url, consumer_key, consumer_secret, name, color"""
        self.shop_config = shop_config
        self.shop_name = shop_config.get('name', 'Shop')
        self.shop_color = shop_config.get('color', '#7c3aed')
        self.shop_url = shop_config.get('url', '')
        self.odoo_url = shop_config.get('odoo_url', '')
        self.wcapi = WooCommerceAPI(
            url=shop_config['url'],
            consumer_key=shop_config['consumer_key'],
            consumer_secret=shop_config['consumer_secret'],
            version="wc/v3",
            timeout=15
        )

    def normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if len(digits) > 10:
            if digits.startswith('00'):
                digits = digits[2:]
            elif digits.startswith('0'):
                digits = digits[1:]
            for prefix in ['1', '44', '49', '33', '39', '34', '31', '98', '359']:
                if digits.startswith(prefix) and len(digits) > 10:
                    digits = digits[len(prefix):]
                    break
        return digits[-10:] if len(digits) >= 10 else digits

    def search_orders_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """Search orders by phone - uses WooCommerce search API which searches ALL orders."""
        normalized_phone = self.normalize_phone(phone)
        logger.info(f"[{self.shop_name}] Searching for phone: {phone} (normalized: {normalized_phone})")

        try:
            matching_orders = []
            seen_ids = set()

            # Build search variants - try different formats
            search_variants = [phone]
            if normalized_phone != phone:
                search_variants.append(normalized_phone)
            # Try with country code prefix for Bulgarian numbers
            if len(normalized_phone) == 9:
                search_variants.append(f"+359{normalized_phone}")
                search_variants.append(f"359{normalized_phone}")
                search_variants.append(f"0{normalized_phone}")

            # WooCommerce search searches ALL orders in database
            for search_term in search_variants:
                response = self.wcapi.get("orders", params={
                    "search": search_term,
                    "per_page": 100
                })

                if response.status_code == 200:
                    orders = response.json()
                    for order in orders:
                        if order['id'] in seen_ids:
                            continue
                        billing = order.get('billing', {})
                        billing_phone = billing.get('phone', '')
                        billing_normalized = self.normalize_phone(billing_phone)

                        if self._phone_matches(normalized_phone, billing_normalized):
                            seen_ids.add(order['id'])
                            matching_orders.append(order)

            logger.info(f"[{self.shop_name}] Found {len(matching_orders)} matching orders")
            return matching_orders

        except Exception as e:
            logger.error(f"[{self.shop_name}] Error searching orders: {e}")
            return []

    def _phone_matches(self, normalized_search: str, normalized_billing: str) -> bool:
        """Check if two normalized phone numbers match"""
        if not normalized_search or not normalized_billing:
            return False

        # Direct containment check
        if normalized_search in normalized_billing or normalized_billing in normalized_search:
            return True

        # Last 9 digits comparison (handles country code differences)
        if len(normalized_search) >= 9 and len(normalized_billing) >= 9:
            if normalized_search[-9:] == normalized_billing[-9:]:
                return True

        return False

    def get_order_url(self, order_id: int) -> str:
        base_url = self.shop_url.rstrip('/')
        return f"{base_url}/wp-admin/admin.php?page=wc-orders&action=edit&id={order_id}"

    def update_call_status(self, order_id: int, status: str) -> tuple[bool, str]:
        """Update the ElevenLabs_Call_Status meta for an order.
        Returns (success, message)"""
        try:
            # Get current order to verify it exists
            response = self.wcapi.get(f"orders/{order_id}")
            if response.status_code != 200:
                return False, f"Order not found: {response.status_code}"

            # Update the meta data
            data = {
                "meta_data": [
                    {
                        "key": "ElevenLabs_Call_Status",
                        "value": status
                    }
                ]
            }

            response = self.wcapi.put(f"orders/{order_id}", data)
            if response.status_code == 200:
                # Verify the update
                updated_order = response.json()
                for meta in updated_order.get('meta_data', []):
                    if meta.get('key') == 'ElevenLabs_Call_Status' and meta.get('value') == status:
                        return True, "Status updated successfully"
                return True, "Status sent (unverified)"
            else:
                return False, f"API error: {response.status_code}"

        except Exception as e:
            logger.error(f"Error updating call status: {e}")
            return False, str(e)

    def get_order_statuses(self) -> List[Dict[str, str]]:
        """Get available order statuses from WooCommerce API.
        Returns list of dicts with 'slug' and 'name' keys."""
        try:
            response = self.wcapi.get("orders/statuses")
            if response.status_code == 200:
                statuses = response.json()
                # WooCommerce API can return either a dict or a list
                if isinstance(statuses, dict):
                    return [{'slug': slug, 'name': name} for slug, name in statuses.items()]
                elif isinstance(statuses, list):
                    # List of status objects
                    return [{'slug': s.get('slug', s.get('status', '')), 'name': s.get('name', s.get('label', ''))} for s in statuses]
                else:
                    logger.error(f"Unexpected response type for order statuses: {type(statuses)}")
                    return []
            else:
                logger.error(f"Failed to get order statuses: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error getting order statuses: {e}")
            return []

    def update_order_status(self, order_id: int, status: str) -> tuple[bool, str]:
        """Update the order status.
        Returns (success, message)"""
        try:
            data = {"status": status}
            response = self.wcapi.put(f"orders/{order_id}", data)
            if response.status_code == 200:
                updated_order = response.json()
                if updated_order.get('status') == status:
                    return True, "Order status updated successfully"
                return True, "Status sent (unverified)"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            logger.error(f"Error updating order status: {e}")
            return False, str(e)

    def get_order_by_number(self, order_number: str) -> List[Dict[str, Any]]:
        """Get order by order number (not ID).
        Supports partial matching - e.g. '7993' matches 'MP7993AX'.
        Returns list with matching orders."""
        logger.info(f"Searching for order number: {order_number}")
        try:
            # Clean up the order number - remove # if present
            order_number = order_number.strip().lstrip('#').upper()

            # Method 1: Try search parameter (works for standard WooCommerce)
            response = self.wcapi.get("orders", params={
                "search": order_number,
                "per_page": 50
            })

            if response.status_code == 200:
                orders = response.json()
                # Filter to partial match on order number (case-insensitive)
                matching = [o for o in orders if order_number in str(o.get('number', '')).upper()]
                if matching:
                    logger.info(f"Found {len(matching)} order(s) matching '{order_number}' via search")
                    return matching

            # Method 2: Try fetching recent orders and filtering
            # This helps when using custom order number plugins
            response = self.wcapi.get("orders", params={
                "per_page": 100,
                "orderby": "date",
                "order": "desc"
            })

            if response.status_code == 200:
                orders = response.json()
                # Filter to partial match on order number (case-insensitive)
                matching = [o for o in orders if order_number in str(o.get('number', '')).upper()]
                if matching:
                    logger.info(f"Found {len(matching)} order(s) matching '{order_number}' in recent orders")
                    return matching

            logger.info(f"No order found matching '{order_number}'")
            return []

        except Exception as e:
            logger.error(f"Error searching order by number: {e}")
            return []


class MultiShopClient:
    """Manages multiple WooCommerce shop clients and aggregates searches"""

    def __init__(self, config: Config):
        self.config = config
        self.clients: List[WooCommerceClient] = []
        self._order_to_client: Dict[int, WooCommerceClient] = {}

        # Create a client for each configured shop
        for shop_config in config.shops:
            try:
                client = WooCommerceClient(shop_config)
                self.clients.append(client)
                logger.info(f"Initialized shop: {client.shop_name}")
            except Exception as e:
                logger.error(f"Failed to initialize shop {shop_config.get('name', 'Unknown')}: {e}")

        # Fallback to legacy config if no shops configured
        if not self.clients and config.woocommerce:
            try:
                client = WooCommerceClient(config.woocommerce)
                self.clients.append(client)
                logger.info(f"Initialized legacy shop config")
            except Exception as e:
                logger.error(f"Failed to initialize legacy shop: {e}")

    def search_orders_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """Search all shops for orders matching phone number"""
        all_orders = []
        for client in self.clients:
            try:
                orders = client.search_orders_by_phone(phone)
                # Tag each order with shop info
                for order in orders:
                    order['_shop_name'] = client.shop_name
                    order['_shop_color'] = client.shop_color
                    order['_shop_odoo_url'] = client.odoo_url
                    self._order_to_client[order['id']] = client
                all_orders.extend(orders)
            except Exception as e:
                logger.error(f"Error searching {client.shop_name}: {e}")
        # Sort by date (newest first)
        all_orders.sort(key=lambda o: o.get('date_created', ''), reverse=True)
        return all_orders

    def get_order_by_number(self, order_number: str) -> List[Dict[str, Any]]:
        """Search all shops for an order by number"""
        all_orders = []
        for client in self.clients:
            try:
                orders = client.get_order_by_number(order_number)
                for order in orders:
                    order['_shop_name'] = client.shop_name
                    order['_shop_color'] = client.shop_color
                    order['_shop_odoo_url'] = client.odoo_url
                    self._order_to_client[order['id']] = client
                all_orders.extend(orders)
            except Exception as e:
                logger.error(f"Error searching {client.shop_name}: {e}")
        # Sort by date, newest first
        all_orders.sort(key=lambda o: o.get('date_created', ''), reverse=True)
        return all_orders

    def get_client_for_order(self, order_id: int) -> Optional[WooCommerceClient]:
        """Get the WooCommerceClient that owns a specific order"""
        return self._order_to_client.get(order_id)

    def get_order_url(self, order_id: int) -> str:
        """Get the admin URL for an order"""
        client = self.get_client_for_order(order_id)
        if client:
            return client.get_order_url(order_id)
        # Fallback to first client
        if self.clients:
            return self.clients[0].get_order_url(order_id)
        return ""

    def update_call_status(self, order_id: int, status: str) -> tuple[bool, str]:
        """Update call status for an order"""
        client = self.get_client_for_order(order_id)
        if client:
            return client.update_call_status(order_id, status)
        return False, "Unknown order source"

    def update_order_status(self, order_id: int, status: str) -> tuple[bool, str]:
        """Update order status"""
        client = self.get_client_for_order(order_id)
        if client:
            return client.update_order_status(order_id, status)
        return False, "Unknown order source"

    def get_order_statuses(self) -> List[Dict[str, str]]:
        """Get order statuses from first available shop"""
        if self.clients:
            return self.clients[0].get_order_statuses()
        return []


class SignalEmitter(QObject):
    incoming_call = pyqtSignal(str, dict)
    connection_status = pyqtSignal(bool, str)
    search_result = pyqtSignal(list, str)
    status_update_result = pyqtSignal(int, bool, str)  # row, success, message


class WebhookServer:
    """HTTP server for receiving incoming call notifications from Android/Tasker"""

    def __init__(self, signals: SignalEmitter, port: int = 5039):
        self.signals = signals
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def _create_handler(self):
        signals = self.signals

        class WebhookHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                logging.debug(f"Webhook: {format % args}")

            def do_POST(self):
                if self.path == '/incoming-call':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                        body = self.rfile.read(content_length).decode('utf-8')
                        data = json.loads(body)
                        phone = data.get('phone', '')

                        if phone:
                            logging.info(f"Webhook: Incoming call from {phone}")
                            signals.incoming_call.emit(phone, {"source": "android"})
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({"status": "ok"}).encode())
                        else:
                            self.send_response(400)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({"error": "phone required"}).encode())
                    except Exception as e:
                        logging.error(f"Webhook error: {e}")
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": str(e)}).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_GET(self):
                if self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "running"}).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

        return WebhookHandler

    def start(self):
        if self.running:
            return

        try:
            handler = self._create_handler()
            self.server = HTTPServer(('0.0.0.0', self.port), handler)
            self.running = True
            self._thread = threading.Thread(target=self._serve, daemon=True)
            self._thread.start()
            logging.info(f"Webhook server started on port {self.port}")
        except Exception as e:
            logging.error(f"Failed to start webhook server: {e}")

    def _serve(self):
        while self.running and self.server:
            self.server.handle_request()

    def stop(self):
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server = None
        logging.info("Webhook server stopped")


class AsteriskAMI:
    def __init__(self, config: Config, signals: SignalEmitter):
        self.host = config.asterisk.get('host', '')
        self.port = config.asterisk.get('port', 5038)
        self.username = config.asterisk.get('username', '')
        self.secret = config.asterisk.get('secret', '')
        self.watch_number = config.asterisk.get('watch_number', '')  # Only catch calls to this number
        self.watch_channel = config.asterisk.get('watch_channel', '').upper()  # Watch channel like SIP/1034
        self.signals = signals
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self._processed_calls = set()
        # Track calls: LinkedID -> original CallerID from SIP trunk
        self._call_callers = {}  # LinkedID -> CallerID
        self._reconnect_delay = 5  # seconds between reconnect attempts
        self._auto_reconnect = True

    def connect(self) -> bool:
        if not self.host or not self.username:
            self.signals.connection_status.emit(False, "Not configured")
            return False

        try:
            self.signals.connection_status.emit(False, "Connecting...")

            # Close existing socket if any
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))

            self.socket.recv(1024)
            login_cmd = f"Action: Login\r\nUsername: {self.username}\r\nSecret: {self.secret}\r\n\r\n"
            self.socket.send(login_cmd.encode('utf-8'))

            response = self.socket.recv(1024).decode('utf-8')
            if 'Success' in response:
                self.connected = True
                self.socket.settimeout(1)
                self.signals.connection_status.emit(True, "Connected")
                logger.info("AMI connected successfully")
                return True
            else:
                self.signals.connection_status.emit(False, "Auth failed")
                return False

        except Exception as e:
            logger.error(f"AMI connection error: {e}")
            self.signals.connection_status.emit(False, "Connection failed")
            return False

    def disconnect(self):
        self._auto_reconnect = False
        self.running = False
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass

    def start_listening(self):
        self.running = True
        self._auto_reconnect = True
        threading.Thread(target=self._event_loop, daemon=True).start()

    def _reconnect(self):
        """Attempt to reconnect to AMI with exponential backoff."""
        retry_count = 0
        max_delay = 60  # Maximum delay between retries

        while self.running and self._auto_reconnect and not self.connected:
            delay = min(self._reconnect_delay * (2 ** retry_count), max_delay)
            self.signals.connection_status.emit(False, f"Reconnecting in {delay}s...")
            logger.info(f"AMI reconnecting in {delay} seconds...")

            time.sleep(delay)

            if not self.running or not self._auto_reconnect:
                break

            if self.connect():
                logger.info("AMI reconnected successfully")
                return True

            retry_count += 1

        return False

    def _event_loop(self):
        buffer = ""
        while self.running:
            # If not connected, try to reconnect
            if not self.connected:
                if self._auto_reconnect:
                    if not self._reconnect():
                        continue
                else:
                    break

            try:
                data = self.socket.recv(4096).decode('utf-8')
                if not data:
                    self.connected = False
                    self.signals.connection_status.emit(False, "Disconnected")
                    logger.warning("AMI disconnected - no data received")
                    continue  # Will trigger reconnect

                buffer += data
                while '\r\n\r\n' in buffer:
                    event_str, buffer = buffer.split('\r\n\r\n', 1)
                    self._process_event(event_str)

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"AMI event loop error: {e}")
                self.connected = False
                self.signals.connection_status.emit(False, "Connection lost")
                buffer = ""  # Clear buffer on reconnect
                continue  # Will trigger reconnect

    def _is_external_call(self, channel: str) -> bool:
        """Check if the channel is from an external SIP trunk (not internal extension)."""
        if not channel:
            return False
        channel_lower = channel.lower()
        if 'prov' in channel_lower or 'trunk' in channel_lower:
            return True
        if channel_lower.startswith('sip/'):
            name_part = channel_lower[4:].split('-')[0]
            if name_part and name_part[0].isalpha():
                return True
        return False

    def _normalize_number(self, number: str) -> str:
        """Remove leading zeros and country code prefix for comparison."""
        digits = re.sub(r'\D', '', number)
        # Remove leading zeros
        digits = digits.lstrip('0')
        return digits

    def _numbers_match(self, num1: str, num2: str) -> bool:
        """Check if two phone numbers match (handling different formats)."""
        n1 = self._normalize_number(num1)
        n2 = self._normalize_number(num2)
        if not n1 or not n2:
            return False
        # Check if one contains the other or last 9 digits match
        return n1 in n2 or n2 in n1 or (len(n1) >= 9 and len(n2) >= 9 and n1[-9:] == n2[-9:])

    def _process_event(self, event_str: str):
        event = {}
        for line in event_str.strip().split('\r\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                event[key.strip()] = value.strip()

        event_type = event.get('Event', '')
        channel = event.get('Channel', '')
        caller_id = event.get('CallerIDNum', '')
        unique_id = event.get('Uniqueid', '')
        linked_id = event.get('Linkedid', unique_id)  # LinkedID links all channels of same call
        connected_num = event.get('ConnectedLineNum', '')
        exten = event.get('Exten', '')
        dest_channel = event.get('DestChannel', '')
        dest_caller_id = event.get('DestCallerIDNum', '')

        state = event.get('ChannelStateDesc', '')

        # Debug logging for relevant events
        if event_type in ('Newstate', 'DialBegin', 'DialState', 'Newchannel', 'Dial', 'Bridge'):
            logger.info(f"AMI: {event_type} | CallerID: {caller_id or 'N/A'} | Channel: {channel[:30] if channel else 'N/A'} | State: {state} | ConnectedLine: {connected_num} | DestChannel: {dest_channel[:30] if dest_channel else 'N/A'}")

        # Strategy: Catch incoming calls to watch_channel using multiple detection methods
        # This ensures we don't miss calls that arrive via different paths

        actual_caller = None
        matched = False

        # Method 1: DialBegin - when a call starts dialing to our extension
        # This is often the earliest and most reliable event
        if event_type == 'DialBegin' and self.watch_channel and dest_channel:
            dest_base = dest_channel.upper().split('-')[0]
            if dest_base == self.watch_channel:
                # CallerIDNum on the source channel is the external caller
                actual_caller = caller_id if caller_id and caller_id not in ('<unknown>', '', 's', 'anonymous') else None
                if actual_caller:
                    matched = True
                    logger.info(f">>> MATCH via DialBegin! Caller {actual_caller} -> {self.watch_channel}")

        # Method 2: DialState with Ringing - backup detection
        if not matched and event_type == 'DialState' and self.watch_channel and dest_channel:
            dest_base = dest_channel.upper().split('-')[0]
            if dest_base == self.watch_channel and state == 'Ringing':
                actual_caller = caller_id if caller_id and caller_id not in ('<unknown>', '', 's', 'anonymous') else None
                if actual_caller:
                    matched = True
                    logger.info(f">>> MATCH via DialState! Caller {actual_caller} -> {self.watch_channel}")

        # Method 3: Newstate Ringing on watch_channel - original method as fallback
        if not matched and event_type == 'Newstate' and state == 'Ringing' and self.watch_channel and channel:
            channel_base = channel.upper().split('-')[0]
            if channel_base == self.watch_channel:
                # ConnectedLineNum is the actual caller for incoming calls
                actual_caller = connected_num if connected_num and connected_num not in ('<unknown>', '', 's', 'anonymous') else None
                # Also try CallerIDNum if ConnectedLineNum is not available
                if not actual_caller:
                    actual_caller = caller_id if caller_id and caller_id not in ('<unknown>', '', 's', 'anonymous') else None
                if actual_caller:
                    matched = True
                    logger.info(f">>> MATCH via Newstate! {self.watch_channel} ringing, caller: {actual_caller}")

        # Emit signal if we found a caller
        if matched and actual_caller:
            call_key = f"call_{linked_id}_{actual_caller}"
            if call_key not in self._processed_calls:
                self._processed_calls.add(call_key)
                # Clean up old entries
                if len(self._processed_calls) > 200:
                    self._processed_calls = set(list(self._processed_calls)[-100:])
                logger.info(f">>> EMITTING incoming call from: {actual_caller}")
                self.signals.incoming_call.emit(actual_caller, event)


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with spinning loader"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start(30)  # ~33 FPS

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def _rotate(self):
        self.angle = (self.angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent background
        painter.fillRect(self.rect(), QColor(255, 255, 255, 200))

        # Draw spinner in center
        center_x = self.width() // 2
        center_y = self.height() // 2
        radius = 30
        line_width = 4
        arc_length = 90

        pen = QPen(QColor("#7c3aed"))
        pen.setWidth(line_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)
        painter.drawArc(rect, self.angle * 16, arc_length * 16)

        # Draw "Loading..." text
        painter.setPen(QColor("#666"))
        painter.setFont(QFont("Segoe UI", 14))
        text_rect = QRectF(0, center_y + radius + 20, self.width(), 30)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "Loading...")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())


class CustomerTab(QWidget):
    """A tab widget containing customer information and orders"""

    def __init__(self, woo_client, signals, order_statuses=None, parent=None):
        super().__init__(parent)
        self.woo_client = woo_client
        self.signals = signals
        self.current_orders = []
        self.phone_number = ""
        self.order_statuses = order_statuses or []
        self.pending_status_updates = {}  # row -> {'col': col, 'prev_idx': idx, 'prev_status': status}
        self._setup_ui()

    def _create_card(self, title: str) -> tuple:
        """Create a card widget with title."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 15, 20, 20)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333; border: none;")
        layout.addWidget(title_label)

        return card, layout

    def _create_info_label(self, text: str, is_value: bool = False, size: int = 13) -> QLabel:
        """Create styled label."""
        label = QLabel(text)
        label.setFont(QFont("Segoe UI", size, QFont.Weight.Bold if is_value else QFont.Weight.Normal))
        label.setStyleSheet(f"color: {'#333' if is_value else '#666'}; border: none;")
        label.setWordWrap(True)
        return label

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 15, 20, 20)

        # ========== SEARCH BARS ==========
        search_container = QHBoxLayout()
        search_container.setSpacing(15)

        # Phone search
        phone_frame = QFrame()
        phone_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
        """)
        phone_layout = QHBoxLayout(phone_frame)
        phone_layout.setContentsMargins(15, 10, 15, 10)

        phone_icon = QLabel("📞")
        phone_icon.setFont(QFont("Segoe UI", 16))
        phone_icon.setStyleSheet("border: none;")
        phone_layout.addWidget(phone_icon)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Search by phone number...")
        self.phone_input.setFont(QFont("Segoe UI", 14))
        self.phone_input.setStyleSheet("""
            QLineEdit {
                border: none;
                padding: 8px;
                background: transparent;
            }
        """)
        self.phone_input.returnPressed.connect(self._search)
        self.phone_input.textChanged.connect(self._on_search_input_changed)
        phone_layout.addWidget(self.phone_input)

        self.search_btn = QPushButton("Search")
        self.search_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.search_btn.clicked.connect(self._search)
        phone_layout.addWidget(self.search_btn)

        search_container.addWidget(phone_frame, 1)

        # Order number search
        order_frame = QFrame()
        order_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
        """)
        order_layout = QHBoxLayout(order_frame)
        order_layout.setContentsMargins(15, 10, 15, 10)

        order_icon = QLabel("#")
        order_icon.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        order_icon.setStyleSheet("border: none; color: #7c3aed;")
        order_layout.addWidget(order_icon)

        self.order_input = QLineEdit()
        self.order_input.setPlaceholderText("Search by order number...")
        self.order_input.setFont(QFont("Segoe UI", 14))
        self.order_input.setStyleSheet("""
            QLineEdit {
                border: none;
                padding: 8px;
                background: transparent;
            }
        """)
        self.order_input.returnPressed.connect(self._search_order)
        self.order_input.textChanged.connect(self._on_search_input_changed)
        order_layout.addWidget(self.order_input)

        self.order_search_btn = QPushButton("Find Order")
        self.order_search_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.order_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.order_search_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.order_search_btn.clicked.connect(self._search_order)
        order_layout.addWidget(self.order_search_btn)

        search_container.addWidget(order_frame, 1)

        main_layout.addLayout(search_container)

        # ========== MAIN CONTENT ==========
        # Wrap content in a widget so overlay can be positioned over it
        self.content_widget = QWidget()
        content_layout = QHBoxLayout(self.content_widget)
        content_layout.setSpacing(15)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # ---------- LEFT COLUMN: Customer Info ----------
        left_column = QVBoxLayout()
        left_column.setSpacing(15)

        # Customer Card
        customer_card, customer_layout = self._create_card("Customer Information")

        # Customer name (large)
        self.customer_name = QLabel("No customer selected")
        self.customer_name.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self.customer_name.setStyleSheet("color: #333; border: none;")
        self.customer_name.setWordWrap(True)
        customer_layout.addWidget(self.customer_name)

        # Info grid
        info_grid = QGridLayout()
        info_grid.setSpacing(8)
        info_grid.setColumnStretch(1, 1)

        self.info_labels = {}
        fields = [
            ("Phone", "phone"),
            ("Email", "email"),
            ("City", "city"),
            ("Address", "address"),
        ]

        for i, (label, key) in enumerate(fields):
            lbl = self._create_info_label(label + ":")
            val = self._create_info_label("-", is_value=True)
            info_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignTop)
            info_grid.addWidget(val, i, 1, Qt.AlignmentFlag.AlignTop)
            self.info_labels[key] = val

        customer_layout.addLayout(info_grid)
        customer_card.setFixedWidth(380)
        left_column.addWidget(customer_card)

        # Stats Card
        stats_card, stats_layout = self._create_card("Customer Statistics")

        stats_grid = QHBoxLayout()
        stats_grid.setSpacing(30)

        # Total Orders
        orders_box = QVBoxLayout()
        orders_title = self._create_info_label("Total Orders")
        self.total_orders = QLabel("-")
        self.total_orders.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.total_orders.setStyleSheet("color: #1a73e8; border: none;")
        orders_box.addWidget(orders_title)
        orders_box.addWidget(self.total_orders)
        stats_grid.addLayout(orders_box)

        # Total Spent
        spent_box = QVBoxLayout()
        spent_title = self._create_info_label("Total Spent")
        self.total_spent = QLabel("-")
        self.total_spent.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.total_spent.setStyleSheet("color: #34a853; border: none;")
        spent_box.addWidget(spent_title)
        spent_box.addWidget(self.total_spent)
        stats_grid.addLayout(spent_box)

        stats_grid.addStretch()
        stats_layout.addLayout(stats_grid)
        stats_card.setFixedWidth(380)
        left_column.addWidget(stats_card)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.open_btn = QPushButton("Open in WooCommerce")
        self.open_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setEnabled(False)
        self.open_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 15px 20px;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.open_btn.clicked.connect(self._open_woocommerce)
        btn_layout.addWidget(self.open_btn)

        left_column.addLayout(btn_layout)
        left_column.addStretch()

        content_layout.addLayout(left_column)

        # ---------- RIGHT COLUMN: Orders Table ----------
        orders_card, orders_layout = self._create_card("Order History")

        self.orders_table = QTableWidget()
        self.orders_table.setColumnCount(8)
        self.orders_table.setHorizontalHeaderLabels(["Order #", "Date", "Status", "Call Status", "Items", "Total", "", ""])
        self.orders_table.setFont(QFont("Segoe UI", 14))
        self.orders_table.setStyleSheet("""
            QTableWidget {
                border: none;
                background-color: white;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item {
                padding: 12px;
                border-bottom: 1px solid #f0f0f0;
            }
            QTableWidget::item:selected {
                background-color: #e8f0fe;
                color: #333;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #666;
                font-weight: 600;
                font-size: 12px;
                border: none;
                border-bottom: 2px solid #e0e0e0;
                padding: 12px 8px;
            }
        """)

        header = self.orders_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # Order #
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # Date
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Status
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Call Status
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Items
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Total
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)  # Open button
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)  # Odoo button

        self.orders_table.setColumnWidth(0, 130)   # Order #
        self.orders_table.setColumnWidth(1, 120)   # Date (dd.mm.yyyy)
        self.orders_table.setColumnWidth(2, 160)   # Status (dropdown)
        self.orders_table.setColumnWidth(3, 250)   # Call Status (dropdown - larger)
        self.orders_table.setColumnWidth(5, 100)   # Total
        self.orders_table.setColumnWidth(6, 80)    # Open button
        self.orders_table.setColumnWidth(7, 80)    # Odoo button

        self.orders_table.verticalHeader().setVisible(False)
        self.orders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders_table.setAlternatingRowColors(True)
        self.orders_table.setShowGrid(False)
        self.orders_table.setWordWrap(True)
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        orders_layout.addWidget(self.orders_table)
        content_layout.addWidget(orders_card, 1)

        # Connect row selection change to update customer info
        self.orders_table.currentCellChanged.connect(self._on_order_selected)

        # Add content widget to main layout
        main_layout.addWidget(self.content_widget, 1)

        # Create loading overlay (child of content_widget so it covers only the content area)
        self.loading_overlay = LoadingOverlay(self.content_widget)

    def _show_loading(self):
        """Show loading overlay over content area"""
        self.loading_overlay.setGeometry(self.content_widget.rect())
        self.loading_overlay.show()
        self.loading_overlay.raise_()

    def _hide_loading(self):
        """Hide loading overlay"""
        self.loading_overlay.hide()

    def _search(self):
        phone = self.phone_input.text().strip()
        if not phone:
            return

        self.phone_number = phone
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching...")
        self._show_loading()

        def search_thread():
            orders = self.woo_client.search_orders_by_phone(phone)
            self.signals.search_result.emit(orders, phone)

        threading.Thread(target=search_thread, daemon=True).start()

    def _search_order(self):
        order_num = self.order_input.text().strip()
        if not order_num:
            return

        self.phone_number = f"order:{order_num}"  # Use special prefix for order search
        self.order_search_btn.setEnabled(False)
        self.order_search_btn.setText("Searching...")
        self._show_loading()

        def search_thread():
            orders = self.woo_client.get_order_by_number(order_num)
            self.signals.search_result.emit(orders, f"order:{order_num}")

        threading.Thread(target=search_thread, daemon=True).start()

    def search_phone(self, phone: str):
        """External method to search for a phone number"""
        self.phone_input.setText(phone)
        self.phone_number = phone
        self._search()

    def display_results(self, orders: list, phone: str):
        """Display search results - called from main window signal"""
        # Only process if this is for our phone number
        if phone != self.phone_number:
            return

        # Hide loading overlay
        self._hide_loading()

        # Re-enable both search buttons
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")
        self.order_search_btn.setEnabled(True)
        self.order_search_btn.setText("Find Order")
        self.current_orders = orders

        if not orders:
            self._clear_results()
            # Show appropriate message based on search type
            if phone.startswith("order:"):
                order_num = phone[6:]
                QMessageBox.information(self, "Not Found", f"No order found with number: #{order_num}")
            else:
                QMessageBox.information(self, "Not Found", f"No orders found for: {phone}")
            return

        # Customer info
        first_order = orders[0]
        billing = first_order.get('billing', {})

        name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
        self.customer_name.setText(name or "Unknown")

        self.info_labels['phone'].setText(billing.get('phone', '-'))
        self.info_labels['email'].setText(billing.get('email', '-'))
        self.info_labels['city'].setText(f"{billing.get('city', '')} {billing.get('country', '')}")

        address = f"{billing.get('address_1', '')} {billing.get('address_2', '')}".strip()
        self.info_labels['address'].setText(address or '-')

        # Stats
        currency = first_order.get('currency', 'BGN')
        total_spent = sum(float(o.get('total', 0)) for o in orders)
        self.total_orders.setText(str(len(orders)))
        self.total_spent.setText(f"{total_spent:.2f} {currency}")

        # Orders table
        self.orders_table.setRowCount(len(orders))
        for i, order in enumerate(orders):
            # Order number (with shop indicator if multi-shop)
            order_num = order.get('number', '')
            shop_name = order.get('_shop_name', '')
            shop_color = order.get('_shop_color', '#7c3aed')
            if shop_name:
                # Show shop initial as colored badge
                shop_initial = shop_name[0].upper() if shop_name else 'S'
                num_text = f"[{shop_initial}] #{order_num}"
            else:
                num_text = f"#{order_num}"
            num_item = QTableWidgetItem(num_text)
            num_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            if shop_name:
                num_item.setForeground(QColor(shop_color))
                num_item.setToolTip(f"Shop: {shop_name}")
            self.orders_table.setItem(i, 0, num_item)

            # Date - format as dd.mm.yyyy
            date_raw = order.get('date_created', '')
            if date_raw:
                date = f"{date_raw[8:10]}.{date_raw[5:7]}.{date_raw[:4]}"
            else:
                date = '-'
            self.orders_table.setItem(i, 1, QTableWidgetItem(date))

            # Status dropdown
            current_status = order.get('status', '')
            status_combo = QComboBox()
            status_combo.setFont(QFont("Segoe UI", 14))

            # Add statuses from API with colors
            current_index = 0
            for idx, st in enumerate(self.order_statuses):
                status_combo.addItem(st['name'], st['slug'])
                if st['slug'] == current_status:
                    current_index = idx

            status_combo.setCurrentIndex(current_index)

            # Apply custom delegate for colored items in dropdown
            order_status_delegate = ColoredComboDelegate(ORDER_STATUS_COLORS, status_combo)
            status_combo.setItemDelegate(order_status_delegate)

            # Get color for current status
            order_color = ORDER_STATUS_COLORS.get(current_status, '#6c757d')
            hover_bg = lighten_color(order_color, 0.7)

            # Style the main combo button
            status_combo.setStyleSheet(f"""
                QComboBox {{
                    font-weight: bold;
                    font-size: 14px;
                    border: 2px solid {order_color};
                    border-radius: 6px;
                    padding: 6px 10px;
                    background-color: white;
                    color: {order_color};
                }}
                QComboBox:hover {{
                    background-color: {hover_bg};
                    border-color: {order_color};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 25px;
                }}
                QComboBox QAbstractItemView {{
                    font-size: 14px;
                    padding: 0px;
                    background-color: white;
                    outline: none;
                }}
            """)

            # Connect to change handler
            order_id = order.get('id')
            row = i
            status_combo.currentIndexChanged.connect(
                lambda idx, oid=order_id, r=row, combo=status_combo: self._on_order_status_changed(oid, r, combo)
            )

            self.orders_table.setCellWidget(i, 2, status_combo)

            # ElevenLabs Call Status from meta_data - as dropdown
            call_status = ""
            meta_data = order.get('meta_data', [])
            for meta in meta_data:
                if meta.get('key') == 'ElevenLabs_Call_Status':
                    call_status = meta.get('value', '')
                    break

            # Create dropdown for call status
            call_combo = QComboBox()
            call_combo.setFont(QFont("Segoe UI", 14))

            # Add all status options with icons and colors
            current_index = 0
            for idx, (key, info) in enumerate(CALL_STATUSES.items()):
                display_text = f"{info['icon']} {info['text']}"
                call_combo.addItem(display_text, key)
                if key == call_status:
                    current_index = idx

            call_combo.setCurrentIndex(current_index)

            # Apply custom delegate for colored items in dropdown
            call_status_delegate = CallStatusComboDelegate(CALL_STATUSES, call_combo)
            call_combo.setItemDelegate(call_status_delegate)

            # Style based on current status
            call_color = CALL_STATUSES.get(call_status, {}).get('color', '#6c757d')
            call_hover_bg = lighten_color(call_color, 0.7)

            call_combo.setStyleSheet(f"""
                QComboBox {{
                    color: {call_color};
                    font-weight: bold;
                    font-size: 14px;
                    border: 2px solid {call_color};
                    border-radius: 6px;
                    padding: 6px 10px;
                    background-color: white;
                }}
                QComboBox:hover {{
                    background-color: {call_hover_bg};
                    border-color: {call_color};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 25px;
                }}
                QComboBox QAbstractItemView {{
                    font-size: 14px;
                    padding: 0px;
                    background-color: white;
                    outline: none;
                }}
            """)

            # Connect to change handler
            order_id = order.get('id')
            row = i
            call_combo.currentIndexChanged.connect(
                lambda idx, oid=order_id, r=row, combo=call_combo: self._on_call_status_changed(oid, r, combo)
            )

            self.orders_table.setCellWidget(i, 3, call_combo)

            # Items - show products, shipping, and fee lines
            all_items = []

            # Product lines - full format with SKU first
            for item in order.get('line_items', []):
                name = item.get('name', '')
                sku = item.get('sku', '')
                sku_text = f"[{sku}] " if sku else ""
                qty = item.get('quantity', 1)
                all_items.append(f"{sku_text}{name} x{qty}")

            # Shipping lines
            for shipping in order.get('shipping_lines', []):
                method = shipping.get('method_title', '') or shipping.get('method_id', 'Ship')
                total = shipping.get('total', '')
                if total and float(total) > 0:
                    all_items.append(f"🚚 {method}")

            # Fee lines
            for fee in order.get('fee_lines', []):
                fee_name = fee.get('name', 'Fee')
                all_items.append(f"⚙ {fee_name}")

            items_text = "\n".join(all_items)
            items_item = QTableWidgetItem(items_text)
            items_item.setToolTip(items_text)
            self.orders_table.setItem(i, 4, items_item)

            # Total
            total = f"{order.get('total', '0')} {order.get('currency', '')}"
            total_item = QTableWidgetItem(total)
            total_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            self.orders_table.setItem(i, 5, total_item)

            # Open button
            open_btn = QPushButton("Open")
            open_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6c757d;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #5a6268;
                }
            """)
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            order_id = order.get('id')
            open_btn.clicked.connect(lambda checked, oid=order_id: self._open_order(oid))
            self.orders_table.setCellWidget(i, 6, open_btn)

            # Odoo button - only if _odoo_order_id exists in meta_data
            odoo_order_id = None
            for meta in meta_data:
                if meta.get('key') == '_odoo_order_id':
                    odoo_order_id = meta.get('value')
                    break

            if odoo_order_id:
                # Get odoo_url from shop config
                shop_odoo_url = order.get('_shop_odoo_url', '')
                if shop_odoo_url:
                    odoo_btn = QPushButton("Odoo")
                    odoo_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #714B67;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            padding: 6px 12px;
                            font-size: 11px;
                        }
                        QPushButton:hover {
                            background-color: #5a3d52;
                        }
                    """)
                    odoo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    odoo_url = f"{shop_odoo_url}/{odoo_order_id}"
                    odoo_btn.clicked.connect(lambda checked, url=odoo_url: webbrowser.open(url))
                    self.orders_table.setCellWidget(i, 7, odoo_btn)

            # Auto row height based on all items
            row_height = max(60, 25 * len(all_items) + 20)
            self.orders_table.setRowHeight(i, row_height)

        self.open_btn.setEnabled(True)
        self.orders_table.selectRow(0)

    def _clear_results(self):
        self.customer_name.setText("No customer selected")
        for key in self.info_labels:
            self.info_labels[key].setText("-")
        self.total_orders.setText("-")
        self.total_spent.setText("-")
        self.orders_table.setRowCount(0)
        self.open_btn.setEnabled(False)
        self.current_orders = []

    def _open_order(self, order_id: int):
        if order_id:
            url = self.woo_client.get_order_url(order_id)
            webbrowser.open(url)

    def _open_woocommerce(self):
        selected = self.orders_table.currentRow()
        if selected >= 0 and selected < len(self.current_orders):
            order_id = self.current_orders[selected].get('id')
            self._open_order(order_id)

    def _on_order_selected(self, row: int, col: int, prev_row: int, prev_col: int):
        """Update customer info when a different order row is selected"""
        if row < 0 or row >= len(self.current_orders):
            return

        order = self.current_orders[row]
        billing = order.get('billing', {})

        # Update customer name
        name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
        self.customer_name.setText(name or "Unknown")

        # Update customer info labels
        self.info_labels['phone'].setText(billing.get('phone', '-'))
        self.info_labels['email'].setText(billing.get('email', '-'))
        self.info_labels['city'].setText(f"{billing.get('city', '')} {billing.get('country', '')}")

        address = f"{billing.get('address_1', '')} {billing.get('address_2', '')}".strip()
        self.info_labels['address'].setText(address or '-')

    def _on_order_status_changed(self, order_id: int, row: int, combo: QComboBox):
        """Handle order status dropdown change"""
        new_status = combo.currentData()

        # Get the previous status from stored order data
        prev_status = None
        if row < len(self.current_orders):
            prev_status = self.current_orders[row].get('status')

        # Store pending update info for potential revert
        self.pending_status_updates[row] = {
            'col': 2,
            'prev_status': prev_status,
            'prev_idx': combo.findData(prev_status) if prev_status else 0
        }

        # Update combo color immediately
        order_color = ORDER_STATUS_COLORS.get(new_status, '#6c757d')
        hover_bg = lighten_color(order_color, 0.7)
        combo.setStyleSheet(f"""
            QComboBox {{
                font-weight: bold;
                font-size: 14px;
                border: 2px solid {order_color};
                border-radius: 6px;
                padding: 6px 10px;
                background-color: white;
                color: {order_color};
            }}
            QComboBox:hover {{
                background-color: {hover_bg};
                border-color: {order_color};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 25px;
            }}
            QComboBox QAbstractItemView {{
                font-size: 14px;
                padding: 5px;
                background-color: white;
                color: #333;
                selection-background-color: {order_color};
                selection-color: white;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px;
                color: #333;
                background-color: white;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {hover_bg};
                color: #333;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {order_color};
                color: white;
            }}
        """)

        # Disable combo while updating
        combo.setEnabled(False)

        # Update via API in background thread
        def update_thread():
            success, message = self.woo_client.update_order_status(order_id, new_status)
            self.signals.status_update_result.emit(row, success, message)

        threading.Thread(target=update_thread, daemon=True).start()

    def _on_call_status_changed(self, order_id: int, row: int, combo: QComboBox):
        """Handle call status dropdown change"""
        new_status = combo.currentData()
        status_info = CALL_STATUSES.get(new_status, {})

        # Get previous call status from order meta_data
        prev_status = ""
        if row < len(self.current_orders):
            for meta in self.current_orders[row].get('meta_data', []):
                if meta.get('key') == '_call_status':
                    prev_status = meta.get('value', '')
                    break

        # Store pending update info for potential revert
        self.pending_status_updates[row] = {
            'col': 3,
            'prev_status': prev_status,
            'prev_idx': combo.findData(prev_status) if prev_status else 0
        }

        # Update combo color immediately
        call_color = status_info.get('color', '#6c757d')
        call_hover_bg = lighten_color(call_color, 0.7)
        combo.setStyleSheet(f"""
            QComboBox {{
                color: {call_color};
                font-weight: bold;
                font-size: 14px;
                border: 2px solid {call_color};
                border-radius: 6px;
                padding: 6px 10px;
                background-color: white;
            }}
            QComboBox:hover {{
                background-color: {call_hover_bg};
                border-color: {call_color};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 25px;
            }}
            QComboBox QAbstractItemView {{
                font-size: 14px;
                padding: 5px;
                background-color: white;
                color: #333;
                selection-background-color: {call_color};
                selection-color: white;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px;
                color: #333;
                background-color: white;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {call_hover_bg};
                color: #333;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {call_color};
                color: white;
            }}
        """)

        # Disable combo while updating
        combo.setEnabled(False)

        # Update via API in background thread
        def update_thread():
            success, message = self.woo_client.update_call_status(order_id, new_status)
            self.signals.status_update_result.emit(row, success, message)

        threading.Thread(target=update_thread, daemon=True).start()

    def on_status_update_result(self, row: int, success: bool, message: str):
        """Handle the result of status update API call"""
        # Get pending update info
        pending = self.pending_status_updates.pop(row, None)

        # Re-enable both order status (col 2) and call status (col 3) combos
        for col in (2, 3):
            combo = self.orders_table.cellWidget(row, col)
            if combo:
                combo.setEnabled(True)

        if success:
            logger.info(f"Status updated: {message}")
            # Update stored order data on success
            if pending and row < len(self.current_orders):
                if pending['col'] == 2:
                    # Order status
                    combo = self.orders_table.cellWidget(row, 2)
                    if combo:
                        self.current_orders[row]['status'] = combo.currentData()
                elif pending['col'] == 3:
                    # Call status - update meta_data
                    combo = self.orders_table.cellWidget(row, 3)
                    if combo:
                        new_call_status = combo.currentData()
                        found = False
                        for meta in self.current_orders[row].get('meta_data', []):
                            if meta.get('key') == '_call_status':
                                meta['value'] = new_call_status
                                found = True
                                break
                        if not found:
                            self.current_orders[row].setdefault('meta_data', []).append({
                                'key': '_call_status',
                                'value': new_call_status
                            })
        else:
            # Revert combo to previous value on failure
            if pending:
                combo = self.orders_table.cellWidget(row, pending['col'])
                if combo and pending['prev_idx'] >= 0:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(pending['prev_idx'])
                    # Update color to match reverted status
                    prev_status = pending['prev_status']
                    if pending['col'] == 2:
                        # Order status
                        order_color = ORDER_STATUS_COLORS.get(prev_status, '#6c757d')
                        hover_bg = lighten_color(order_color, 0.7)
                        combo.setStyleSheet(f"""
                            QComboBox {{
                                font-weight: bold;
                                font-size: 14px;
                                border: 2px solid {order_color};
                                border-radius: 6px;
                                padding: 6px 10px;
                                background-color: white;
                                color: {order_color};
                            }}
                            QComboBox:hover {{
                                background-color: {hover_bg};
                                border-color: {order_color};
                            }}
                            QComboBox::drop-down {{
                                border: none;
                                width: 25px;
                            }}
                            QComboBox QAbstractItemView {{
                                font-size: 14px;
                                padding: 5px;
                                background-color: white;
                                color: #333;
                                selection-background-color: {order_color};
                                selection-color: white;
                            }}
                            QComboBox QAbstractItemView::item {{
                                padding: 6px;
                                color: #333;
                                background-color: white;
                            }}
                            QComboBox QAbstractItemView::item:hover {{
                                background-color: {hover_bg};
                                color: #333;
                            }}
                            QComboBox QAbstractItemView::item:selected {{
                                background-color: {order_color};
                                color: white;
                            }}
                        """)
                    else:
                        # Call status
                        call_color = CALL_STATUSES.get(prev_status, {}).get('color', '#6c757d')
                        call_hover_bg = lighten_color(call_color, 0.7)
                        combo.setStyleSheet(f"""
                            QComboBox {{
                                color: {call_color};
                                font-weight: bold;
                                font-size: 14px;
                                border: 2px solid {call_color};
                                border-radius: 6px;
                                padding: 6px 10px;
                                background-color: white;
                            }}
                            QComboBox:hover {{
                                background-color: {call_hover_bg};
                                border-color: {call_color};
                            }}
                            QComboBox::drop-down {{
                                border: none;
                                width: 25px;
                            }}
                            QComboBox QAbstractItemView {{
                                font-size: 14px;
                                padding: 5px;
                                background-color: white;
                                color: #333;
                                selection-background-color: {call_color};
                                selection-color: white;
                            }}
                            QComboBox QAbstractItemView::item {{
                                padding: 6px;
                                color: #333;
                                background-color: white;
                            }}
                            QComboBox QAbstractItemView::item:hover {{
                                background-color: {call_hover_bg};
                                color: #333;
                            }}
                            QComboBox QAbstractItemView::item:selected {{
                                background-color: {call_color};
                                color: white;
                            }}
                        """)
                    combo.blockSignals(False)
            QMessageBox.warning(self, "Update Failed", f"Failed to update status:\n{message}")

    def _on_search_input_changed(self, text: str):
        """Hide results when user starts typing in search fields"""
        self._clear_results()

    def get_customer_name(self) -> str:
        """Return customer name for tab title"""
        name = self.customer_name.text()
        if name and name != "No customer selected":
            return name[:20] + "..." if len(name) > 20 else name
        return self.phone_number[:15] if self.phone_number else "New"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.woo_client = MultiShopClient(self.config)
        self.signals = SignalEmitter()
        self.ami: Optional[AsteriskAMI] = None
        self.webhook_server: Optional[WebhookServer] = None
        self.tab_counter = 0
        self.order_statuses = self.woo_client.get_order_statuses()

        self.setWindowTitle("Martinez Orders")
        self.setMinimumSize(1400, 900)
        self.resize(1800, 1000)

        # Set window/taskbar icon - purple "M" matching the app logo
        self.setWindowIcon(self._create_app_icon())

        # Light professional theme
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #f5f5f5;
                font-family: "Segoe UI", "SF Pro Display", Arial, sans-serif;
            }
        """)

        self.signals.incoming_call.connect(self._on_incoming_call)
        self.signals.connection_status.connect(self._update_status)
        self.signals.search_result.connect(self._on_search_result)
        self.signals.status_update_result.connect(self._on_status_update_result)

        self._setup_ui()
        self._connect_ami()
        self._start_webhook_server()

    def _create_app_icon(self) -> QIcon:
        """Create a purple M icon for the taskbar/dock"""
        size = 128
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded purple background
        painter.setBrush(QBrush(QColor("#7c3aed")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, size, size, 20, 20)

        # Draw white "M"
        painter.setPen(QPen(QColor("white")))
        font = QFont("Segoe UI", 72, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")

        painter.end()
        return QIcon(pixmap)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # ========== TOP BAR ==========
        top_bar = QHBoxLayout()

        # Logo/Icon and Title
        logo_label = QLabel("M")
        logo_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        logo_label.setStyleSheet("""
            background-color: #7c3aed;
            color: white;
            border-radius: 8px;
            padding: 4px 12px;
        """)
        logo_label.setFixedSize(50, 50)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_bar.addWidget(logo_label)

        title = QLabel("Martinez Orders")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #7c3aed; margin-left: 10px;")
        top_bar.addWidget(title)

        # Version label
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setFont(QFont("Segoe UI", 10))
        version_label.setStyleSheet("color: #999; margin-left: 10px;")
        top_bar.addWidget(version_label)

        top_bar.addStretch()

        # Update button (hidden by default)
        self.update_btn = QPushButton("Update Available")
        self.update_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self._show_update_dialog)
        top_bar.addWidget(self.update_btn)

        # Check for updates button
        self.check_update_btn = QPushButton("Check Updates")
        self.check_update_btn.setFont(QFont("Segoe UI", 10))
        self.check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_update_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #333;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:disabled {
                background-color: #f0f0f0;
                color: #999;
            }
        """)
        self.check_update_btn.clicked.connect(self._check_for_updates)
        top_bar.addWidget(self.check_update_btn)

        # Status indicator
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet("""
            QFrame {
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 4px;
                padding: 5px 10px;
            }
        """)
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(10, 5, 10, 5)
        self.status_label = QLabel("Asterisk: Connecting...")
        self.status_label.setFont(QFont("Segoe UI", 11))
        self.status_label.setStyleSheet("border: none;")
        status_layout.addWidget(self.status_label)
        top_bar.addWidget(self.status_frame)

        main_layout.addLayout(top_bar)

        # ========== TAB WIDGET ==========
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background: #f5f5f5;
            }
            QTabBar::tab {
                background: #e0e0e0;
                color: #333;
                padding: 10px 20px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background: white;
                border: 1px solid #e0e0e0;
                border-bottom: none;
            }
            QTabBar::tab:hover:!selected {
                background: #d0d0d0;
            }
        """)

        # Add "+" button for new tab
        self.new_tab_btn = QPushButton("+")
        self.new_tab_btn.setFixedSize(30, 30)
        self.new_tab_btn.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.new_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_tab_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                border: none;
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
        """)
        self.new_tab_btn.clicked.connect(self._add_new_tab)
        self.tab_widget.setCornerWidget(self.new_tab_btn, Qt.Corner.TopRightCorner)

        main_layout.addWidget(self.tab_widget, 1)

        # Create first tab
        self._add_new_tab()

    def _add_new_tab(self, phone: str = None) -> CustomerTab:
        """Add a new customer tab"""
        self.tab_counter += 1
        tab = CustomerTab(self.woo_client, self.signals, self.order_statuses, self)
        tab_title = f"📞 {phone[:12]}..." if phone and len(phone) > 12 else (f"📞 {phone}" if phone else "New")
        index = self.tab_widget.addTab(tab, tab_title)
        self.tab_widget.setCurrentIndex(index)

        if phone:
            tab.search_phone(phone)

        return tab

    def _close_tab(self, index: int):
        """Close a tab - keep at least one tab open"""
        if self.tab_widget.count() > 1:
            self.tab_widget.removeTab(index)
        else:
            # Clear the last tab instead of closing
            tab = self.tab_widget.widget(0)
            if isinstance(tab, CustomerTab):
                tab._clear_results()
                tab.phone_input.clear()
                self.tab_widget.setTabText(0, "New")

    def _connect_ami(self):
        def connect_thread():
            self.ami = AsteriskAMI(self.config, self.signals)
            if self.ami.connect():
                self.ami.start_listening()
        threading.Thread(target=connect_thread, daemon=True).start()

    def _start_webhook_server(self):
        webhook_port = self.config.settings.get('webhook_port', 5039)
        self.webhook_server = WebhookServer(self.signals, port=webhook_port)
        self.webhook_server.start()

    def _update_status(self, connected: bool, message: str):
        if connected:
            self.status_frame.setStyleSheet("""
                QFrame {
                    background-color: #d4edda;
                    border: 1px solid #28a745;
                    border-radius: 4px;
                }
            """)
            self.status_label.setText(f"✓ Asterisk: {message}")
            self.status_label.setStyleSheet("color: #155724; border: none;")
        else:
            self.status_frame.setStyleSheet("""
                QFrame {
                    background-color: #fff3cd;
                    border: 1px solid #ffc107;
                    border-radius: 4px;
                }
            """)
            self.status_label.setText(f"⚠ Asterisk: {message}")
            self.status_label.setStyleSheet("color: #856404; border: none;")

    def _on_search_result(self, orders: list, phone: str):
        """Route search results to the appropriate tab and update tab title"""
        # Find all tabs with this phone number and update them
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, CustomerTab) and tab.phone_number == phone:
                tab.display_results(orders, phone)
                # Update tab title with customer name
                if orders:
                    billing = orders[0].get('billing', {})
                    name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
                    tab_title = name[:15] + "..." if len(name) > 15 else name
                    self.tab_widget.setTabText(i, f"📞 {tab_title}" if tab_title else f"📞 {phone[:10]}")
                else:
                    self.tab_widget.setTabText(i, f"📞 {phone[:10]}...")

    def _on_status_update_result(self, row: int, success: bool, message: str):
        """Route status update results to current tab"""
        current_tab = self.tab_widget.currentWidget()
        if isinstance(current_tab, CustomerTab):
            current_tab.on_status_update_result(row, success, message)

    def _on_incoming_call(self, caller_id: str, event: dict):
        """Handle incoming call - open new tab with caller info"""
        # Create new tab for incoming call
        tab = self._add_new_tab(caller_id)

        # Bring window to front
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _check_for_updates(self, silent: bool = False):
        """Check GitHub for updates"""
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("Checking...")
        self._silent_update_check = silent

        self.update_checker = UpdateChecker()
        self.update_checker.update_available.connect(self._on_update_available)
        self.update_checker.no_update.connect(self._on_no_update)
        self.update_checker.error.connect(self._on_update_error)
        self.update_checker.start()

    def _on_update_available(self, version: str, download_url: str):
        """Called when a new version is available"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("Check Updates")

        # Store update info
        self._pending_update_version = version
        self._pending_update_url = download_url

        # Show update button
        self.update_btn.setText(f"Update to v{version}")
        self.update_btn.setVisible(True)

        # If not silent, show dialog immediately
        if not getattr(self, '_silent_update_check', False):
            self._show_update_dialog()

    def _on_no_update(self):
        """Called when app is up to date"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("Check Updates")

        if not getattr(self, '_silent_update_check', False):
            QMessageBox.information(self, "Up to Date", f"You are running the latest version (v{APP_VERSION})")

    def _on_update_error(self, error: str):
        """Called when update check fails"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("Check Updates")

        if not getattr(self, '_silent_update_check', False):
            QMessageBox.warning(self, "Update Check Failed", f"Could not check for updates:\n{error}")

    def _show_update_dialog(self):
        """Show the update dialog"""
        version = getattr(self, '_pending_update_version', None)
        url = getattr(self, '_pending_update_url', None)

        if version and url:
            dialog = UpdateDialog(version, url, self)
            dialog.exec()


def set_macos_dock_icon(pixmap: QPixmap):
    """Set the macOS dock icon using AppKit"""
    try:
        from AppKit import NSApplication, NSImage
        from PyQt6.QtCore import QBuffer, QIODevice

        # Convert QPixmap to PNG bytes
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        png_data = bytes(buffer.data())
        buffer.close()

        # Create NSImage from PNG data
        ns_image = NSImage.alloc().initWithData_(png_data)

        # Set as dock icon
        NSApplication.sharedApplication().setApplicationIconImage_(ns_image)
    except ImportError:
        pass  # pyobjc not installed, skip dock icon


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PhoneCaller")
    window = MainWindow()

    # Set dock icon on macOS
    if sys.platform == 'darwin':
        icon = window.windowIcon()
        if not icon.isNull():
            pixmap = icon.pixmap(128, 128)
            set_macos_dock_icon(pixmap)

    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
