1 Dashboard

# Navegar para o diretório
cd "/home/penutaco/Desktop/4 HP Autocal Dosing Stages ECSolA ECSolB ECSolC ECminus/0 Dasboard"

# Criar ambiente virtual
python3 -m venv myenv

# Ativar ambiente virtual
source myenv/bin/activate

# Instalar todas as dependências necessárias
pip install pyzmq dash plotly dash-bootstrap-components pyserial pandas numpy torch

# Verificar se todas as bibliotecas foram instaladas
python3 -c "import zmq, dash, plotly, serial, pandas, numpy, torch; print('✅ All libraries installed successfully')"

# Executar o dashboard
python3 "1p2 dashboard v10.py"



2 Dosing Controller

# 1. Navegar para o diretório
cd "/home/penutaco/Desktop/4 HP Autocal Dosing Stages ECSolA ECSolB ECSolC ECminus/0 Dasboard"

# 2. Ativar ambiente virtual (deve já existir do dashboard)
source myenv/bin/activate

# 3. Verificar se ambiente virtual está ativo
echo "✅ Ambiente virtual ativo: $(which python3)"

# 4. Instalar dependências adicionais se necessário (torch e numpy para IA)
pip install torch numpy pandas

# 5. Verificar se todas as bibliotecas estão instaladas
python3 -c "import zmq, torch, numpy, pandas; print('✅ Todas as bibliotecas do dosing controller instaladas')"

# 6. Atualizar porta serial automaticamente
AVAILABLE_PORT=$(ls /dev/tty* 2>/dev/null | grep -E "(USB|ACM|cu)" | head -1)
if [ -n "$AVAILABLE_PORT" ]; then
    echo "📱 Atualizando porta serial para: $AVAILABLE_PORT"
    sed -i "s|\"serial_port\": \"/dev/ttyUSB0\"|\"serial_port\": \"$AVAILABLE_PORT\"|" "1p3 dosing_controller V10p10.py"
    echo "✅ Porta atualizada no código"
fi

# 7. Executar o dosing controller
echo "🤖 Iniciando AI Dosing Controller..."
python3 "1p3 dosing_controller V10p12.py"


