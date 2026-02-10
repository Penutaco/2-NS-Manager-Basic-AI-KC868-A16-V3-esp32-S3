import time
import csv
import os
import copy
import threading
from datetime import datetime
from dash import dcc, html
from dash.dependencies import Output, Input
import dash
import plotly.graph_objs as go
import dash_bootstrap_components as dbc

# CONFIGURATION
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Global data storage for visualization
global_data = []
event_data = []
lock = threading.Lock()

def read_data_from_csv():
    """Read data from CSV files for visualization"""
    global global_data, event_data
    
    csv_file_position = 0
    current_csv_file = None
    last_full_reload = 0
    
    try:
        print("🔍 Starting CSV monitor for visualization...")
        
        while True:
            try:
                # Find latest sensor data CSV file
                data_files = [f for f in os.listdir(DATA_DIR) if f.startswith('sensor_data_') and f.endswith('.csv')]
                if data_files:
                    latest_file = max(data_files)
                    latest_path = os.path.join(DATA_DIR, latest_file)
                    
                    if current_csv_file != latest_path:
                        current_csv_file = latest_path
                        csv_file_position = 0
                        last_full_reload = time.time()
                        print(f"📊 Monitoring CSV file: {latest_file}")
                
                # Reload data periodically for time window support
                current_time = time.time()
                if current_time - last_full_reload > 300:  # Every 5 minutes
                    last_full_reload = current_time
                    max_window = 28800  # 8 hours maximum
                    reload_data_for_time_window(current_csv_file, max_window)
                
                # Read new lines from CSV
                if current_csv_file and os.path.exists(current_csv_file):
                    with open(current_csv_file, 'r') as f:
                        # Check if file has grown
                        file_size = os.path.getsize(current_csv_file)
                        if file_size <= csv_file_position:
                            continue  # No new data
                        
                        f.seek(csv_file_position)
                        new_lines = f.readlines()
                        csv_file_position = f.tell()
                        
                        for line in new_lines:
                            line = line.strip()
                            if line and not line.startswith('Time'):  # Skip header
                                parts = line.split(',')
                                if len(parts) >= 11:  # Sensor data line
                                    try:
                                        time_ms = float(parts[0]) if parts[0].strip() else None
                                        if time_ms:
                                            # Simple parsing like dashboard - only filter out inf/nan values, keep all other values including 0.0
                                            sensor_values = []
                                            for p in parts[1:11]:
                                                if p.strip():
                                                    try:
                                                        val = float(p)
                                                        # Only filter out infinite values, keep everything else including 0.0 for calibration
                                                        if val == float('inf') or val == float('-inf') or val != val:  # val != val checks for NaN
                                                            sensor_values.append(None)
                                                        else:
                                                            sensor_values.append(val)
                                                    except (ValueError, OverflowError):
                                                        sensor_values.append(None)
                                                else:
                                                    sensor_values.append(None)
                                            
                                            with lock:
                                                global_data.append([time_ms] + sensor_values)
                                                # Keep reasonable amount of data for visualization
                                                if len(global_data) > 50000:
                                                    global_data = global_data[-25000:]
                                                
                                                # Store event info if present
                                                if len(parts) > 11 and parts[11].strip():
                                                    event_data.append(parts[11].strip())
                                                    # Keep recent events
                                                    if len(event_data) > 1000:
                                                        event_data = event_data[-500:]
                                                        
                                    except (ValueError, IndexError):
                                        continue
                
            except Exception as e:
                print(f"❌ Error reading CSV: {e}")
            
            time.sleep(0.1)  # Check every 100ms
                
    except Exception as e:
        print(f"❌ Error in CSV reading: {e}")

def reload_data_for_time_window(csv_file, time_window_seconds):
    """Reload historical data to support current time window"""
    if not csv_file or not os.path.exists(csv_file):
        return
    
    try:
        current_time_ms = time.time() * 1000
        cutoff_time_ms = current_time_ms - (time_window_seconds * 1000)
        
        with lock:
            # Check if we need more historical data
            if global_data and global_data[0][0] > cutoff_time_ms:
                print(f"🔄 Reloading data for {time_window_seconds}s time window...")
                
                temp_data = []
                with open(csv_file, 'r') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    
                    for row in reader:
                        if len(row) >= 11:
                            try:
                                time_ms = float(row[0]) if row[0].strip() else None
                                if time_ms and time_ms >= cutoff_time_ms:
                                    # Simple parsing like dashboard - only filter out inf/nan values, keep all other values including 0.0
                                    sensor_values = []
                                    for p in row[1:11]:
                                        if p.strip():
                                            try:
                                                val = float(p)
                                                # Only filter out infinite values, keep everything else including 0.0 for calibration
                                                if val == float('inf') or val == float('-inf') or val != val:  # val != val checks for NaN
                                                    sensor_values.append(None)
                                                else:
                                                    sensor_values.append(val)
                                            except (ValueError, OverflowError):
                                                sensor_values.append(None)
                                        else:
                                            sensor_values.append(None)
                                    temp_data.append([time_ms] + sensor_values)
                            except (ValueError, IndexError):
                                continue
                
                global_data.clear()
                global_data.extend(temp_data)
                print(f"📈 Loaded {len(global_data)} data points for visualization")
                
    except Exception as e:
        print(f"❌ Error reloading data: {e}")

def create_graph_with_controls(graph_id, graph_title):
    """Create a graph with y-axis controls"""
    return html.Div([
        html.H4(graph_title),
        html.Div([
            html.Div([
                html.Label("Center Point:", style={'marginRight': '10px', 'fontSize': '14px'}),
                dcc.Input(
                    id=f'{graph_id}-center-input',
                    type='number',
                    placeholder='Auto',
                    step=0.01,
                    style={'width': '80px'}
                ),
            ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
            
            html.Div([
                html.Label("Signal Range:", style={'marginRight': '10px', 'fontSize': '14px'}),
                dcc.Input(
                    id=f'{graph_id}-signal-input',
                    type='number',
                    min=0.001,
                    max=20,
                    step=0.001,
                    value=1,
                    style={'width': '80px'}
                ),
            ], style={'width': '48%', 'display': 'inline-block'}),
        ], style={'margin': '5px 0', 'padding': '5px', 'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),
        dcc.Graph(id=graph_id),
    ], style={'marginBottom': '30px'})

def start_csv_monitor_thread():
    """Start CSV monitoring thread"""
    thread = threading.Thread(target=read_data_from_csv)
    thread.daemon = True
    thread.start()
    print("🚀 Started CSV monitoring thread")
    return thread

# Initialize Dash app
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("Hydroponic Sensor Visualization", style={'textAlign': 'center', 'color': '#2c3e50'}),
    
    html.Div([
        html.Div([
            html.Label("Time Window (seconds):", style={'marginRight': '10px', 'fontWeight': 'bold'}),
            dcc.Slider(
                id='time-window-slider',
                min=5,
                max=28800,
                step=5,
                value=60,
                marks={i: f'{i}s' for i in [5, 30, 60, 120, 180, 240, 300]},
                tooltip={"placement": "bottom", "always_visible": True}
            ),
            html.Div([
                html.Label("Visualization Mode:", style={'marginRight': '10px', 'marginTop': '15px', 'fontWeight': 'bold'}),
                dcc.RadioItems(
                    id='viz-mode-selector',
                    options=[
                        {'label': 'Full data', 'value': 'full'},
                        {'label': 'Time window', 'value': 'window'}
                    ],
                    value='window',
                    inline=True
                )
            ], style={'marginTop': '10px'})
        ], style={'width': '80%', 'display': 'inline-block', 'verticalAlign': 'middle'}),
        
        html.Div([
            html.Div(id='data-status', style={'fontSize': '14px', 'color': '#27ae60', 'fontWeight': 'bold'})
        ], style={'width': '20%', 'display': 'inline-block', 'verticalAlign': 'middle', 'textAlign': 'right'})
    ], style={'margin': '20px 0', 'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '8px'}),
    
    # Sensor graphs
    create_graph_with_controls('graph-photoresistor', 'Photoresistor (V)'),
    create_graph_with_controls('graph-absorbance', 'Absorbance (a.u.)'),
    create_graph_with_controls('graph-concentration', 'Concentration (ppm)'),
    create_graph_with_controls('graph-ec-voltage', 'EC Voltage (V)'),
    create_graph_with_controls('graph-ec-ppm', 'EC (mS/cm)'),
    create_graph_with_controls('graph-ph-voltage', 'pH Voltage (V)'),
    create_graph_with_controls('graph-ph-value', 'pH Value'),
    create_graph_with_controls('graph-nitrate-voltage', 'Nitrate Voltage (V)'),
    create_graph_with_controls('graph-nitrate-value', 'Nitrate (ppm)'),
    create_graph_with_controls('graph-temperature', 'Temperature (°C)'),
    
    dcc.Interval(id='interval-component', interval=1*1000, n_intervals=0),
    
    html.Hr(),
    html.H3("Recent Events", style={'color': '#2c3e50'}),
    html.Div(id='event-log', style={
        'whiteSpace': 'pre-wrap',
        'overflowY': 'scroll',
        'maxHeight': '300px',
        'backgroundColor': '#f8f9fa',
        'padding': '10px',
        'borderRadius': '5px',
        'fontFamily': 'monospace'
    })
])

@app.callback(
    [Output('graph-photoresistor', 'figure'),
     Output('graph-absorbance', 'figure'),
     Output('graph-concentration', 'figure'),
     Output('graph-ec-voltage', 'figure'),
     Output('graph-ec-ppm', 'figure'),
     Output('graph-ph-voltage', 'figure'),
     Output('graph-ph-value', 'figure'),
     Output('graph-nitrate-voltage', 'figure'),
     Output('graph-nitrate-value', 'figure'),
     Output('graph-temperature', 'figure'),
     Output('data-status', 'children')],
    [Input('interval-component', 'n_intervals'),
     Input('time-window-slider', 'value'),
     Input('viz-mode-selector', 'value'),
     Input('graph-photoresistor-center-input', 'value'),
     Input('graph-photoresistor-signal-input', 'value'),
     Input('graph-absorbance-center-input', 'value'),
     Input('graph-absorbance-signal-input', 'value'),
     Input('graph-concentration-center-input', 'value'),
     Input('graph-concentration-signal-input', 'value'),
     Input('graph-ec-voltage-center-input', 'value'),
     Input('graph-ec-voltage-signal-input', 'value'),
     Input('graph-ec-ppm-center-input', 'value'),
     Input('graph-ec-ppm-signal-input', 'value'),
     Input('graph-ph-voltage-center-input', 'value'),
     Input('graph-ph-voltage-signal-input', 'value'),
     Input('graph-ph-value-center-input', 'value'),
     Input('graph-ph-value-signal-input', 'value'),
     Input('graph-nitrate-voltage-center-input', 'value'),
     Input('graph-nitrate-voltage-signal-input', 'value'),
     Input('graph-nitrate-value-center-input', 'value'),
     Input('graph-nitrate-value-signal-input', 'value'),
     Input('graph-temperature-center-input', 'value'),
     Input('graph-temperature-signal-input', 'value')]
)
def update_graphs(n_intervals, time_window, viz_mode, *axis_controls):
    with lock:
        data = copy.deepcopy(global_data)
    
    # If no data, return empty graphs
    if not data:
        empty_fig = {'data': [], 'layout': {'title': 'Waiting for data...', 'plot_bgcolor': '#f8f9fa'}}
        status = f"📊 No data yet ({len(data)} points)"
        return [empty_fig] * 10 + [status]
    
    # Extract time and sensor values
    time_ms = [d[0] for d in data]
    time_sec = time_ms  # Use raw values
    
    sensor_data = {
        'photoresistor': [d[1] for d in data],
        'absorbance': [d[2] for d in data],
        'concentration': [d[3] for d in data],
        'ec_voltage': [d[4] for d in data],
        'ec_ppm': [d[5] for d in data],
        'ph_voltage': [d[6] for d in data],
        'ph_value': [d[7] for d in data],
        'nitrate_voltage': [d[8] for d in data],
        'nitrate_ppm': [d[9] for d in data],
        'temperature': [d[10] for d in data]
    }
    
    # Determine time range for visualization
    if viz_mode == 'window' and len(time_sec) > 0:
        if time_sec[-1] > time_window:
            x_range = [time_sec[-1] - time_window, time_sec[-1]]
        else:
            x_range = [0, max(time_window, time_sec[-1])]
    else:  # 'full' mode
        if len(time_sec) > 0:
            x_range = [time_sec[0], time_sec[-1]]
        else:
            x_range = [0, 100]
    
    # Helper function to create graph
    def create_graph(sensor_name, y_data, title, center_val, signal_val):
        # Keep ALL data points including None values to preserve timestamps for gaps
        x_all = time_sec
        y_all = y_data  # This includes None values where inf/nan occurred
        
        # For y-axis scaling, use only valid values
        valid_values = [v for v in y_data if v is not None]
        
        # Determine y-axis range using advanced logic from dashboard
        if center_val is not None and signal_val is not None:
            # Use FULL signal range (not half) - matching dashboard behavior
            y_min = center_val - signal_val
            y_max = center_val + signal_val
        else:
            # Advanced adaptive logic when controls are empty - matching dashboard exactly
            if valid_values:
                y_min_data = min(valid_values)
                y_max_data = max(valid_values)
                y_center = (y_min_data + y_max_data) / 2
                base_range = max(y_max_data - y_min_data, max(0.05, abs(y_center * 0.05)))
                applied_range = base_range * (signal_val or 1.0)  # Use signal_val as multiplier
                y_min = max(0, y_center - applied_range/2)  # Prevent negative values
                y_max = y_center + applied_range/2
            else:
                y_min = 0
                y_max = 1
        
        y_range = [y_min, y_max]
        
        return {
            'data': [go.Scatter(
                x=x_all,
                y=y_all,
                mode='lines+markers',
                name=sensor_name,
                line=dict(width=2, color='#3498db'),
                marker=dict(size=3, color='#3498db'),
                connectgaps=False  # This will show gaps where None values exist
            )],
            'layout': go.Layout(
                title=title,
                xaxis={'title': 'Time (s)', 'range': x_range},
                yaxis={'title': title, 'range': y_range},
                plot_bgcolor='#f8f9fa',
                paper_bgcolor='white',
                font={'size': 12},
                margin={'l': 60, 'r': 20, 't': 40, 'b': 40}
            )
        }
    
    # Create all graphs with axis controls
    sensor_names = ['photoresistor', 'absorbance', 'concentration', 'ec_voltage', 'ec_ppm', 
                   'ph_voltage', 'ph_value', 'nitrate_voltage', 'nitrate_ppm', 'temperature']
    
    titles = ['Photoresistor (V)', 'Absorbance (a.u.)', 'Concentration (ppm)', 'EC Voltage (V)', 
             'EC (mS/cm)', 'pH Voltage (V)', 'pH Value', 'Nitrate Voltage (V)', 'Nitrate (ppm)', 'Temperature (°C)']
    
    figures = []
    for i, (sensor_name, title) in enumerate(zip(sensor_names, titles)):
        center_val = axis_controls[i*2]
        signal_val = axis_controls[i*2 + 1]
        fig = create_graph(sensor_name, sensor_data[sensor_name], title, center_val, signal_val)
        figures.append(fig)
    
    # Status message
    latest_time = time_sec[-1] if time_sec else 0
    mode_text = "Window" if viz_mode == 'window' else "Full"
    status = f"📊 {len(data)} points | Latest: {latest_time:.0f} ms | Mode: {mode_text}"
    
    return figures + [status]

@app.callback(
    Output('event-log', 'children'),
    [Input('interval-component', 'n_intervals')]
)
def update_event_log(n_intervals):
    with lock:
        events = copy.deepcopy(event_data)
    
    if not events:
        return "No events recorded yet..."
    
    # Show last 20 events
    recent_events = events[-20:]
    return '\n'.join(recent_events)

def main():
    """Main function to run visualization"""
    print("=== Hydroponic Sensor Visualization ===")
    print(f"Data Directory: {DATA_DIR}")
    print("="*45)
    
    try:
        # Start CSV monitoring
        csv_thread = start_csv_monitor_thread()
        
        print("\n🚀 Visualization system started successfully!")
        print("📊 CSV monitoring active")
        print("🌐 Starting web interface...")
        print("\n💡 Open browser to: http://localhost:8051")
        
        # Start Dash server
        app.run(debug=False, host='0.0.0.0', port=8051)
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down visualization system...")
    except Exception as e:
        print(f"❌ Error in main: {e}")
    finally:
        print("✅ Visualization system stopped.")

if __name__ == "__main__":
    main()
