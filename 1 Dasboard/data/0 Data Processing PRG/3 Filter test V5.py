import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
from tkinter import filedialog, Tk
import os

# Função para exibir seletor de arquivos
def show_file_picker(initial_dir="."):
    """Exibe uma janela para selecionar o arquivo CSV"""
    root = Tk()
    root.withdraw()  # Oculta a janela principal do Tkinter
    file_path = filedialog.askopenfilename(
        title="Selecione o arquivo CSV",
        initialdir=initial_dir,
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )
    root.destroy()  # Fecha o Tkinter após a seleção
    return file_path

# 1. Carregar dados
def load_data():
    print("Abrindo janela para selecionar arquivo...")
    file_path = show_file_picker()  # Use a função para selecionar o arquivo
    if not file_path:
        print("Nenhum arquivo selecionado. Saindo...")
        return None, None
    print(f"Arquivo selecionado: {file_path}")
    
    try:
        df = pd.read_csv(file_path)
        return df, file_path
    except Exception as e:
        print(f"Erro ao carregar o arquivo: {e}")
        return None, None

# 2. Implementação dos filtros
class FilterImplementations:
    @staticmethod
    def median_filter(data, window_size):
        return pd.Series(data).rolling(window=window_size, center=True).median().fillna(method='bfill').fillna(method='ffill').values
    
    @staticmethod
    def iir_filter(data, alpha):
        filtered = np.zeros(len(data))
        filtered[0] = data[0]
        for i in range(1, len(data)):
            filtered[i] = alpha * data[i] + (1 - alpha) * filtered[i-1]
        return filtered
    
    @staticmethod
    def moving_average(data, window_size):
        return pd.Series(data).rolling(window=window_size, center=True).mean().fillna(method='bfill').fillna(method='ffill').values
    
    @staticmethod
    def kalman_filter(data, process_variance, measurement_variance):
        n = len(data)
        filtered = np.zeros(n)
        prediction = data[0]
        prediction_variance = 1.0
        
        for i in range(n):
            prediction_variance = prediction_variance + process_variance
            kalman_gain = prediction_variance / (prediction_variance + measurement_variance)
            filtered[i] = prediction + kalman_gain * (data[i] - prediction)
            prediction = filtered[i]
            prediction_variance = (1 - kalman_gain) * prediction_variance
        
        return filtered
    
    @staticmethod
    def multi_stage_filter(data, window_size, alpha):
        median_filtered = FilterImplementations.median_filter(data, window_size)
        return FilterImplementations.iir_filter(median_filtered, alpha)
    
    @staticmethod
    def savgol_filter_wrapper(data, window_size, poly_order):
        window_size = max(poly_order + 1, window_size)
        if window_size % 2 == 0:
            window_size += 1
        return savgol_filter(data, window_size, poly_order)
    
    @staticmethod
    def oversampling_decimation(data, factor, window_size):
        upsampled = np.repeat(data, factor)
        smoothed = pd.Series(upsampled).rolling(window=window_size, center=True).mean().fillna(method='bfill').fillna(method='ffill').values
        decimated = smoothed[::factor]
        if len(decimated) != len(data):
            decimated = np.interp(np.arange(len(data)), np.linspace(0, len(data)-1, len(decimated)), decimated)
        return decimated

# 3. Otimização de filtros
WINDOW_SIZES = range(50, 101, 10)  # Janela de 50 a 100 pontos, incrementos de 10

def optimize_filters(time, ph_data):
    results = []
    print("\nOtimizando filtros...")
    
    # Adicione esta nova estrutura para armazenar todos os resultados de filtros
    all_filtered_signals = {
        "Original": ph_data
    }
    
    # Filtro de Mediana Móvel
    print("- Filtro de Mediana Móvel")
    for window in WINDOW_SIZES:
        try:
            filtered = FilterImplementations.median_filter(ph_data, window)
            std_dev = np.std(filtered - ph_data)
            all_filtered_signals[f"Median_W{window}"] = filtered
            results.append({
                "Filter": "Median",
                "Window Size": window,
                "Std Deviation": std_dev,
                "Alpha": None,
                "Process Variance": None,
                "Measurement Variance": None,
                "Poly Order": None,
                "Oversampling Factor": None
            })
        except Exception as e:
            print(f"  Erro com tamanho de janela {window}: {e}")
    
    # Filtro de Média Móvel
    print("- Filtro de Média Móvel")
    for window in WINDOW_SIZES:
        filtered = FilterImplementations.moving_average(ph_data, window)
        std_dev = np.std(filtered - ph_data)
        all_filtered_signals[f"MovingAverage_W{window}"] = filtered
        results.append({"Filter": "Moving Average", "Window Size": window, 
                       "Std Deviation": std_dev, "Alpha": None,
                       "Process Variance": None, "Measurement Variance": None,
                       "Poly Order": None, "Oversampling Factor": None})
    
    # Filtro Multi-estágio (Mediana + IIR)
    print("- Filtro Multi-estágio (Mediana + IIR)")
    for window in WINDOW_SIZES:
        for alpha in np.linspace(0.1, 0.9, 5):
            filtered = FilterImplementations.multi_stage_filter(ph_data, window, alpha)
            std_dev = np.std(filtered - ph_data)
            all_filtered_signals[f"MultiStage_W{window}_A{alpha:.2f}"] = filtered
            results.append({"Filter": "Multi-stage", "Window Size": window, 
                           "Std Deviation": std_dev, "Alpha": alpha,
                           "Process Variance": None, "Measurement Variance": None,
                           "Poly Order": None, "Oversampling Factor": None})
    
    # Filtro de Kalman
    print("- Filtro de Kalman")
    for pv in [0.001, 0.01, 0.1, 1.0]:
        for mv in [0.01, 0.1, 1.0, 10.0]:
            filtered = FilterImplementations.kalman_filter(ph_data, pv, mv)
            std_dev = np.std(filtered - ph_data)
            all_filtered_signals[f"Kalman_PV{pv}_MV{mv}"] = filtered
            results.append({"Filter": "Kalman", "Window Size": None, 
                           "Std Deviation": std_dev, "Alpha": None,
                           "Process Variance": pv, "Measurement Variance": mv,
                           "Poly Order": None, "Oversampling Factor": None})
    
    # Filtro Passa-Baixa IIR
    print("- Filtro Passa-Baixa IIR")
    for alpha in np.linspace(0.1, 0.9, 9):
        filtered = FilterImplementations.iir_filter(ph_data, alpha)
        std_dev = np.std(filtered - ph_data)
        all_filtered_signals[f"IIR_A{alpha:.2f}"] = filtered
        results.append({"Filter": "IIR", "Window Size": None, 
                       "Std Deviation": std_dev, "Alpha": alpha,
                       "Process Variance": None, "Measurement Variance": None,
                       "Poly Order": None, "Oversampling Factor": None})
    
    # Sobreamostragem + Decimação
    print("- Sobreamostragem + Decimação")
    for factor in [2, 4, 8]:
        for window in WINDOW_SIZES:
            try:
                filtered = FilterImplementations.oversampling_decimation(ph_data, factor, window)
                std_dev = np.std(filtered - ph_data)
                all_filtered_signals[f"OversamplingDecimation_F{factor}_W{window}"] = filtered
                results.append({"Filter": "Oversampling + Decimation", "Window Size": window, 
                               "Std Deviation": std_dev, "Alpha": None,
                               "Process Variance": None, "Measurement Variance": None,
                               "Poly Order": None, "Oversampling Factor": factor})
            except Exception as e:
                pass
    
    # Filtro Savitzky-Golay
    print("- Filtro Savitzky-Golay")
    for window in WINDOW_SIZES:  # Janela de 50 a 100 pontos, incrementos de 10
        for poly in [2, 3, 4]:  # Polinômios de ordem 2, 3 e 4
            if window > poly:  # A janela deve ser maior que a ordem do polinômio
                try:
                    filtered = FilterImplementations.savgol_filter_wrapper(ph_data, window, poly)
                    std_dev = np.std(filtered - ph_data)
                    all_filtered_signals[f"SavitzkyGolay_W{window}_P{poly}"] = filtered
                    results.append({
                        "Filter": "Savitzky-Golay",
                        "Window Size": window,
                        "Std Deviation": std_dev,
                        "Alpha": None,
                        "Process Variance": None,
                        "Measurement Variance": None,
                        "Poly Order": poly,
                        "Oversampling Factor": None
                    })
                except Exception as e:
                    print(f"  Erro com janela {window} e polinômio {poly}: {e}")
    
    # Criar DataFrame com resultados
    results_df = pd.DataFrame(results)
    
    # Encontrar os melhores parâmetros para cada filtro
    best_filters = {}
    filtered_signals = {"Original": ph_data}
    
    for filter_type in results_df["Filter"].unique():
        filter_subset = results_df[results_df["Filter"] == filter_type]
        if not filter_subset.empty:
            best_idx = filter_subset["Std Deviation"].idxmin()
            best_row = filter_subset.loc[best_idx]
            
            # Aplicar o melhor filtro de cada tipo
            if filter_type == "Median":
                best_window = int(best_row["Window Size"])
                filtered = FilterImplementations.median_filter(ph_data, best_window)
                filtered_signals[f"Best {filter_type}"] = filtered
                
            elif filter_type == "IIR":
                best_alpha = float(best_row["Alpha"])
                filtered = FilterImplementations.iir_filter(ph_data, best_alpha)
                filtered_signals[f"Best {filter_type}"] = filtered
                
            elif filter_type == "Moving Average":
                best_window = int(best_row["Window Size"])
                filtered = FilterImplementations.moving_average(ph_data, best_window)
                filtered_signals[f"Best {filter_type}"] = filtered
                
            elif filter_type == "Kalman":
                best_pv = float(best_row["Process Variance"])
                best_mv = float(best_row["Measurement Variance"])
                filtered = FilterImplementations.kalman_filter(ph_data, best_pv, best_mv)
                filtered_signals[f"Best {filter_type}"] = filtered
                
            elif filter_type == "Multi-stage":
                best_window = int(best_row["Window Size"])
                best_alpha = float(best_row["Alpha"])
                filtered = FilterImplementations.multi_stage_filter(ph_data, best_window, best_alpha)
                filtered_signals[f"Best {filter_type}"] = filtered
                
            elif filter_type == "Savitzky-Golay":
                best_window = int(best_row["Window Size"])
                best_poly = int(best_row["Poly Order"])
                filtered = FilterImplementations.savgol_filter_wrapper(ph_data, best_window, best_poly)
                filtered_signals[f"Best {filter_type}"] = filtered
                
            elif filter_type == "Oversampling + Decimation":
                best_factor = int(best_row["Oversampling Factor"])
                best_window = int(best_row["Window Size"])
                filtered = FilterImplementations.oversampling_decimation(ph_data, best_factor, best_window)
                filtered_signals[f"Best {filter_type}"] = filtered
            
            best_filters[filter_type] = best_row.to_dict()
    
    # Criar DataFrame com os sinais filtrados
    filtered_df = pd.DataFrame({"Time": time})
    for name, signal in filtered_signals.items():
        filtered_df[name] = signal
    
    return results_df, filtered_df, best_filters, all_filtered_signals

# 4. Função principal
def main():
    # Carregar dados
    df, file_path = load_data()
    if df is None:
        print("Não foi possível carregar os dados.")
        return
    
    # Identificar colunas de tempo e pH
    print("Identificando colunas...")
    
    # Buscar coluna de tempo
    time_candidates = ['Time (ms)', 'Time', 'time']
    time_col = None
    for candidate in time_candidates:
        if candidate in df.columns:
            time_col = candidate
            break
    
    if time_col is None:
        print("Colunas disponíveis:")
        for i, col in enumerate(df.columns):
            print(f"  {i}: {col}")
        col_idx = int(input("Digite o número da coluna de tempo: "))
        time_col = df.columns[col_idx]
    
    # Buscar coluna de pH
    ph_candidates = ['pH (V)', 'pH Voltage', 'phVoltage', 'avgPHVoltage']
    ph_col = None
    for candidate in ph_candidates:
        if candidate in df.columns:
            ph_col = candidate
            break
    
    if ph_col is None:
        ph_cols = [col for col in df.columns if 'ph' in col.lower()]
        if ph_cols:
            ph_col = ph_cols[0]
        else:
            print("Colunas disponíveis:")
            for i, col in enumerate(df.columns):
                print(f"  {i}: {col}")
            col_idx = int(input("Digite o número da coluna de pH: "))
            ph_col = df.columns[col_idx]
    
    # Converter e limpar dados
    time = pd.to_numeric(df[time_col], errors='coerce').values
    ph_data = pd.to_numeric(df[ph_col], errors='coerce').values
    
    # Remover NaN
    valid = ~np.isnan(time) & ~np.isnan(ph_data)
    time = time[valid]
    ph_data = ph_data[valid]
    
    print(f"\nDados carregados com sucesso:")
    print(f"  Arquivo: {os.path.basename(file_path)}")
    print(f"  Coluna de tempo: {time_col}")
    print(f"  Coluna de pH: {ph_col}")
    print(f"  Número de pontos: {len(time)}")
    
    # Otimização de filtros
    results_df, filtered_df, best_filters, all_filtered_signals = optimize_filters(time, ph_data)
    
    # Salvar resultados nos dois arquivos existentes
    output_base = os.path.splitext(file_path)[0]
    results_path = f"{output_base}_filter_report.csv"
    filtered_path = f"{output_base}_filtered_signals.csv"
    
    results_df.to_csv(results_path, index=False)
    filtered_df.to_csv(filtered_path, index=False)
    
    # Salvar o terceiro arquivo com todas as variações de filtros
    all_signals_path = f"{output_base}_all_filtered_signals.csv"
    all_signals_df = pd.DataFrame({"Time (ms)": time, "Original pH Voltage": ph_data})
    
    # Adicionar cada sinal filtrado como uma coluna
    for name, signal in all_filtered_signals.items():
        if name != "Original":  # Já incluímos o original
            all_signals_df[name] = signal
    
    # Salvar o terceiro arquivo
    all_signals_df.to_csv(all_signals_path, index=False)
    
    print(f"\nResultados salvos em:")
    print(f"  {os.path.basename(results_path)}")
    print(f"  {os.path.basename(filtered_path)}")
    print(f"  {os.path.basename(all_signals_path)}")
    
    # Relatório final
    print("\n=== RELATÓRIO DE FILTROS ===")
    print("Melhores filtros por tipo:")
    for filter_type, params in best_filters.items():
        print(f"\n{filter_type}:")
        print(f"  Desvio padrão: {params['Std Deviation']:.6f}")
        
        if params['Window Size'] is not None:
            print(f"  Tamanho da janela: {int(params['Window Size'])}")
        if params['Alpha'] is not None:
            print(f"  Alpha: {params['Alpha']:.3f}")
        if params['Process Variance'] is not None:
            print(f"  Variância do processo: {params['Process Variance']}")
        if params['Measurement Variance'] is not None:
            print(f"  Variância da medição: {params['Measurement Variance']}")
        if params['Poly Order'] is not None:
            print(f"  Ordem do polinômio: {int(params['Poly Order'])}")
        if params['Oversampling Factor'] is not None:
            print(f"  Fator de sobreamostragem: {int(params['Oversampling Factor'])}")
    
    # Encontrar filtro com menor desvio padrão geral
    best_filter_type = min(best_filters.items(), key=lambda x: x[1]['Std Deviation'])[0]
    best_params = best_filters[best_filter_type]
    
    print("\nFiltro recomendado para implementação:")
    print(f"  Tipo: {best_filter_type}")
    print(f"  Desvio padrão: {best_params['Std Deviation']:.6f}")
    
    # Visualização
    plt.figure(figsize=(10, 6))

if __name__ == "__main__":
    main()