"""Run Kasir POS so other devices on the local network can access it."""
import socket

from app import create_app


def get_lan_ip():
    """Find the local IPv4 address used to reach other network devices."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect(("8.8.8.8", 80))
        return connection.getsockname()[0]


app = create_app("development")

if __name__ == "__main__":
    try:
        lan_ip = get_lan_ip()
    except OSError as error:
        raise SystemExit(
            f"Tidak dapat mendeteksi IP jaringan lokal: {error}. "
            "Pastikan komputer terhubung ke jaringan."
        ) from error

    print(f"Kasir POS dapat diakses di perangkat satu jaringan: http://{lan_ip}:5000")
    print("Pastikan firewall Windows mengizinkan koneksi masuk pada port 5000.")
    app.run(host="0.0.0.0", port=5000, debug=False)
