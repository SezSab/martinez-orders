# PhoneCaller

A cross-platform desktop application that monitors Asterisk PBX calls and displays WooCommerce customer order information.

## Features

- Runs minimized in system tray (Windows/Mac/Linux)
- Monitors incoming calls via Asterisk AMI
- Looks up customer by phone number in WooCommerce
- Shows system notification + detailed popup with:
  - Customer name, email, phone, address
  - Total orders and lifetime spend
  - Last order details with items

## Requirements

- Python 3.8+
- Asterisk PBX with AMI enabled
- WooCommerce store with REST API access

## Installation

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the example config and edit with your details:
```bash
cp config.example.json config.json
```

4. Edit `config.json` with your credentials:
```json
{
    "asterisk": {
        "host": "your-asterisk-ip",
        "port": 5038,
        "username": "your-ami-user",
        "secret": "your-ami-password"
    },
    "woocommerce": {
        "url": "https://your-store.com",
        "consumer_key": "ck_...",
        "consumer_secret": "cs_..."
    }
}
```

## Asterisk AMI Setup

Make sure AMI is enabled in `/etc/asterisk/manager.conf`:

```ini
[general]
enabled = yes
port = 5038
bindaddr = 0.0.0.0

[your-ami-user]
secret = your-ami-password
deny = 0.0.0.0/0.0.0.0
permit = YOUR_IP/255.255.255.255
read = call,agent
write = call,agent
```

Reload Asterisk after changes:
```bash
asterisk -rx "manager reload"
```

## WooCommerce API Setup

1. Go to WooCommerce > Settings > Advanced > REST API
2. Click "Add Key"
3. Description: "PhoneCaller"
4. User: Select admin user
5. Permissions: Read
6. Click "Generate API Key"
7. Copy the Consumer Key and Consumer Secret to your config

## Usage

Run the application:
```bash
python phonecaller.py
```

The app will:
1. Start minimized in the system tray
2. Connect to your Asterisk server
3. Listen for incoming calls
4. When a call comes in, search WooCommerce for the customer
5. Display a notification and popup with order info

### System Tray Menu

- **Reconnect**: Reconnect to Asterisk if connection is lost
- **Test Popup**: Show a test popup to verify it's working
- **Quit**: Exit the application

## Running on Startup

### Windows
Create a shortcut to `pythonw.exe phonecaller.py` and place it in:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

### macOS
Create a Launch Agent in `~/Library/LaunchAgents/com.phonecaller.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.phonecaller</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/path/to/phonecaller.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

### Linux
Add to your desktop environment's autostart or create a systemd user service.

## Troubleshooting

- **Red tray icon**: Not connected to Asterisk - check your AMI credentials and firewall
- **No popup on call**: Check the log file `phonecaller.log` for errors
- **Customer not found**: Ensure the phone number format in WooCommerce matches incoming calls

## License

MIT
