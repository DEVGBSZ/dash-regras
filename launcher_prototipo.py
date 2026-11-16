"""Abre o protótipo local no navegador ao iniciar o executável."""

import socket
import threading
import webbrowser


def available_port(start=8060, end=8100):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Nenhuma porta local disponível entre 8060 e 8099.")


def main():
    from app import app

    port = available_port()
    address = f"http://127.0.0.1:{port}/"
    print(f"Protótipo iniciado em {address}")
    print("Mantenha esta janela aberta enquanto testa a tela. Feche-a para encerrar.")
    threading.Timer(1.5, webbrowser.open, args=(address,)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
