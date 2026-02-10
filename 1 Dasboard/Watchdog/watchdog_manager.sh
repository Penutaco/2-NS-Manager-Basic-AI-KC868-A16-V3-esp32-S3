#!/bin/bash
# Dashboard Watchdog Management Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_SCRIPT="$SCRIPT_DIR/dashboard_watchdog.py"
SERVICE_FILE="$SCRIPT_DIR/dashboard-watchdog.service"
SYSTEM_SERVICE="/etc/systemd/system/dashboard-watchdog.service"

function show_usage() {
    echo "Dashboard Watchdog Management"
    echo "Usage: $0 {install|uninstall|start|stop|restart|status|logs|test}"
    echo ""
    echo "Commands:"
    echo "  install   - Install dependencies and setup systemd service"
    echo "  uninstall - Remove systemd service"
    echo "  start     - Start the watchdog service"
    echo "  stop      - Stop the watchdog service"
    echo "  restart   - Restart the watchdog service"
    echo "  status    - Show service status"
    echo "  logs      - Show service logs"
    echo "  test      - Test run watchdog manually (foreground)"
    echo ""
}

function install_dependencies() {
    echo "📦 Installing Python dependencies..."
    pip3 install --user psutil configparser
    
    if [ $? -eq 0 ]; then
        echo "✅ Dependencies installed successfully"
    else
        echo "❌ Failed to install dependencies"
        exit 1
    fi
}

function install_service() {
    echo "🔧 Installing Dashboard Watchdog Service..."
    
    # Install dependencies
    install_dependencies
    
    # Make watchdog script executable
    chmod +x "$WATCHDOG_SCRIPT"
    
    # Copy service file to systemd
    sudo cp "$SERVICE_FILE" "$SYSTEM_SERVICE"
    
    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable dashboard-watchdog.service
    
    echo "✅ Watchdog service installed successfully"
    echo "   Use 'sudo systemctl start dashboard-watchdog' to start"
    echo "   Use 'sudo systemctl status dashboard-watchdog' to check status"
}

function uninstall_service() {
    echo "🗑️  Uninstalling Dashboard Watchdog Service..."
    
    # Stop and disable service
    sudo systemctl stop dashboard-watchdog.service 2>/dev/null
    sudo systemctl disable dashboard-watchdog.service 2>/dev/null
    
    # Remove service file
    sudo rm -f "$SYSTEM_SERVICE"
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    echo "✅ Watchdog service uninstalled"
}

function start_service() {
    echo "🚀 Starting Dashboard Watchdog..."
    sudo systemctl start dashboard-watchdog.service
    sudo systemctl status dashboard-watchdog.service --no-pager -l
}

function stop_service() {
    echo "🛑 Stopping Dashboard Watchdog..."
    sudo systemctl stop dashboard-watchdog.service
    echo "✅ Watchdog stopped"
}

function restart_service() {
    echo "🔄 Restarting Dashboard Watchdog..."
    sudo systemctl restart dashboard-watchdog.service
    sudo systemctl status dashboard-watchdog.service --no-pager -l
}

function show_status() {
    echo "📊 Dashboard Watchdog Status:"
    sudo systemctl status dashboard-watchdog.service --no-pager -l
}

function show_logs() {
    echo "📋 Dashboard Watchdog Logs (last 50 lines):"
    sudo journalctl -u dashboard-watchdog.service -n 50 --no-pager
    echo ""
    echo "For live logs, use: sudo journalctl -u dashboard-watchdog.service -f"
}

function test_run() {
    echo "🧪 Testing Dashboard Watchdog (manual run)..."
    echo "Press Ctrl+C to stop"
    echo ""
    cd "$SCRIPT_DIR"
    python3 "$WATCHDOG_SCRIPT"
}

# Main script logic
case "$1" in
    install)
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    test)
        test_run
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
