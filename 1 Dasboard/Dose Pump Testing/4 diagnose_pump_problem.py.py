#!/usr/bin/env python3
"""
Test script to diagnose and fix pump activation issues
"""
import serial
import time
import json

# Configuração
PORT = "/dev/cu.usbserial-110" 
BAUDRATE = 115200
PIN = 26  # pH minus
DURATION_MS = 1000

def test_connection():
    """Teste básico de conexão com o ESP32"""
    print("\n===== TESTE DE CONEXÃO =====")
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=2) as ser:
            print(f"✅ Conexão com {PORT} estabelecida")
            
            # Limpar buffer
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Esperar um momento para ESP32 se estabilizar
            print("Esperando ESP32 inicializar...")
            time.sleep(1.5)
            
            # Enviar comando conhecido
            print("📤 Enviando comando STATUS...")
            ser.write(b'STATUS\n')  # Comando simples
            
            # Ler resposta
            start_time = time.time()
            response_received = False
            
            print("📥 Aguardando resposta...")
            while time.time() - start_time < 3.0:
                if ser.in_waiting:
                    response = ser.readline().decode().strip()
                    print(f"  → Recebido: {response}")
                    response_received = True
                time.sleep(0.1)
            
            if not response_received:
                # Tente outro comando conhecido
                print("📤 Tentando comando TEST_PIN_26...")
                ser.write(b'TEST_PIN_26\n')
                
                start_time = time.time()
                while time.time() - start_time < 3.0:
                    if ser.in_waiting:
                        response = ser.readline().decode().strip()
                        print(f"  → Recebido: {response}")
                        response_received = True
                    time.sleep(0.1)
                
                if not response_received:
                    print("❌ ERRO: ESP32 não respondeu aos comandos básicos")
                    return False
            
            return True
            
    except Exception as e:
        print(f"❌ ERRO: Falha na conexão: {e}")
        return False

def test_direct_command():
    """Teste comando direto ao ESP32"""
    print("\n===== TESTE DE COMANDO DIRETO =====")
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=2) as ser:
            # Limpar buffer
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Montar comando JSON exatamente como os scripts de teste que funcionam
            cmd = {
                "action": "dose",
                "pin": PIN,
                "duration_ms": DURATION_MS,
                "pump_type": "ph_minus"
            }
            
            cmd_str = json.dumps(cmd) + '\n'
            
            # Enviar comando
            print(f"📤 Enviando: {cmd_str.strip()}")
            ser.write(cmd_str.encode())
            
            # Monitorar respostas por um período mais longo
            start_time = time.time()
            print(f"📥 Monitorando respostas por {DURATION_MS/1000 + 3} segundos...")
            
            while time.time() - start_time < (DURATION_MS/1000 + 3):
                if ser.in_waiting:
                    response = ser.readline().decode().strip()
                    print(f"  → {time.time() - start_time:.1f}s: {response}")
                time.sleep(0.1)
                
            print("✅ Teste concluído")
            
    except Exception as e:
        print(f"❌ ERRO: {e}")

def test_alternate_format():
    """Teste formato alternativo do comando"""
    print("\n===== TESTE DE FORMATO ALTERNATIVO =====")
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=2) as ser:
            # Limpar buffer
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Formato simplificado (usado em alguns testes)
            cmd = b'{"action":"dose","pin":26,"duration_ms":1000}\n'
            
            print(f"📤 Enviando comando simplificado: {cmd.decode().strip()}")
            ser.write(cmd)
            
            # Monitorar respostas
            start_time = time.time()
            print(f"📥 Monitorando respostas por {DURATION_MS/1000 + 3} segundos...")
            
            while time.time() - start_time < (DURATION_MS/1000 + 3):
                if ser.in_waiting:
                    response = ser.readline().decode().strip()
                    print(f"  → {time.time() - start_time:.1f}s: {response}")
                time.sleep(0.1)
                
    except Exception as e:
        print(f"❌ ERRO: {e}")

def test_test_pin_command():
    """Teste usando o comando TEST_PIN direto"""
    print("\n===== TESTE COM COMANDO TEST_PIN =====")
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=2) as ser:
            # Limpar buffer
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Enviar comando de teste direto
            print("📤 Enviando comando TEST_PIN_26...")
            ser.write(b'TEST_PIN_26\n')
            
            # Monitorar respostas
            start_time = time.time()
            print("📥 Monitorando respostas por 15 segundos...")
            
            while time.time() - start_time < 15:
                if ser.in_waiting:
                    response = ser.readline().decode().strip()
                    print(f"  → {time.time() - start_time:.1f}s: {response}")
                time.sleep(0.1)
                
    except Exception as e:
        print(f"❌ ERRO: {e}")

if __name__ == "__main__":
    print("🔍 DIAGNÓSTICO DE PROBLEMA DE ATIVAÇÃO DE BOMBAS")
    print(f"🔌 Porta: {PORT}, Baudrate: {BAUDRATE}")
    print(f"📌 Testando pino {PIN} por {DURATION_MS}ms")
    
    if test_connection():
        test_direct_command()
        test_alternate_format()
        test_test_pin_command()
    
    print("\n===== CONCLUSÃO DO DIAGNÓSTICO =====")
    print("""
    1) Se algum teste ativou a bomba:
       - Verifique as diferenças no formato do comando JSON entre esse teste e o dosing_controller
       
    2) Se nenhum teste ativou a bomba:
       - Verifique as conexões físicas entre ESP32 e os relés
       - Verifique se o firmware do ESP32 está processando corretamente os comandos JSON
       - Verifique se há problemas de energia/potência nos relés ou bombas
       - Teste manualmente os pinos do ESP32 para confirmar funcionamento do hardware
    """)