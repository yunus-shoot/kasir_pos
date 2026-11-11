// Scanner JavaScript - Support HP/Mobile

var beepSound = new Audio('/static/sound/scanner.mp3');
var currentCart = [];
var quaggaRunning = false;
var lastScannedCode = '';
var lastScanTime = 0;
var isProcessing = false;

function playBeep() {
    beepSound.currentTime = 0;
    beepSound.play().catch(function(e) { 
        console.log("Audio play error:", e); 
    });
}

function updateCartDisplay() {
    // Scanner JavaScript - Support HP/Mobile

    var beepSound = new Audio('/static/sound/scanner.mp3');
    var currentCart = [];
    var quaggaRunning = false;
    var lastScannedCode = '';
    var lastScanTime = 0;
    var isProcessing = false;

    function playBeep() {
        beepSound.currentTime = 0;
        beepSound.play().catch(function(e) { 
            console.log("Audio play error:", e); 
        });
    }

    function updateCartDisplay() {
        var cartTable = document.getElementById('cartBody');
        var cartTotal = document.getElementById('cartTotal');
    
        if (!cartTable || !cartTotal) return;
    
        if (currentCart && currentCart.length > 0) {
            var html = '';
            var total = 0;
            for (var i = 0; i < currentCart.length; i++) {
                var item = currentCart[i];
                html += '<tr><td>' + item.nama_barang + '</td><td>' + item.jumlah + '</td><td>Rp ' + item.subtotal.toLocaleString('id-ID') + '</td></tr>';
                total += item.subtotal;
            }
            cartTable.innerHTML = html;
            cartTotal.textContent = 'Rp ' + total.toLocaleString('id-ID');
        } else {
            cartTable.innerHTML = '<tr><td colspan="3" class="text-center text-muted">Keranjang kosong</td></tr>';
            cartTotal.textContent = 'Rp 0';
        }
    }

    function fetchCart() {
        fetch('/transaksi')
            .then(function(res) { return res.json(); })
            .then(function(data) { 
                currentCart = data.cart || [];
                updateCartDisplay();
            })
            .catch(function() {
                console.log("Error fetching cart");
            });
    }

    function checkMobile() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    }

    document.addEventListener('DOMContentLoaded', function() {
        fetchCart();
    
        setTimeout(function() { 
            startCamera(); 
        }, 500);
    
        setInterval(function() {
            fetchCart();
        }, 3000);
    
        var barcodeInput = document.getElementById('barcodeInput');
        if (barcodeInput) {
            barcodeInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') doScan();
            });
        
            barcodeInput.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') barcodeInput.value = '';
            });
        
            // Auto focus pada mobile
            if (checkMobile()) {
                barcodeInput.focus();
            }
        }
    });

    function doScan() {
        if (isProcessing) return;
    
        var barcodeInput = document.getElementById('barcodeInput');
        if (!barcodeInput) return;
    
        var barcode = barcodeInput.value.trim();
        if (!barcode) return;
    
        isProcessing = true;
        lastScannedCode = '';
        lastScanTime = 0;
    
        fetch('/scan-barcode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({barcode: barcode})
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                playBeep();
                addToCart(data.barang.id);
                showResult(data.barang);
            } else {
                showError(data.message);
                isProcessing = false;
            }
        })
        .catch(function(err) {
            showError("Error: " + err);
            isProcessing = false;
        });
    }

    function showResult(barang) {
        var resultDiv = document.getElementById('scanResult');
        if (!resultDiv) return;
    
        resultDiv.innerHTML = '<div class="alert alert-success mb-0">' +
            '<h6 class="mb-2"><i class="bi bi-check-circle"></i> ' + barang.nama_barang + '</h6>' +
            '<div class="row">' +
            '<div class="col-6"><small class="text-muted">Kode</small><br><strong>' + barang.kode_barang + '</strong></div>' +
            '<div class="col-6"><small class="text-muted">Harga</small><br><strong>Rp ' + parseInt(barang.harga_jual).toLocaleString('id-ID') + '</strong></div>' +
            '</div></div>';
    }

    function showError(message) {
        var resultDiv = document.getElementById('scanResult');
        if (!resultDiv) return;
    
        resultDiv.innerHTML = '<div class="alert alert-danger mb-0"><i class="bi bi-exclamation-triangle"></i> ' + message + '</div>';
    }

    function addToCart(barangId) {
        fetch('/transaksi', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({barang_id: barangId, jumlah: 1})
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                var barcodeInput = document.getElementById('barcodeInput');
                if (barcodeInput) {
                    barcodeInput.value = '';
                }
                currentCart = data.cart || [];
                updateCartDisplay();
            
                setTimeout(function() { 
                    isProcessing = false;
                    lastScannedCode = '';
                }, 2000);
            } else {
                isProcessing = false;
            }
        })
        .catch(function(err) {
            console.log("Add to cart error:", err);
            isProcessing = false;
        });
    }

    // QuaggaJS - Lebih baik untuk HP
    function startCamera() {
        if (quaggaRunning) {
            Quagga.stop();
            quaggaRunning = false;
        }
    
        var readerDiv = document.getElementById('reader');
        var btn = document.getElementById('startCameraBtn');
        var isMobile = checkMobile();
    
        if (!readerDiv) return;
    
        readerDiv.style.display = 'block';
        if (btn) {
            btn.innerHTML = isMobile ? '<i class="bi bi-camera-fill"></i> Kamera HP Aktif' : '<i class="bi bi-camera-fill"></i> Kamera Aktif';
            btn.className = 'btn btn-danger btn-sm';
        }
        readerDiv.innerHTML = '';
    
        // Prioritas: mobile pakai back camera, desktop bisa front/back
        var facingMode = isMobile ? { exact: "environment" } : "environment";
    
        Quagga.init({
            inputStream: {
                name: "Live",
                type: "LiveStream",
                target: readerDiv,
                constraints: {
                    facingMode: facingMode,
                    width: { min: 640, ideal: isMobile ? 1280 : 1280 },
                    height: { min: 480, ideal: isMobile ? 720 : 720 }
                }
            },
    decoder: {
                readers: [
                    "ean_reader",
                    "code_128_reader"
                ]
            },
            locate: true,
            locator: {
                patchSize: isMobile ? "large" : "medium",
                halfSample: isMobile ? false : true
            }
        }, function(err) {
            if (err) {
                console.error("Quagga error:", err);
                var resultDiv = document.getElementById('scanResult') || document.getElementById('result') || readerDiv;
                var errMsg = (err && err.message) ? err.message : String(err);
                if (resultDiv && resultDiv.innerHTML !== undefined) {
                    resultDiv.innerHTML = '<div class="alert alert-warning mb-0">' +
                        '<i class="bi bi-exclamation-triangle"></i> Camera error: ' + errMsg + '<br>' +
                        '<small>Pakai HTTPS atau izinkan camera di browser</small></div>';
                }
                readerDiv.style.display = 'none';
                if (btn) {
                    btn.innerHTML = isMobile ? '<i class="bi bi-camera"></i> Coba Kamera' : '<i class="bi bi-camera"></i> Coba';
                    btn.className = 'btn btn-success btn-sm';
                }
                return;
            }
        
            Quagga.start();
            quaggaRunning = true;
        
            // Styling video
            setTimeout(function() {
                var video = readerDiv.querySelector('video');
                if (video) {
                    video.style.width = '100%';
                    video.style.height = '100%';
                    video.style.objectFit = 'cover';
                }
            }, 200);
        
            Quagga.onDetected(onBarcodeDetected);
        });
    }

    function stopCamera() {
        var readerDiv = document.getElementById('reader');
        var btn = document.getElementById('startCameraBtn');
    
        if (quaggaRunning) {
            Quagga.stop();
            quaggaRunning = false;
        
            if (readerDiv) {
                readerDiv.style.display = 'none';
                readerDiv.innerHTML = '';
            }
        
            if (btn) {
                btn.innerHTML = '<i class="bi bi-camera"></i> Mulai';
                btn.className = 'btn btn-success btn-sm';
            }
        }
    
        isProcessing = false;
        lastScannedCode = '';
    }

    function onBarcodeDetected(result) {
        if (isProcessing) return;
    
        var code = result.codeResult.code;
        var now = Date.now();
    
        if (lastScanTime > 0 && (now - lastScanTime) > 5000) {
            lastScannedCode = '';
        }
    
        if (code === lastScannedCode && (now - lastScanTime) < 5000) {
            return;
        }
    
        lastScannedCode = code;
        lastScanTime = now;
    
        var barcodeInput = document.getElementById('barcodeInput');
        if (barcodeInput) {
            barcodeInput.value = code;
        }
    
        doScan();
    }
