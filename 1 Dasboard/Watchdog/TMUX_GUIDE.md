# TMUX Guide for Hydroponic Dashboard

## Quick Start Commands

### Start Watchdog (Recommended Method)
```bash
# Start watchdog in background tmux session
tmux new-session -d -s hydro-watchdog 'cd "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard" && "/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python" dashboard_watchdog.py'

# View watchdog logs (attach to session)
tmux attach-session -t hydro-watchdog
```

### Start Dashboard Directly (Optional)
```bash
# Start dashboard in separate tmux session
tmux new-session -d -s hydro-dashboard 'cd "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard" && "/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python" "1p2 dashboard v10 NS Manager Basic.py"'

# View dashboard logs
tmux attach-session -t hydro-dashboard
```

## TMUX Session Management

### View Sessions
```bash
# List all running sessions
tmux list-sessions

# Check if sessions are running
tmux has-session -t hydro-watchdog && echo "Watchdog running" || echo "Watchdog stopped"
```

### Attach/Detach
```bash
# Attach to watchdog session
tmux attach-session -t hydro-watchdog

# Attach to dashboard session  
tmux attach-session -t hydro-dashboard

# Detach from session (while inside tmux): Ctrl+B then D
```

### Kill Sessions
```bash
# Kill watchdog session
tmux kill-session -t hydro-watchdog

# Kill dashboard session
tmux kill-session -t hydro-dashboard

# Kill all sessions
tmux kill-server
```

## TMUX Keyboard Shortcuts (Inside Session)

- **Ctrl+B then D**: Detach from session (keeps running in background)
- **Ctrl+B then C**: Create new window in session
- **Ctrl+B then N**: Next window
- **Ctrl+B then P**: Previous window
- **Ctrl+B then [**: Enter scroll mode (use arrows, Page Up/Down, then Q to exit)

## Usage Workflow

### 1. Start Watchdog
```bash
tmux new-session -d -s hydro-watchdog 'cd "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard" && "/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python" dashboard_watchdog.py'
```

### 2. Check Status
```bash
tmux list-sessions
```

### 3. View Logs Anytime
```bash
tmux attach-session -t hydro-watchdog
# Press Ctrl+B then D to detach
```

### 4. Dashboard Restart Monitoring
When watchdog restarts dashboard, you can:
- Stay attached to see real-time logs
- Detach and check later
- Dashboard will run in background automatically

## Benefits

✅ **Persistent Sessions**: Sessions survive SSH disconnections
✅ **Background Execution**: Can detach and let it run
✅ **Real-time Monitoring**: Attach anytime to see live logs
✅ **Multiple Windows**: Can run watchdog and dashboard in separate sessions
✅ **Professional**: Industry standard for server management

## Troubleshooting

### Session Not Found
```bash
# Check if session exists
tmux has-session -t hydro-watchdog 2>/dev/null && echo "Exists" || echo "Not found"

# Start new session if needed
tmux new-session -d -s hydro-watchdog 'cd "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard" && "/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python" dashboard_watchdog.py'
```

### Session Already Exists
```bash
# Kill existing and start fresh
tmux kill-session -t hydro-watchdog 2>/dev/null
tmux new-session -d -s hydro-watchdog 'cd "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard" && "/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python" dashboard_watchdog.py'
```

## Log Files

- **Watchdog Logs**: `dashboard_watchdog.log` (in Dashboard folder)
- **Dashboard Logs**: Check tmux session or dashboard's own log files

## Recommended Daily Workflow

1. **Morning**: `tmux attach-session -t hydro-watchdog` - Check overnight status
2. **During Day**: Detached - let it run automatically  
3. **Evening**: Attach again to check status
4. **Maintenance**: Kill sessions, update code, restart fresh sessions
